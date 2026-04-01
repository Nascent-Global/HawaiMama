from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from statistics import mean
from typing import TYPE_CHECKING, Iterable, Mapping, Sequence

import cv2
import numpy as np

from .domain import (
    BoundingBox,
    Detection,
    FrameContext,
    HelmetState,
    PlateState,
    TrackState,
)

if TYPE_CHECKING:
    from .config import TrafficMonitoringConfig
    from .detectors import EasyOCRReader, InferenceDetection, YOLODetector


@dataclass(frozen=True, slots=True)
class TrackMatch:
    """Result of matching one track or detection to another."""

    primary_track_id: int
    secondary_track_id: int
    score: float
    overlap_ratio: float
    center_distance: float


@dataclass(slots=True)
class AssociationSet:
    """All matches from a single association pass."""

    matches: dict[int, list[TrackMatch]] = field(default_factory=dict)

    def add(self, match: TrackMatch) -> None:
        self.matches.setdefault(match.primary_track_id, []).append(match)

    def for_primary(self, track_id: int) -> list[TrackMatch]:
        return list(self.matches.get(track_id, ()))

    def primary_ids(self) -> list[int]:
        return sorted(self.matches)


def center_distance(left: BoundingBox, right: BoundingBox) -> float:
    return hypot(left.center[0] - right.center[0], left.center[1] - right.center[1])


def _overlap_ratio(left: BoundingBox, right: BoundingBox) -> float:
    if left.area <= 0.0 or right.area <= 0.0:
        return 0.0
    return left.intersection_area(right) / min(left.area, right.area)


def _score_match(left: BoundingBox, right: BoundingBox) -> tuple[float, float, float]:
    overlap = _overlap_ratio(left, right)
    distance = center_distance(left, right)
    scale = max(left.diagonal, right.diagonal, 1.0)
    proximity = max(0.0, 1.0 - (distance / scale))
    score = (0.65 * overlap) + (0.35 * proximity)
    return score, overlap, distance


def associate_tracks(
    primary_tracks: Sequence[TrackState],
    secondary_tracks: Sequence[TrackState],
    *,
    minimum_score: float = 0.20,
) -> AssociationSet:
    """Associate secondary tracks to primary tracks using box overlap and proximity."""

    result = AssociationSet()
    for primary in primary_tracks:
        for secondary in secondary_tracks:
            score, overlap, distance = _score_match(primary.bbox, secondary.bbox)
            if score < minimum_score:
                continue
            result.add(
                TrackMatch(
                    primary_track_id=primary.track_id,
                    secondary_track_id=secondary.track_id,
                    score=score,
                    overlap_ratio=overlap,
                    center_distance=distance,
                )
            )
    for primary_id in result.primary_ids():
        result.matches[primary_id].sort(key=lambda match: match.score, reverse=True)
    return result


def best_match_per_primary(
    primary_tracks: Sequence[TrackState],
    secondary_tracks: Sequence[TrackState],
    *,
    minimum_score: float = 0.20,
) -> dict[int, TrackMatch]:
    """Return the single best secondary track for each primary track."""

    associations = associate_tracks(
        primary_tracks, secondary_tracks, minimum_score=minimum_score
    )
    best: dict[int, TrackMatch] = {}
    for primary_id, matches in associations.matches.items():
        if matches:
            best[primary_id] = matches[0]
    return best


def associate_people_to_motorcycles(
    motorcycle_tracks: Sequence[TrackState],
    person_tracks: Sequence[TrackState],
    *,
    minimum_score: float = 0.20,
) -> AssociationSet:
    """Associate rider candidates to motorcycles.

    Many-to-one associations are allowed because a motorcycle can carry a rider and a passenger.
    """

    return associate_tracks(
        motorcycle_tracks, person_tracks, minimum_score=minimum_score
    )


def associate_plates_to_vehicles(
    vehicle_tracks: Sequence[TrackState],
    plate_tracks: Sequence[TrackState],
    *,
    minimum_score: float = 0.10,
) -> dict[int, TrackMatch]:
    """Associate the most plausible plate crop to each vehicle."""

    return best_match_per_primary(
        vehicle_tracks, plate_tracks, minimum_score=minimum_score
    )


def estimate_speed_kmh(
    previous_center: tuple[float, float],
    current_center: tuple[float, float],
    *,
    fps: float,
    pixels_per_meter: float,
    frame_interval: int = 1,
) -> float:
    """Estimate approximate speed in km/h using pixel displacement."""

    if fps <= 0.0 or pixels_per_meter <= 0.0 or frame_interval <= 0:
        return 0.0
    displacement_px = hypot(
        current_center[0] - previous_center[0],
        current_center[1] - previous_center[1],
    )
    meters_moved = displacement_px / pixels_per_meter
    seconds = frame_interval / fps
    if seconds <= 0.0:
        return 0.0
    meters_per_second = meters_moved / seconds
    return meters_per_second * 3.6


