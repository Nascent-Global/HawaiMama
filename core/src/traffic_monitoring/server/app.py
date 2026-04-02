from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import cv2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from traffic_monitoring.config import TrafficMonitoringConfig, apply_input_overrides, build_default_config
from traffic_monitoring.events import ViolationCode
from traffic_monitoring.pipeline import TrafficMonitoringPipeline
from traffic_monitoring.server.repository import AdminRepository, SeedPayloads, default_database_url
from traffic_monitoring.traffic import SignalStateMachine


def _build_camera_registry() -> dict[str, dict[str, object]]:
    cameras: dict[str, dict[str, object]] = {}
    for index in range(1, 10):
        camera_id = f"cam{index}"
        cameras[camera_id] = {
            "id": camera_id,
            "source": f"input/input{index}.mp4",
            "location": f"Input {index}",
            "status": "online",
            "system_mode": "enforcement_mode",
        }

    cameras["cam6"].update(
        {
            "location": "Lakeside",
            "system_mode": "traffic_management_mode",
            "intersection_id": "main_intersection",
            "lanes": ["north", "east"],
        }
    )
    cameras["cam9"].update(
        {
            "frame_skip": 2,
            "resolution": (720, 1280),
            "fps_limit": 8.0,
            "ocr_debug": False,
            "ocr_enabled": False,
        }
    )
    return cameras


def _load_seed_payloads(root: Path) -> SeedPayloads:
    admin_db_dir = root.parent / "admin" / "db"

    def _load_json(name: str) -> list[dict[str, object]]:
        path = admin_db_dir / name
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    return SeedPayloads(
        violations=_load_json("mock-violations.json"),
        accidents=_load_json("mock-accidents.json"),
        challans=_load_json("mock-challans.json"),
    )


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp_to_iso(timestamp_seconds: float) -> str:
    return datetime.fromtimestamp(timestamp_seconds, tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


app = FastAPI(title="Traffic Monitoring Stream Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_base_config = build_default_config()
_base_config.runtime.output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=str(_base_config.runtime.output_dir)), name="snapshots")
app.mount("/inputs", StaticFiles(directory=str(_base_config.root / "input")), name="inputs")

cameras: dict[str, dict[str, object]] = _build_camera_registry()
repository = AdminRepository(default_database_url(), project_root=_base_config.root)
repository.initialize(cameras, _load_seed_payloads(_base_config.root))

events: list[dict[str, object]] = []
traffic_state_by_camera: dict[str, dict[str, object]] = {}
intersection_state_by_id: dict[str, dict[str, object]] = {}
_seen_event_keys: set[tuple[str, float, int, str]] = set()
_api_event_codes = {
    ViolationCode.OVERSPEED.value,
    ViolationCode.NO_HELMET.value,
    ViolationCode.PLATE_UNREADABLE.value,
    ViolationCode.PLATE_MISSING.value,
    ViolationCode.WRONG_LANE.value,
}
_intersection_signal_machines: dict[str, SignalStateMachine] = {}


