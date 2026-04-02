from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections import deque
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import cv2
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from traffic_monitoring.config import TrafficMonitoringConfig, apply_input_overrides, build_default_config
from traffic_monitoring.events import ViolationCode
from traffic_monitoring.mock_dotm_service import load_mock_dotm_service
from traffic_monitoring.pipeline import TrafficMonitoringPipeline
from traffic_monitoring.server.repository import AdminRepository, default_database_url
from traffic_monitoring.storage import build_object_storage, load_object_storage_settings
from traffic_monitoring.traffic import SignalStateMachine


def _camera_sort_key(path: Path) -> tuple[int, str]:
    suffix = path.stem[2:]
    return (int(suffix) if suffix.isdigit() else 10_000, path.stem)


def _discover_surveillance_videos(root: Path) -> list[Path]:
    surveillance_dir = root / "surveillance"
    surveillance_dir.mkdir(parents=True, exist_ok=True)
    return sorted(surveillance_dir.glob("nv*.mp4"), key=_camera_sort_key)


def _build_camera_registry(root: Path) -> dict[str, dict[str, object]]:
    cameras: dict[str, dict[str, object]] = {}
    for index, video_path in enumerate(_discover_surveillance_videos(root), start=1):
        camera_id = video_path.stem.lower()
        label = camera_id.upper() if camera_id.startswith("nv") else f"Input {index}"
        cameras[camera_id] = {
            "id": camera_id,
            "source": str(video_path),
            "location": label,
            "location_link": f"https://maps.google.com/?q={label.replace(' ', '+')}",
            "status": "online",
            "system_mode": "enforcement_mode",
        }
    return cameras

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
load_dotenv(_base_config.root / ".env", override=False)
_object_storage_settings = load_object_storage_settings(_base_config.root)
_base_config.runtime.output_dir.mkdir(parents=True, exist_ok=True)
(_base_config.root / "surveillance").mkdir(parents=True, exist_ok=True)
_object_storage_settings.local_root.mkdir(parents=True, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=str(_base_config.runtime.output_dir)), name="snapshots")
app.mount("/inputs", StaticFiles(directory=str(_base_config.root / "input")), name="inputs")
app.mount(
    "/surveillance-media",
    StaticFiles(
        directory=str(_base_config.root / "surveillance"),
        follow_symlink=True,
    ),
    name="surveillance-media",
)
app.mount(
    "/surveillance-output",
    StaticFiles(
        directory=str(_base_config.root / "surveillance" / "output"),
        follow_symlink=True,
    ),
    name="surveillance-output",
)
app.mount(
    "/wwwroots",
    StaticFiles(
        directory=str(_object_storage_settings.local_root),
        follow_symlink=True,
    ),
    name="wwwroots",
)

cameras: dict[str, dict[str, object]] = _build_camera_registry(_base_config.root)
repository = AdminRepository(default_database_url(), project_root=_base_config.root)
repository.initialize(cameras)
object_storage = build_object_storage(_base_config.root)
vehicle_registry = load_mock_dotm_service(_base_config.root)

events: list[dict[str, object]] = []
traffic_state_by_camera: dict[str, dict[str, object]] = {}
intersection_state_by_id: dict[str, dict[str, object]] = {}
_seen_event_keys: set[tuple[str, float, int, str]] = set()
_recent_frames_by_camera: dict[str, deque[tuple[float, object]]] = {}
_api_event_codes = {
    ViolationCode.OVERSPEED.value,
    ViolationCode.NO_HELMET.value,
    ViolationCode.PLATE_UNREADABLE.value,
    ViolationCode.PLATE_MISSING.value,
    ViolationCode.WRONG_LANE.value,
}
_intersection_signal_machines: dict[str, SignalStateMachine] = {}
_VIOLATION_CLIP_PRE_SECONDS = 3.0
_VIOLATION_CLIP_MAX_SECONDS = 6.0


class CameraConfigUpdate(BaseModel):
    system_mode: Literal["enforcement_mode", "traffic_management_mode"] | None = None
    location: str | None = None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown"


