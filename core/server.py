from __future__ import annotations

from dataclasses import replace
from collections.abc import Iterator

import cv2
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from traffic_monitoring.config import TrafficMonitoringConfig, build_default_config
from traffic_monitoring.pipeline import TrafficMonitoringPipeline
from traffic_monitoring.violations import ViolationCode


app = FastAPI(title="Traffic Monitoring Stream Server")

cameras = {
    "cam1": "input.mp4",
    "cam2": "input2.mp4",
}
events: list[dict[str, object]] = []
_seen_event_keys: set[tuple[str, float, int, str]] = set()
_api_event_codes = {
    ViolationCode.OVERSPEED.value,
    ViolationCode.NO_HELMET.value,
    ViolationCode.PLATE_UNREADABLE.value,
}


def _camera_config(camera_id: str) -> tuple[str, TrafficMonitoringConfig]:
    source = cameras.get(camera_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Unknown camera: {camera_id}")

    config = build_default_config()
    stream_output_dir = config.runtime.output_dir / camera_id
    runtime = replace(
        config.runtime,
        output_dir=stream_output_dir,
        snapshots_dir=stream_output_dir / "snapshots",
        records_path=stream_output_dir / config.output.violations_filename,
    )
    return source, replace(config, runtime=runtime)


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
            events.append(
                {
                    "camera": camera_id,
                    "time": timestamp,
                    "track_id": track_id,
                    "vehicle": track.label_name,
                    "plate": track.plate_text,
                    "violation": violation,
                }
            )


def mjpeg_frame_generator(camera_id: str) -> Iterator[bytes]:
    source, config = _camera_config(camera_id)
    pipeline = TrafficMonitoringPipeline(config)
    for frame in pipeline.frame_generator(source):
        _record_new_events(camera_id, pipeline)
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


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
