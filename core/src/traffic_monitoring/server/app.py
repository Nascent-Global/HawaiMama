from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

import cv2
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from traffic_monitoring.config import TrafficMonitoringConfig, build_default_config
from traffic_monitoring.events import ViolationCode
from traffic_monitoring.pipeline import TrafficMonitoringPipeline
from traffic_monitoring.traffic import SignalStateMachine


app = FastAPI(title="Traffic Monitoring Stream Server")
_base_config = build_default_config()
_base_config.runtime.output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=str(_base_config.runtime.output_dir)), name="snapshots")

cameras: dict[str, dict[str, str]] = {
    "cam1": {
        "id": "cam1",
        "source": "input/input6.mp4",
        "location": "Lakeside",
        "status": "online",
        "system_mode": "traffic_management_mode",
        "intersection_id": "main_intersection",
        "lanes": ["north", "east"],
    },
    "cam2": {
        "id": "cam2",
        "source": "input/input2.mp4",
        "location": "Highway South",
        "status": "online",
        "system_mode": "traffic_management_mode",
        "intersection_id": "main_intersection",
        "lanes": ["south", "west"],
    },
}
events: list[dict[str, object]] = []
traffic_state_by_camera: dict[str, dict[str, object]] = {}
intersection_state_by_id: dict[str, dict[str, object]] = {}
_seen_event_keys: set[tuple[str, float, int, str]] = set()
_api_event_codes = {
    ViolationCode.OVERSPEED.value,
    ViolationCode.NO_HELMET.value,
    ViolationCode.PLATE_UNREADABLE.value,
}
_intersection_signal_machines: dict[str, SignalStateMachine] = {}


def _camera_config(camera_id: str) -> tuple[str, TrafficMonitoringConfig]:
    camera = cameras.get(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Unknown camera: {camera_id}")
    source = camera["source"]

    config = build_default_config()
    stream_output_dir = config.runtime.output_dir / camera_id
    runtime = replace(
        config.runtime,
        output_dir=stream_output_dir,
        snapshots_dir=stream_output_dir / "snapshots",
        records_path=stream_output_dir / config.output.violations_filename,
    )
    runtime_options = replace(
        config.runtime_options,
        system_mode=camera.get("system_mode", config.runtime_options.system_mode),
        overlay_mode=(
            "traffic_control"
            if camera.get("system_mode", config.runtime_options.system_mode) == "traffic_management_mode"
            else "monitoring"
        ),
    )
    speed = replace(
        config.speed,
        enabled=runtime_options.system_mode != "traffic_management_mode",
    )
    return source, replace(config, runtime=runtime, runtime_options=runtime_options, speed=speed)


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
    if not intersection_id:
        return
    if pipeline.last_context is None:
        return

    lane_metrics = pipeline.last_traffic_state.get("lane_metrics", {})
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
            events.append(
                {
                    "camera": camera_id,
                    "time": timestamp,
                    "track_id": track_id,
                    "vehicle": track.label_name,
                    "plate": track.plate_text,
                    "violation": violation,
                    "image": image_path,
                }
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
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + payload + b"\r\n"
        )


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


@app.get("/events")
def list_events() -> JSONResponse:
    return JSONResponse(events)


@app.get("/cameras")
def list_cameras() -> JSONResponse:
    payload = [
        {
            "id": camera["id"],
            "location": camera["location"],
            "status": camera["status"],
        }
        for camera in cameras.values()
    ]
    return JSONResponse(payload)


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
