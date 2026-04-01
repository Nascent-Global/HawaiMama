from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

try:
    from easyocr import Reader
except ImportError:  # pragma: no cover - import guard
    Reader = None  # type: ignore[assignment]

try:
    from ultralytics import YOLO
except ImportError:  # pragma: no cover - import guard
    YOLO = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class InferenceDetection:
    xyxy: tuple[float, float, float, float]
    confidence: float
    class_id: int
    class_name: str
    track_id: int | None = None


@dataclass(frozen=True, slots=True)
class OCRCandidate:
    text: str
    confidence: float


class YOLODetector:
    def __init__(self, model_path: str | Path, *, confidence: float) -> None:
        if YOLO is None:
            raise RuntimeError("ultralytics is not installed. Run `uv sync` first.")
        self.model_path = str(model_path)
        self.confidence = confidence
        self.model = YOLO(self.model_path, task="detect")

    def track(
        self,
        frame: np.ndarray,
        *,
        classes: Iterable[int] | None = None,
        tracker: str | None = None,
        persist: bool = True,
        verbose: bool = False,
    ) -> list[InferenceDetection]:
        results = self.model.track(
            frame,
            conf=self.confidence,
            classes=list(classes) if classes is not None else None,
            tracker=tracker,
            persist=persist,
            verbose=verbose,
        )
        return _parse_yolo_results(results)

    def predict(
        self,
        frame: np.ndarray,
        *,
        classes: Iterable[int] | None = None,
        verbose: bool = False,
    ) -> list[InferenceDetection]:
        results = self.model.predict(
            frame,
            conf=self.confidence,
            classes=list(classes) if classes is not None else None,
            verbose=verbose,
        )
        return _parse_yolo_results(results)


class EasyOCRReader:
    def __init__(self, languages: list[str]) -> None:
        if Reader is None:
            raise RuntimeError("easyocr is not installed. Run `uv sync` first.")
        self.reader = Reader(languages, gpu=False)

    def read(self, image: np.ndarray) -> list[OCRCandidate]:
        candidates = self.reader.readtext(image, detail=1)
        parsed: list[OCRCandidate] = []
        for _, text, confidence in candidates:
            cleaned = text.strip()
            if not cleaned:
                continue
            parsed.append(OCRCandidate(text=cleaned, confidence=float(confidence)))
        return parsed


def _parse_yolo_results(results: object) -> list[InferenceDetection]:
    parsed: list[InferenceDetection] = []
    if not results:
        return parsed

    for result in results:
        names = getattr(result, "names", {}) or {}
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            continue
        xyxy_tensor = getattr(boxes, "xyxy", None)
        conf_tensor = getattr(boxes, "conf", None)
        cls_tensor = getattr(boxes, "cls", None)
        ids_tensor = getattr(boxes, "id", None)
        if xyxy_tensor is None or conf_tensor is None or cls_tensor is None:
            continue

        xyxy_array = xyxy_tensor.cpu().numpy()
        conf_array = conf_tensor.cpu().numpy()
        cls_array = cls_tensor.cpu().numpy()
        ids_array = ids_tensor.cpu().numpy() if ids_tensor is not None else None

        for index, xyxy in enumerate(xyxy_array):
            class_id = int(cls_array[index])
            track_id = int(ids_array[index]) if ids_array is not None else None
            parsed.append(
                InferenceDetection(
                    xyxy=tuple(float(value) for value in xyxy),
                    confidence=float(conf_array[index]),
                    class_id=class_id,
                    class_name=str(names.get(class_id, class_id)),
                    track_id=track_id,
                )
            )
    return parsed
