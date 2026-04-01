from __future__ import annotations

from dataclasses import replace
from collections.abc import Iterator

import cv2
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from traffic_monitoring.config import TrafficMonitoringConfig, build_default_config
from traffic_monitoring.pipeline import frame_generator


app = FastAPI(title="Traffic Monitoring Stream Server")

cameras = {
    "cam1": "input.mp4",
    "cam2": "input2.mp4",
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


def mjpeg_frame_generator(camera_id: str) -> Iterator[bytes]:
    source, config = _camera_config(camera_id)
    for frame in frame_generator(source, config=config):
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


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
