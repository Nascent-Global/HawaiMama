from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    fps: float
    width: int
    height: int
    frame_count: int


class VideoSource:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._capture: cv2.VideoCapture | None = None
        self._metadata: VideoMetadata | None = None

    def open(self) -> VideoMetadata:
        capture = cv2.VideoCapture(str(self.path))
        if not capture.isOpened():
            raise FileNotFoundError(f"Unable to open video input: {self.path}")

        fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if width <= 0 or height <= 0:
            capture.release()
            raise ValueError(f"Video stream has invalid resolution: {self.path}")

        self._capture = capture
        self._metadata = VideoMetadata(
            fps=fps if fps > 0 else 30.0,
            width=width,
            height=height,
            frame_count=frame_count,
        )
        return self._metadata

    @property
    def metadata(self) -> VideoMetadata:
        if self._metadata is None:
            raise RuntimeError("Video source is not opened.")
        return self._metadata

    def read(self) -> np.ndarray | None:
        if self._capture is None:
            raise RuntimeError("Video source is not opened.")
        ok, frame = self._capture.read()
        return frame if ok else None

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None


class VideoSink:
    def __init__(self, path: Path, metadata: VideoMetadata) -> None:
        self.path = path
        self.metadata = metadata
        self._writer: cv2.VideoWriter | None = None

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(
            str(self.path),
            fourcc,
            self.metadata.fps,
            (self.metadata.width, self.metadata.height),
        )
        if not writer.isOpened():
            raise RuntimeError(f"Unable to create output video: {self.path}")
        self._writer = writer

    def write(self, frame: np.ndarray) -> None:
        if self._writer is None:
            raise RuntimeError("Video sink is not opened.")
        self._writer.write(frame)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None