def _camera_location(camera_id: str) -> str:
    return str(cameras.get(camera_id, {}).get("location", "Pokhara"))


def _refresh_camera_inventory() -> None:
    global cameras
    discovered = _build_camera_registry(_base_config.root)
    repository.sync_cameras(discovered)
    stored = {camera["id"]: camera for camera in repository.list_cameras()}
    cameras = {
        camera_id: {**camera, **stored.get(camera_id, {})}
        for camera_id, camera in discovered.items()
    }


_refresh_camera_inventory()


def _camera_config(camera_id: str) -> tuple[str, TrafficMonitoringConfig]:
    _refresh_camera_inventory()
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

    ok, encoded = cv2.imencode(".jpg", crop)
    if not ok:
        return None

    timestamp = datetime.fromtimestamp(context_time, tz=UTC)
    timestamp_tag = timestamp.strftime("%H%M%S_%f")
    location_slug = _slugify(_camera_location(camera_id))
    owner_snapshot = _owner_snapshot(
        camera_id=camera_id,
        track=track,
        seed=f"{camera_id}:{track.track_id}:{timestamp_tag}:{violation}",
    )
    storage_key = (
        f"violations/{timestamp:%Y/%m/%d}/{camera_id}-{location_slug}/"
        f"{violation}/track-{track.track_id}/{timestamp_tag}_snapshot.jpg"
    )
    image_url = object_storage.put_bytes(
        storage_key,
        encoded.tobytes(),
        content_type="image/jpeg",
    )
    metadata_key = storage_key.rsplit(".", maxsplit=1)[0] + ".json"
    metadata_payload = {
        "plate": track.plate_text,
        "owner_name": owner_snapshot["owner_name"],
        "owner_address": owner_snapshot["owner_address"],
        "violation": violation,
        "camera_id": camera_id,
        "camera_location": _camera_location(camera_id),
        "timestamp": _timestamp_to_iso(context_time),
        "image_url": image_url,
        "is_mock_data": owner_snapshot["is_mock_data"],
    }
    object_storage.put_bytes(
        metadata_key,
        json.dumps(metadata_payload, indent=2).encode("utf-8"),
        content_type="application/json",
    )
    return image_url


def _remember_frame(camera_id: str, pipeline: TrafficMonitoringPipeline) -> None:
    context = pipeline.last_context
    frame = pipeline.last_frame
    if context is None or frame is None:
        return

    frame_buffer = _recent_frames_by_camera.setdefault(camera_id, deque())
    frame_buffer.append((context.timestamp_seconds, frame.copy()))
    cutoff = context.timestamp_seconds - _VIOLATION_CLIP_MAX_SECONDS
    while frame_buffer and frame_buffer[0][0] < cutoff:
        frame_buffer.popleft()


def _save_violation_clip(
    *,
    camera_id: str,
    track,
    context_time: float,
    violation: str,
) -> str | None:
    frame_buffer = _recent_frames_by_camera.get(camera_id)
    if not frame_buffer:
        return None

    clip_start_time = context_time - _VIOLATION_CLIP_PRE_SECONDS
    selected_frames = [
        (timestamp, frame)
        for timestamp, frame in frame_buffer
        if clip_start_time <= timestamp <= context_time
    ]
    if len(selected_frames) < 2:
        return None

    duration = max(selected_frames[-1][0] - selected_frames[0][0], 0.1)
    fps = min(24.0, max(6.0, (len(selected_frames) - 1) / duration))
    timestamp = datetime.fromtimestamp(context_time, tz=UTC)
    timestamp_tag = timestamp.strftime("%H%M%S_%f")
    location_slug = _slugify(_camera_location(camera_id))
    storage_key = (
        f"violations/{timestamp:%Y/%m/%d}/{camera_id}-{location_slug}/"
        f"{violation}/track-{track.track_id}/{timestamp_tag}_clip.mp4"
    )

    with tempfile.TemporaryDirectory(prefix=f"{camera_id}_{violation}_") as temp_dir:
        temp_path = Path(temp_dir)
        for index, (_, frame) in enumerate(selected_frames):
            frame_path = temp_path / f"frame_{index:05d}.jpg"
            if not cv2.imwrite(str(frame_path), frame):
                return None

        clip_path = temp_path / "clip.mp4"
        command = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            f"{fps:.2f}",
            "-i",
            str(temp_path / "frame_%05d.jpg"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(clip_path),
        ]
        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None
        if not clip_path.exists():
            return None

        return object_storage.put_file(
            storage_key,
            clip_path,
            content_type="video/mp4",
        )


