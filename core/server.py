from __future__ import annotations

from collections.abc import Iterator

import cv2
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from traffic_monitoring.config import build_default_config
from traffic_monitoring.pipeline import frame_generator


app = FastAPI(title="Traffic Monitoring Stream Server")


def mjpeg_frame_generator() -> Iterator[bytes]:
    config = build_default_config()
    for frame in frame_generator(config.runtime.input_video, config=config):
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
        mjpeg_frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
