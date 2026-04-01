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
    def __init__(self, source: Path | str | cv2.VideoCapture) -> None:
        self.source = source
        self._capture: cv2.VideoCapture | None = None
        self._metadata: VideoMetadata | None = None
        self._owns_capture = True

    def open(self) -> VideoMetadata:
        if isinstance(self.source, cv2.VideoCapture):
            capture = self.source
            self._owns_capture = False
        else:
            capture = cv2.VideoCapture(str(self.source))
            self._owns_capture = True
        if not capture.isOpened():
            raise FileNotFoundError(f"Unable to open video input: {self.source}")

        fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if width <= 0 or height <= 0:
            if self._owns_capture:
                capture.release()
            raise ValueError(f"Video stream has invalid resolution: {self.source}")

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
            if self._owns_capture:
                self._capture.release()
            self._capture = None