def _camera_location_link(camera_id: str) -> str:
    camera = cameras.get(camera_id, {})
    return str(
        camera.get("location_link")
        or f"https://maps.google.com/?q={_camera_location(camera_id).replace(' ', '+')}"
    )


def _owner_snapshot(*, camera_id: str, track, seed: str) -> dict[str, object]:
    fallback = vehicle_registry.choose_demo_record(seed=seed)
    return {
        "owner_name": str(track.metadata.get("owner_name") or fallback.owner_name),
        "owner_address": str(track.metadata.get("owner_address") or fallback.address),
        "vehicle_color": str(track.metadata.get("vehicle_color") or fallback.color),
        "registration_date": str(track.metadata.get("registration_date") or fallback.registration_date),
        "owner_contact_number": str(track.metadata.get("owner_contact_number") or fallback.contact_number),
        "is_mock_data": bool(track.metadata.get("is_mock_data", True)),
    }


def _build_violation_record(
    *,
    camera_id: str,
    track,
    timestamp_seconds: float,
    violation_code: str,
    image_path: str | None,
    clip_url: str | None,
) -> dict[str, object]:
    location = _camera_location(camera_id)
    source_path = Path(str(cameras.get(camera_id, {}).get("source", "")))
    if source_path.parent.name == "surveillance":
        source_video_url = f"/surveillance-media/{source_path.name}"
    else:
        source_video_url = f"/inputs/{source_path.name}"
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
    owner_snapshot = _owner_snapshot(
        camera_id=camera_id,
        track=track,
        seed=f"{camera_id}:{track.track_id}:{timestamp}",
    )
    owner_name = str(owner_snapshot["owner_name"])
    owner_address = str(owner_snapshot["owner_address"])
    vehicle_color = str(owner_snapshot["vehicle_color"])
    registration_date = str(owner_snapshot["registration_date"])
    owner_contact_number = str(owner_snapshot["owner_contact_number"])
    is_mock_data = bool(owner_snapshot["is_mock_data"])
    vehicle_type = str(track.metadata.get("owner_vehicle_type") or track.label_name)
    return {
        "id": str(uuid4()),
        "cameraId": camera_id,
        "trackId": track.track_id,
        "violationCode": violation_code,
        "vehicleType": vehicle_type,
        "title": violation_titles.get(violation_code, "Traffic Violation"),
        "driverName": owner_name,
        "age": 0,
        "dob": "2000-01-01T00:00:00Z",
        "bloodGroup": "Unknown",
        "licensePlate": license_plate,
        "tempAddress": owner_address,
        "permAddress": owner_address,
        "timestamp": timestamp,
        "locationLink": _camera_location_link(camera_id),
        "screenshot1Url": image_path or "",
        "screenshot2Url": "",
        "screenshot3Url": "",
        "videoUrl": clip_url or source_video_url,
        "description": (
            f"{violation_titles.get(violation_code, 'Traffic violation')} detected at "
            f"{location}. Plate read: {track.plate_text or 'pending verification'}. "
            f"Owner: {owner_name}."
        ),
        "verified": False,
        "cameraLocation": location,
        "cameraLocationLink": _camera_location_link(camera_id),
        "evidenceProvider": object_storage.provider,
        "evidenceClipUrl": clip_url or "",
        "sourceVideoUrl": source_video_url,
        "ownerName": owner_name,
        "ownerAddress": owner_address,
        "ownerContactNumber": owner_contact_number,
        "vehicleColor": vehicle_color,
        "registrationDate": registration_date,
        "isMockData": is_mock_data,
        "createdAt": now,
        "updatedAt": now,
    }


