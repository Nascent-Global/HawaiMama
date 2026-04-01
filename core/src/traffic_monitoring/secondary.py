from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

import numpy as np

from .detectors import InferenceDetection, YOLODetector
from .domain import BoundingBox, HelmetState, TrackState

if TYPE_CHECKING:
    from .config import TrafficMonitoringConfig


@dataclass(frozen=True, slots=True)
class HelmetCandidate:
    label: str
    confidence: float
    bbox: BoundingBox


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
                    motorcycle.set_helmet_counters(absent_frames=0, present_frames=0)
            return

        people_by_id = {track.track_id: track for track in tracks if track.label_name == "person"}
        for motorcycle in motorcycles:
            motorcycle.debug_boxes = [
                box for box in motorcycle.debug_boxes if box.get("kind") != "helmet"
            ]
            rider_boxes = [people_by_id[track_id].bbox for track_id in motorcycle.associated_person_ids if track_id in people_by_id]
            if not rider_boxes:
                motorcycle.mark_helmet_state(HelmetState.UNKNOWN)
                motorcycle.set_helmet_counters(absent_frames=0, present_frames=0)
                continue

            state, candidates = self._analyze_riders(frame, rider_boxes)
            self._update_stability(motorcycle, state)
            motorcycle.mark_helmet_state(state)
            if self.config.runtime_options.helmet_debug:
                motorcycle.debug_boxes.extend(
                    {
                        "kind": "helmet",
                        "label": candidate.label,
                        "confidence": candidate.confidence,
                        "bbox": candidate.bbox.as_tuple(),
                    }
                    for candidate in candidates
                )

    def _analyze_riders(
        self,
        frame: np.ndarray,
        rider_boxes: Sequence[BoundingBox],
    ) -> tuple[HelmetState, list[HelmetCandidate]]:
        states: list[HelmetState] = []
        candidates: list[HelmetCandidate] = []
        for rider_box in rider_boxes:
            crop = _crop(frame, rider_box)
            if crop.size == 0:
                continue
            detections = self.detector.predict(crop, verbose=False)
            top_region = _top_region(rider_box, self.config.detection.helmet_top_region_ratio)
            relevant: list[HelmetCandidate] = []
            for detection in detections:
                label = detection.class_name.lower()
                if label not in self.HELMET_LABELS and label not in self.NO_HELMET_LABELS:
                    continue
                translated_bbox = BoundingBox(*detection.xyxy).translate(rider_box.x1, rider_box.y1)
                if translated_bbox.coverage_ratio(top_region) < self.config.detection.helmet_overlap_threshold:
                    continue
                relevant.append(
                    HelmetCandidate(
                        label=label,
                        confidence=detection.confidence,
                        bbox=translated_bbox,
                    )
                )

            candidates.extend(relevant)
            if not relevant:
                states.append(HelmetState.ABSENT)
                continue

            best = max(relevant, key=lambda candidate: candidate.confidence)
            if best.label in self.HELMET_LABELS:
                states.append(HelmetState.PRESENT)
            else:
                states.append(HelmetState.ABSENT)

        if any(state == HelmetState.ABSENT for state in states):
            return HelmetState.ABSENT, candidates
        if any(state == HelmetState.PRESENT for state in states):
            return HelmetState.PRESENT, candidates
        return HelmetState.UNKNOWN, candidates

    def _update_stability(self, motorcycle: TrackState, state: HelmetState) -> None:
        absent_frames = motorcycle.helmet_stable_absent_frames
        present_frames = motorcycle.helmet_stable_present_frames
        if state == HelmetState.ABSENT:
            absent_frames += 1
            present_frames = 0
        elif state == HelmetState.PRESENT:
            present_frames += 1
            absent_frames = 0
        else:
            absent_frames = 0
            present_frames = 0
        motorcycle.set_helmet_counters(
            absent_frames=absent_frames,
            present_frames=present_frames,
        )


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


def _top_region(bbox: BoundingBox, ratio: float) -> BoundingBox:
    top_height = max(1.0, bbox.height * ratio)
    return BoundingBox(bbox.x1, bbox.y1, bbox.x2, min(bbox.y1 + top_height, bbox.y2))
