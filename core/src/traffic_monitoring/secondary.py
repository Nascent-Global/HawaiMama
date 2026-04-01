from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

import numpy as np

from .detectors import InferenceDetection, YOLODetector
from .domain import BoundingBox, HelmetState, TrackState

if TYPE_CHECKING:
    from .config import TrafficMonitoringConfig


class HelmetComplianceAnalyzer:
    """Optional analyzer for rider helmet compliance."""

    HELMET_LABELS = {"helmet", "with_helmet"}
    NO_HELMET_LABELS = {"no_helmet", "without_helmet"}

    def __init__(
        self,
        config: "TrafficMonitoringConfig",
        detector: YOLODetector | None,
    ) -> None:
        self.config = config
        self.detector = detector

    def enrich_tracks(self, frame: np.ndarray, tracks: Sequence[TrackState]) -> None:
        motorcycles = [track for track in tracks if track.label_name == "motorcycle"]
        if self.detector is None:
            for motorcycle in motorcycles:
                if motorcycle.helmet_state == HelmetState.UNKNOWN:
                    motorcycle.mark_helmet_state(HelmetState.UNKNOWN)
            return

        people_by_id = {track.track_id: track for track in tracks if track.label_name == "person"}
        for motorcycle in motorcycles:
            rider_boxes = [people_by_id[track_id].bbox for track_id in motorcycle.associated_person_ids if track_id in people_by_id]
            if not rider_boxes:
                motorcycle.mark_helmet_state(HelmetState.UNKNOWN)
                continue

            state = self._analyze_riders(frame, rider_boxes)
            motorcycle.mark_helmet_state(state)

    def _analyze_riders(
        self,
        frame: np.ndarray,
        rider_boxes: Sequence[BoundingBox],
    ) -> HelmetState:
        states: list[HelmetState] = []
        for rider_box in rider_boxes:
            crop = _crop(frame, rider_box)
            if crop.size == 0:
                continue
            detections = self.detector.predict(crop, verbose=False)
            if not detections:
                continue
            best = max(detections, key=lambda detection: detection.confidence)
            label = best.class_name.lower()
            if label in self.HELMET_LABELS:
                states.append(HelmetState.PRESENT)
            elif label in self.NO_HELMET_LABELS:
                states.append(HelmetState.ABSENT)

        if any(state == HelmetState.ABSENT for state in states):
            return HelmetState.ABSENT
        if any(state == HelmetState.PRESENT for state in states):
            return HelmetState.PRESENT
        return HelmetState.UNKNOWN


class FaceCaptureAnalyzer:
    """Optional best-effort face detector for motorbike riders."""

    def __init__(
        self,
        config: "TrafficMonitoringConfig",
        detector: YOLODetector | None,
    ) -> None:
        self.config = config
        self.detector = detector

    def enrich_tracks(self, frame: np.ndarray, tracks: Sequence[TrackState]) -> None:
        if self.detector is None or not self.config.face_capture.enabled:
            return

        people_by_id = {track.track_id: track for track in tracks if track.label_name == "person"}
        for motorcycle in (track for track in tracks if track.label_name == "motorcycle"):
            best_detection: InferenceDetection | None = None
            best_bbox: BoundingBox | None = None
            for person_id in motorcycle.associated_person_ids:
                rider = people_by_id.get(person_id)
                if rider is None:
                    continue
                crop = _crop(frame, rider.bbox)
                if crop.size == 0:
                    continue
                detections = self.detector.predict(crop, verbose=False)
                if not detections:
                    continue
                detection = max(detections, key=lambda item: item.confidence)
                if best_detection is not None and detection.confidence <= best_detection.confidence:
                    continue
                translated = BoundingBox(*detection.xyxy).translate(rider.bbox.x1, rider.bbox.y1)
                best_detection = detection
                best_bbox = translated

            if best_detection is None or best_bbox is None:
                continue
            if best_detection.confidence < self.config.face_capture.minimum_confidence:
                continue
            motorcycle.mark_face(best_bbox, best_detection.confidence)


def _crop(frame: np.ndarray, bbox: BoundingBox) -> np.ndarray:
    clamped = bbox.clamp(frame.shape[1], frame.shape[0])
    x1, y1, x2, y2 = (int(value) for value in clamped.as_tuple())
    if x2 <= x1 or y2 <= y1:
        return np.empty((0, 0, 3), dtype=frame.dtype)
    return frame[y1:y2, x1:x2].copy()