def _record_new_events(camera_id: str, pipeline: TrafficMonitoringPipeline) -> None:
    context = pipeline.last_context
    if context is None:
        return

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
                track=track,
                context_time=timestamp,
                violation=violation,
                frame=pipeline.last_frame,
            )
            clip_url = _save_violation_clip(
                camera_id=camera_id,
                track=track,
                context_time=timestamp,
                violation=violation,
            )
            owner_snapshot = _owner_snapshot(
                camera_id=camera_id,
                track=track,
                seed=f"{camera_id}:{track_id}:{timestamp}:{violation}",
            )
            event_payload = {
                "camera": camera_id,
                "time": timestamp,
                "track_id": track_id,
                "vehicle": track.label_name,
                "vehicle_type": str(track.metadata.get("owner_vehicle_type") or track.label_name),
                "plate": track.plate_text,
                "owner_name": owner_snapshot["owner_name"],
                "address": owner_snapshot["owner_address"],
                "violation": violation,
                "image": image_path,
                "video": clip_url,
                "location": _camera_location(camera_id),
                "location_link": _camera_location_link(camera_id),
                "storage_provider": object_storage.provider,
                "is_mock_data": owner_snapshot["is_mock_data"],
            }
            events.append(event_payload)
            repository.ingest_violation_event(
                _build_violation_record(
                    camera_id=camera_id,
                    track=track,
                    timestamp_seconds=timestamp,
                    violation_code=violation,
                    image_path=image_path,
                    clip_url=clip_url,
                ),
                source_event_key=f"{camera_id}:{timestamp}:{track_id}:{violation}",
            )


def mjpeg_frame_generator(camera_id: str) -> Iterator[bytes]:
    source, config = _camera_config(camera_id)
    pipeline = TrafficMonitoringPipeline(config)
    for frame in pipeline.frame_generator(source):
        _remember_frame(camera_id, pipeline)
        _record_new_events(camera_id, pipeline)
        _update_intersection_state(camera_id, pipeline)
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            continue
        payload = encoded.tobytes()
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + payload + b"\r\n"


@app.get("/video_feed")
def video_feed() -> StreamingResponse:
    _refresh_camera_inventory()
    if not cameras:
        raise HTTPException(status_code=404, detail="No surveillance videos found")
    return StreamingResponse(
        mjpeg_frame_generator(next(iter(cameras))),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/camera/{camera_id}/stream")
def camera_stream(camera_id: str) -> StreamingResponse:
    _refresh_camera_inventory()
    return StreamingResponse(
        mjpeg_frame_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/surveillance/feeds")
def surveillance_feeds() -> JSONResponse:
    _refresh_camera_inventory()
    return JSONResponse(repository.list_surveillance_feeds())


@app.get("/vehicle/{plate}")
def vehicle_lookup(plate: str) -> JSONResponse:
    return JSONResponse(vehicle_registry.api_response(plate))


@app.get("/events")
def list_events() -> JSONResponse:
    return JSONResponse(events)


@app.get("/cameras")
def list_cameras() -> JSONResponse:
    _refresh_camera_inventory()
    return JSONResponse(repository.list_cameras())


@app.get("/admin/cameras")
def list_camera_configs() -> JSONResponse:
    _refresh_camera_inventory()
    return JSONResponse(repository.list_cameras())


@app.patch("/admin/cameras/{camera_id}")
def update_camera_config(camera_id: str, update: CameraConfigUpdate) -> JSONResponse:
    _refresh_camera_inventory()

    camera = repository.update_camera_config(
        camera_id,
        system_mode=update.system_mode,
        location=update.location,
    )
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Unknown camera: {camera_id}")
    if camera_id in cameras:
        cameras[camera_id]["location"] = camera["location"]
        cameras[camera_id]["status"] = camera["status"]
        cameras[camera_id]["system_mode"] = camera["system_mode"]
        cameras[camera_id]["source"] = camera["source"]
        cameras[camera_id]["location_link"] = camera["location_link"]
    return JSONResponse(camera)


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