def _camera_config(camera_id: str) -> tuple[str, TrafficMonitoringConfig]:
    camera = cameras.get(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Unknown camera: {camera_id}")
    source = str(camera["source"])

    config = build_default_config()
    stream_output_dir = config.runtime.output_dir / camera_id
    runtime = replace(
        config.runtime,
        input_video=Path(source),
        output_dir=stream_output_dir,
        snapshots_dir=stream_output_dir / "snapshots",
        records_path=stream_output_dir / config.output.violations_filename,
    )
    runtime_options = replace(
        config.runtime_options,
        system_mode=camera.get("system_mode", config.runtime_options.system_mode),
        ocr_debug=bool(camera.get("ocr_debug", config.runtime_options.ocr_debug)),
        overlay_mode=(
            "traffic_control"
            if camera.get("system_mode", config.runtime_options.system_mode) == "traffic_management_mode"
            else "monitoring"
        ),
    )
    performance = replace(
        config.performance,
        frame_skip=int(camera.get("frame_skip", config.performance.frame_skip)),
        resolution=camera.get("resolution", config.performance.resolution),
        fps_limit=float(camera.get("fps_limit", config.performance.fps_limit))
        if camera.get("fps_limit", config.performance.fps_limit) is not None
        else None,
    )
    speed = replace(
        config.speed,
        enabled=runtime_options.system_mode != "traffic_management_mode",
    )
    ocr = replace(
        config.ocr,
        enabled=bool(camera.get("ocr_enabled", config.ocr.enabled)),
    )
    config = replace(
        config,
        runtime=runtime,
        runtime_options=runtime_options,
        performance=performance,
        speed=speed,
        ocr=ocr,
    )
    return source, apply_input_overrides(config)


def _intersection_signal_machine(intersection_id: str) -> SignalStateMachine:
    machine = _intersection_signal_machines.get(intersection_id)
    if machine is not None:
        return machine

    config = build_default_config()
    lane_order: list[str] = []
    for camera in cameras.values():
        if camera.get("intersection_id") != intersection_id:
            continue
        for lane in camera.get("lanes", []):
            if lane not in lane_order:
                lane_order.append(lane)

    machine = SignalStateMachine(
        lane_order or [config.traffic_control.initial_active_lane],
        initial_active_lane=config.traffic_control.initial_active_lane,
        min_green_time=config.traffic_control.min_green_time,
        max_green_time=config.traffic_control.max_green_time,
        yellow_time=config.traffic_control.yellow_time,
        priority_queue_weight=config.traffic_control.priority_queue_weight,
        priority_wait_weight=config.traffic_control.priority_wait_weight,
        fairness_weight=config.traffic_control.fairness_weight,
        max_priority_score=config.traffic_control.max_priority_score,
    )
    _intersection_signal_machines[intersection_id] = machine
    return machine


def _update_intersection_state(camera_id: str, pipeline: TrafficMonitoringPipeline) -> None:
    camera = cameras.get(camera_id)
    if camera is None:
        return
    intersection_id = camera.get("intersection_id")
    if not intersection_id or pipeline.last_context is None:
        return

    timestamp = pipeline.last_context.timestamp_seconds
    traffic_state_by_camera[camera_id] = {
        **dict(pipeline.last_traffic_state),
        "timestamp_seconds": timestamp,
        "camera_id": camera_id,
        "intersection_id": intersection_id,
    }

    aggregate_lanes: dict[str, dict[str, float | int]] = {}
    participating_cameras: list[dict[str, object]] = []
    aggregate_timestamp = timestamp
    emergency_lane: str | None = None
    for member_camera_id, member_camera in cameras.items():
        if member_camera.get("intersection_id") != intersection_id:
            continue
        latest = traffic_state_by_camera.get(member_camera_id)
        if latest is None:
            continue
        participating_cameras.append(
            {
                "camera": member_camera_id,
                "lanes": member_camera.get("lanes", []),
                "timestamp_seconds": latest.get("timestamp_seconds"),
            }
        )
        aggregate_timestamp = max(
            aggregate_timestamp,
            float(latest.get("timestamp_seconds", aggregate_timestamp)),
        )
        if latest.get("emergency_lane") and emergency_lane is None:
            emergency_lane = str(latest.get("emergency_lane"))
        latest_lane_metrics = latest.get("lane_metrics", {})
        for lane in member_camera.get("lanes", []):
            metrics = latest_lane_metrics.get(lane)
            if metrics is None:
                continue
            aggregate_lanes[lane] = {
                "count": int(metrics.get("count", 0)),
                "queue": int(metrics.get("queue", 0)),
                "avg_wait": float(metrics.get("avg_wait", 0.0)),
            }

    if not aggregate_lanes:
        return

    signal_machine = _intersection_signal_machine(intersection_id)
    signal_snapshot = signal_machine.update(
        aggregate_timestamp,
        aggregate_lanes,
        emergency_lane=emergency_lane,
    )
    intersection_state_by_id[intersection_id] = {
        "intersection": intersection_id,
        "signal": signal_snapshot.to_dict(),
        "lanes": aggregate_lanes,
        "cameras": participating_cameras,
        "timestamp_seconds": round(aggregate_timestamp, 3),
    }


def _save_snapshot(
    *,
    camera_id: str,
    config: TrafficMonitoringConfig,
    track,
    context_time: float,
    violation: str,
    frame,
) -> str | None:
    if frame is None:
        return None
    bbox = track.bbox.clamp(frame.shape[1], frame.shape[0])
    x1, y1, x2, y2 = (int(value) for value in bbox.as_tuple())
    if x2 <= x1 or y2 <= y1:
        return None
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    config.runtime.snapshots_dir.mkdir(parents=True, exist_ok=True)
    timestamp_tag = f"{context_time:.3f}".replace(".", "_")
    filename = f"{camera_id}_{track.track_id}_{violation}_{timestamp_tag}.jpg"
    snapshot_path = config.runtime.snapshots_dir / filename
    if not cv2.imwrite(str(snapshot_path), crop):
        return None
    return f"/snapshots/{camera_id}/snapshots/{filename}"


def _camera_location_link(camera_id: str) -> str:
    camera = cameras.get(camera_id, {})
    return str(
        camera.get("location_link")
        or f"https://maps.google.com/?q={str(camera.get('location', 'Pokhara')).replace(' ', '+')}"
    )


def _build_violation_record(
    *,
    camera_id: str,
    track,
    timestamp_seconds: float,
    violation_code: str,
    image_path: str | None,
) -> dict[str, object]:
    location = str(cameras.get(camera_id, {}).get("location", "Pokhara"))
    violation_titles = {
        "overspeed": "Overspeed Violation",
        "no_helmet": "No Helmet Detected",
        "wrong_lane": "Wrong Lane Violation",
        "plate_missing": "License Plate Missing",
        "plate_unreadable": "License Plate Unreadable",
    }
    now = _utc_now_iso()
    timestamp = _timestamp_to_iso(timestamp_seconds)
    license_plate = (track.plate_text or f"{track.label_name[:2].upper()}-{track.track_id:04d}").upper()
    return {
        "id": str(uuid4()),
        "cameraId": camera_id,
        "trackId": track.track_id,
        "violationCode": violation_code,
        "vehicleType": track.label_name,
        "title": violation_titles.get(violation_code, "Traffic Violation"),
        "driverName": f"Tracked {track.label_name.title()} {track.track_id}",
        "age": 0,
        "dob": "2000-01-01T00:00:00Z",
        "bloodGroup": "Unknown",
        "licensePlate": license_plate,
        "tempAddress": location,
        "permAddress": location,
        "timestamp": timestamp,
        "locationLink": _camera_location_link(camera_id),
        "screenshot1Url": image_path or "",
        "screenshot2Url": image_path or "",
        "screenshot3Url": image_path or "",
        "videoUrl": f"/inputs/{Path(str(cameras.get(camera_id, {}).get('source', ''))).name}",
        "description": (
            f"{violation_titles.get(violation_code, 'Traffic violation')} detected at "
            f"{location}. Plate read: {track.plate_text or 'pending verification'}."
        ),
        "verified": False,
        "createdAt": now,
        "updatedAt": now,
    }


def _record_new_events(camera_id: str, pipeline: TrafficMonitoringPipeline) -> None:
    context = pipeline.last_context
    if context is None:
        return

    _, config = _camera_config(camera_id)
    tracks_by_id = {track.track_id: track for track in pipeline.last_tracks}
    for track_id, findings in pipeline.last_new_findings.items():
        track = tracks_by_id.get(track_id)
        if track is None:
            continue
        for finding in findings:
            violation = finding.code.value
            if violation not in _api_event_codes:
                continue
            timestamp = round(context.timestamp_seconds, 3)
            event_key = (camera_id, timestamp, track_id, violation)
            if event_key in _seen_event_keys:
                continue
            _seen_event_keys.add(event_key)
            image_path = _save_snapshot(
                camera_id=camera_id,
                config=config,
                track=track,
                context_time=timestamp,
                violation=violation,
                frame=pipeline.last_frame,
            )
            event_payload = {
                "camera": camera_id,
                "time": timestamp,
                "track_id": track_id,
                "vehicle": track.label_name,
                "plate": track.plate_text,
                "violation": violation,
                "image": image_path,
            }
            events.append(event_payload)
            repository.ingest_violation_event(
                _build_violation_record(
                    camera_id=camera_id,
                    track=track,
                    timestamp_seconds=timestamp,
                    violation_code=violation,
                    image_path=image_path,
                ),
                source_event_key=f"{camera_id}:{timestamp}:{track_id}:{violation}",
            )


def mjpeg_frame_generator(camera_id: str) -> Iterator[bytes]:
    source, config = _camera_config(camera_id)
    pipeline = TrafficMonitoringPipeline(config)
    for frame in pipeline.frame_generator(source):
        _record_new_events(camera_id, pipeline)
        _update_intersection_state(camera_id, pipeline)
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            continue
        payload = encoded.tobytes()
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + payload + b"\r\n"


@app.get("/video_feed")
def video_feed() -> StreamingResponse:
    return StreamingResponse(
        mjpeg_frame_generator("cam1"),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/camera/{camera_id}/stream")
def camera_stream(camera_id: str) -> StreamingResponse:
    return StreamingResponse(
        mjpeg_frame_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/surveillance/feeds")
def surveillance_feeds() -> JSONResponse:
    return JSONResponse(repository.list_surveillance_feeds())


@app.get("/events")
def list_events() -> JSONResponse:
    return JSONResponse(events)


@app.get("/cameras")
def list_cameras() -> JSONResponse:
    return JSONResponse(repository.list_cameras())


@app.get("/violations")
def list_violations() -> JSONResponse:
    return JSONResponse(repository.list_violations())


@app.get("/violations/{violation_id}")
def get_violation(violation_id: str) -> JSONResponse:
    violation = repository.get_violation(violation_id)
    if violation is None:
        raise HTTPException(status_code=404, detail=f"Unknown violation: {violation_id}")
    return JSONResponse(violation)


@app.post("/violations/{violation_id}/verify")
def verify_violation(violation_id: str) -> JSONResponse:
    result = repository.verify_violation(violation_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown violation: {violation_id}")
    return JSONResponse(result)


@app.get("/accidents")
def list_accidents() -> JSONResponse:
    return JSONResponse(repository.list_accidents())


@app.get("/accidents/{accident_id}")
def get_accident(accident_id: str) -> JSONResponse:
    accident = repository.get_accident(accident_id)
    if accident is None:
        raise HTTPException(status_code=404, detail=f"Unknown accident: {accident_id}")
    return JSONResponse(accident)


@app.post("/accidents/{accident_id}/verify")
def verify_accident(accident_id: str) -> JSONResponse:
    result = repository.verify_accident(accident_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown accident: {accident_id}")
    return JSONResponse(result)


@app.get("/challans")
def list_challans() -> JSONResponse:
    return JSONResponse(repository.list_challans())


@app.get("/challans/{challan_id}")
def get_challan(challan_id: str) -> JSONResponse:
    challan = repository.get_challan(challan_id)
    if challan is None:
        raise HTTPException(status_code=404, detail=f"Unknown challan: {challan_id}")
    return JSONResponse(challan)


@app.get("/traffic/state")
def traffic_state() -> JSONResponse:
    if intersection_state_by_id:
        intersection_id = next(reversed(intersection_state_by_id))
        latest = intersection_state_by_id[intersection_id]
        return JSONResponse(latest)
    return JSONResponse({"intersection": None, "signal": {}, "lanes": {}, "cameras": []})


@app.get("/traffic/lanes")
def traffic_lanes() -> JSONResponse:
    if intersection_state_by_id:
        intersection_id = next(reversed(intersection_state_by_id))
        latest = intersection_state_by_id[intersection_id]
        return JSONResponse(
            {
                "intersection": intersection_id,
                "lanes": latest.get("lanes", {}),
                "cameras": latest.get("cameras", []),
            }
        )
    return JSONResponse({"intersection": None, "lanes": {}, "cameras": []})