def smooth_speed_kmh(samples: Iterable[float], *, window: int = 5) -> float | None:
    values = [sample for sample in samples if sample is not None]
    if not values:
        return None
    return mean(values[-window:])


def update_track_speed(
    track: TrackState,
    *,
    fps: float,
    pixels_per_meter: float,
    frame_interval: int = 1,
    smoothing_window: int = 5,
    minimum_pixel_distance: float = 0.0,
    direction_consistency_window: int = 4,
    spike_ratio_threshold: float = 2.0,
    max_speed_kmh: float | None = None,
) -> float | None:
    """Update a track's speed estimate from its motion history."""

    if len(track.center_history) < 2:
        return track.estimated_speed_kmh

    previous_center = track.center_history[-2]
    current_center = track.center_history[-1]
    displacement_px = hypot(
        current_center[0] - previous_center[0],
        current_center[1] - previous_center[1],
    )
    track.record_displacement(displacement_px)
    if displacement_px < minimum_pixel_distance:
        return track.estimated_speed_kmh
    if not _movement_is_consistent(track, window=direction_consistency_window):
        return track.estimated_speed_kmh
    speed = estimate_speed_kmh(
        previous_center,
        current_center,
        fps=fps,
        pixels_per_meter=pixels_per_meter,
        frame_interval=frame_interval,
    )
    if max_speed_kmh is not None and speed > max_speed_kmh:
        return track.estimated_speed_kmh
    previous_speed = track.estimated_speed_kmh
    if (
        previous_speed is not None
        and previous_speed > 0.0
        and speed > previous_speed * spike_ratio_threshold
    ):
        return track.estimated_speed_kmh
    track.record_speed(speed)
    track.estimated_speed_kmh = smooth_speed_kmh(
        track.speed_history_kmh, window=smoothing_window
    )
    return track.estimated_speed_kmh


def _movement_is_consistent(track: TrackState, *, window: int) -> bool:
    if len(track.center_history) < window:
        return True

    recent_centers = list(track.center_history)[-window:]
    vectors: list[tuple[float, float]] = []
    for previous, current in zip(recent_centers, recent_centers[1:]):
        dx = current[0] - previous[0]
        dy = current[1] - previous[1]
        magnitude = hypot(dx, dy)
        if magnitude == 0.0:
            continue
        vectors.append((dx / magnitude, dy / magnitude))

    if len(vectors) < 2:
        return True

    base_x, base_y = vectors[0]
    for vx, vy in vectors[1:]:
        cosine_similarity = (base_x * vx) + (base_y * vy)
        if cosine_similarity < 0.5:
            return False
    return True


def refresh_tracks(
    tracks: Mapping[int, TrackState],
    current_frame_index: int,
    *,
    max_age_frames: int,
) -> dict[int, TrackState]:
    """Return a copy of tracks with stale entries removed."""

    refreshed: dict[int, TrackState] = {}
    for track_id, track in tracks.items():
        if track.age_in_frames(current_frame_index) <= max_age_frames:
            refreshed[track_id] = track
    return refreshed


def update_track_from_detection(
    track: TrackState,
    detection: Detection,
    *,
    frame_index: int,
) -> TrackState:
    """Update a track in place from a new detection and return it for chaining."""

    track.update_from_detection(detection, frame_index)
    track.last_seen_frame = frame_index
    return track


class TrackManager:
    """Create and update per-object state from tracked detections."""

    def __init__(self, config: "TrafficMonitoringConfig") -> None:
        self.config = config
        self._tracks: dict[int, TrackState] = {}

    def update(
        self,
        context: FrameContext,
        detections: Sequence["InferenceDetection"],
    ) -> list[TrackState]:
        updated_ids: set[int] = set()
        for detection in detections:
            if detection.track_id is None:
                continue
            normalized = Detection(
                label=detection.class_name,
                confidence=detection.confidence,
                bbox=BoundingBox(*detection.xyxy),
                track_id=detection.track_id,
                frame_index=context.frame_index,
            )
            if normalized.normalized_label() not in self.config.detection.tracked_classes:
                continue
            track = self._tracks.get(normalized.track_id)
            if track is None:
                track = TrackState(
                    track_id=normalized.track_id,
                    label=normalized.label,
                    bbox=normalized.bbox,
                    confidence=normalized.confidence,
                    first_seen_frame=context.frame_index,
                    last_seen_frame=context.frame_index,
                )
                self._tracks[track.track_id] = track
            else:
                update_track_from_detection(
                    track,
                    normalized,
                    frame_index=context.frame_index,
                )

            if (
                track.label_name != "person"
                and len(track.center_history) >= self.config.speed.minimum_history
            ):
                pixels_per_meter = max(1e-6, 1.0 / self.config.speed.meters_per_pixel)
                update_track_speed(
                    track,
                    fps=context.fps,
                    pixels_per_meter=pixels_per_meter,
                    smoothing_window=self.config.speed.smoothing_window,
                    minimum_pixel_distance=self.config.speed.minimum_pixel_distance,
                    direction_consistency_window=self.config.speed.direction_consistency_window,
                    spike_ratio_threshold=self.config.speed.spike_ratio_threshold,
                    max_speed_kmh=self.config.speed.max_reasonable_speed_kmh,
                )
            updated_ids.add(track.track_id)

        self._tracks = refresh_tracks(
            self._tracks,
            context.frame_index,
            max_age_frames=self.config.tracking.max_age_frames,
        )
        return sorted(self._tracks.values(), key=lambda track: track.track_id)


class RiderAssociationEngine:
    def __init__(self, config: "TrafficMonitoringConfig") -> None:
        self.config = config

    def assign_riders(self, tracks: Sequence[TrackState]) -> None:
        motorcycles = [track for track in tracks if track.label_name == "motorcycle"]
        persons = [track for track in tracks if track.label_name == "person"]

        for motorcycle in motorcycles:
            motorcycle.associated_person_ids.clear()

        associations = associate_people_to_motorcycles(
            motorcycles,
            persons,
            minimum_score=self.config.detection.minimum_association_iou,
        )
        for motorcycle in motorcycles:
            for match in associations.for_primary(motorcycle.track_id):
                if match.center_distance > (
                    motorcycle.bbox.diagonal * self.config.detection.minimum_rider_distance_ratio
                ):
                    continue
                motorcycle.attach_person(match.secondary_track_id)


class PlateRecognizer:
    def __init__(
        self,
        config: "TrafficMonitoringConfig",
        detector: "YOLODetector | None",
        ocr_reader: "EasyOCRReader | None",
    ) -> None:
        self.config = config
        self.detector = detector
        self.ocr_reader = ocr_reader

    def enrich_tracks(self, frame: np.ndarray, tracks: Sequence[TrackState]) -> None:
        vehicle_tracks = [track for track in tracks if track.label_name != "person"]
        if self.detector is None:
            for track in vehicle_tracks:
                if track.plate_text:
                    continue
                track.mark_plate(text=None, confidence=None, state=PlateState.UNKNOWN, bbox=None)
            return

        for track in vehicle_tracks:
            self._enrich_track(frame, track)

    def _enrich_track(self, frame: np.ndarray, track: TrackState) -> None:
        crop, origin = self._crop(frame, track.bbox)
        if crop.size == 0:
            track.mark_plate(text=None, confidence=None, state=PlateState.MISSING, bbox=None)
            return

        detections = self.detector.predict(crop, verbose=False)
        if not detections:
            if track.plate_text is None:
                track.mark_plate(text=None, confidence=None, state=PlateState.MISSING, bbox=None)
            return

        best = max(detections, key=lambda detection: detection.confidence)
        translated_bbox = BoundingBox(*best.xyxy).translate(origin[0], origin[1])
        plate_crop, _ = self._crop(frame, translated_bbox)
        text, confidence = self._read_plate_text(plate_crop)
        if text:
            current_conf = track.plate_confidence or 0.0
            if confidence >= current_conf:
                track.mark_plate(
                    text=text,
                    confidence=confidence,
                    state=PlateState.READABLE,
                    bbox=translated_bbox,
                )
            return
        track.mark_plate(
            text=None if track.plate_text is None else track.plate_text,
            confidence=confidence,
            state=PlateState.UNREADABLE,
            bbox=translated_bbox,
        )

    def _read_plate_text(self, image: np.ndarray) -> tuple[str | None, float | None]:
        if self.ocr_reader is None or image.size == 0:
            return None, None
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        scaled = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        candidates = self.ocr_reader.read(scaled)
        if not candidates:
            return None, None
        best = max(candidates, key=lambda candidate: candidate.confidence)
        normalized = "".join(character for character in best.text.upper() if character.isalnum())
        if not normalized or best.confidence < self.config.ocr.minimum_confidence:
            return None, best.confidence
        return normalized, best.confidence

    def _crop(
        self,
        frame: np.ndarray,
        bbox: BoundingBox,
    ) -> tuple[np.ndarray, tuple[int, int]]:
        clamped = bbox.clamp(frame.shape[1], frame.shape[0])
        x1, y1, x2, y2 = (int(value) for value in clamped.as_tuple())
        if x2 <= x1 or y2 <= y1:
            return np.empty((0, 0, 3), dtype=frame.dtype), (x1, y1)
        return frame[y1:y2, x1:x2].copy(), (x1, y1)
