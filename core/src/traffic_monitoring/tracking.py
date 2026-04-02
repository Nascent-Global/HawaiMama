from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from math import hypot
import unicodedata
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


def update_track_line_crossing_speed(
    track: TrackState,
    *,
    context: FrameContext,
    line1_y: float,
    line2_y: float,
    line_distance_meters: float,
    line_tolerance_pixels: int,
    max_speed_kmh: float | None = None,
) -> float | None:
    """Measure speed once using the time between two horizontal reference lines."""

    if track.speed_measured or len(track.bbox_history) < 2:
        return track.estimated_speed_kmh

    previous_box = track.bbox_history[-2]
    current_box = track.bbox_history[-1]
    previous_y_px = previous_box.y2
    current_y_px = current_box.y2
    delta_y = current_y_px - previous_y_px
    track.motion_direction = "downward" if delta_y > 0 else "upward"

    line1_y_px = line1_y * context.height
    line2_y_px = line2_y * context.height
    tolerance = float(line_tolerance_pixels)

    line1_crossed = _crossed_line(
        previous_y_px,
        current_y_px,
        line1_y_px,
        tolerance,
        direction=track.motion_direction,
    )
    line2_crossed = _crossed_line(
        previous_y_px,
        current_y_px,
        line2_y_px,
        tolerance,
        direction=track.motion_direction,
    )

    if track.motion_direction == "downward":
        first_line_name = "line1"
        second_line_name = "line2"
        skipped_both = previous_y_px < (line1_y_px - tolerance) and current_y_px > (line2_y_px + tolerance)
    else:
        first_line_name = "line2"
        second_line_name = "line1"
        skipped_both = previous_y_px > (line2_y_px + tolerance) and current_y_px < (line1_y_px - tolerance)

    if skipped_both:
        line1_crossed = True
        line2_crossed = True

    if not track.line1_crossed and line1_crossed:
        track.line1_crossed = True
        track.line1_crossed_at_seconds = context.timestamp_seconds
        print(f"Track {track.track_id} crossed line1 at t={context.timestamp_seconds:.3f}")

    if not track.line2_crossed and line2_crossed:
        track.line2_crossed = True
        track.line2_crossed_at_seconds = context.timestamp_seconds
        print(f"Track {track.track_id} crossed line2 at t={context.timestamp_seconds:.3f}")

    if track.first_line_crossed is None:
        if first_line_name == "line1" and line1_crossed:
            track.first_line_crossed = "line1"
        elif first_line_name == "line2" and line2_crossed:
            track.first_line_crossed = "line2"

    if track.first_line_crossed is not None and track.second_line_crossed is None:
        if second_line_name == "line1" and line1_crossed:
            track.second_line_crossed = "line1"
        elif second_line_name == "line2" and line2_crossed:
            track.second_line_crossed = "line2"

    if not track.line1_crossed or not track.line2_crossed:
        return track.estimated_speed_kmh

    if track.line1_crossed_at_seconds is None or track.line2_crossed_at_seconds is None:
        return track.estimated_speed_kmh

    if track.motion_direction == "upward":
        start_time = track.line2_crossed_at_seconds
        end_time = track.line1_crossed_at_seconds
    else:
        start_time = track.line1_crossed_at_seconds
        end_time = track.line2_crossed_at_seconds

    time_seconds = end_time - start_time
    if time_seconds <= 0.0:
        return track.estimated_speed_kmh

    speed_kmh = (line_distance_meters / time_seconds) * 3.6
    if max_speed_kmh is not None and speed_kmh > max_speed_kmh:
        track.speed_measured = True
        return track.estimated_speed_kmh

    track.record_speed(speed_kmh)
    track.speed_measured = True
    track.metadata["lane"] = "left" if track.latest_center[0] < (context.width / 2.0) else "right"
    return track.estimated_speed_kmh


def _crossed_line(
    previous_y_px: float,
    current_y_px: float,
    line_y_px: float,
    tolerance: float,
    *,
    direction: str,
) -> bool:
    lower = line_y_px - tolerance
    upper = line_y_px + tolerance
    if direction == "downward":
        return previous_y_px < lower and current_y_px >= lower
    return previous_y_px > upper and current_y_px <= upper


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
                and self.config.speed.enabled
            ):
                update_track_line_crossing_speed(
                    track,
                    context=context,
                    line1_y=self.config.speed.line1_y,
                    line2_y=self.config.speed.line2_y,
                    line_distance_meters=self.config.speed.line_distance_meters,
                    line_tolerance_pixels=self.config.speed.line_tolerance_pixels,
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
        char_detector: "YOLODetector | None" = None,
    ) -> None:
        self.config = config
        self.detector = detector
        self.ocr_reader = ocr_reader
        self.char_detector = char_detector

    def _debug(self, message: str) -> None:
        if self.config.runtime_options.ocr_debug:
            print(message)

    def enrich_tracks(self, frame: np.ndarray, tracks: Sequence[TrackState]) -> None:
        vehicle_tracks = [track for track in tracks if track.label_name != "person"]
        if self.detector is None:
            for track in vehicle_tracks:
                if track.plate_text:
                    continue
                track.mark_plate(text=None, confidence=None, state=PlateState.UNKNOWN, bbox=None)
            return

        for track in vehicle_tracks:
            self.handle_plate(track, frame)

    def handle_plate(self, track: TrackState, frame: np.ndarray) -> None:
        self._enrich_track(frame, track)

    def _enrich_track(self, frame: np.ndarray, track: TrackState) -> None:
        if self._can_skip_plate_ocr(track):
            return
        track.metadata["plate_last_attempt_frame"] = track.last_seen_frame
        self._debug(
            f"[plate-ocr] trigger track={track.track_id} frame={track.last_seen_frame}"
        )

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
            smoothed_text = self._update_plate_history(track, text)
            best_confidence = max(confidence or 0.0, track.plate_confidence or 0.0)
            track.mark_plate(
                text=smoothed_text,
                confidence=best_confidence,
                state=PlateState.READABLE,
                bbox=translated_bbox,
            )
            track.metadata["plate_last_success_frame"] = track.last_seen_frame
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
        plate_format = self._detect_plate_format(image)
        self._debug(f"[plate-ocr] plate format: {plate_format}")

        if plate_format == "traditional":
            top_region, bottom_region = self._split_plate_regions(image)
            top_text, top_conf = self._read_top_plate_text(top_region)
            bottom_digits, bottom_conf = self._read_bottom_plate_digits(bottom_region)
            confidence_values = [value for value in (top_conf, bottom_conf) if value is not None]
            mean_confidence = (
                sum(confidence_values) / len(confidence_values) if confidence_values else None
            )
            self._debug(f"[plate-ocr] structured top: {top_text!r}")
            self._debug(f"[plate-ocr] structured bottom: {bottom_digits!r}")
            if bottom_digits:
                return bottom_digits, mean_confidence
        else:
            modern_text, modern_conf = self._read_modern_plate_text(image)
            if modern_text:
                return modern_text, modern_conf

        if plate_format == "traditional":
            segmented_text, segmented_conf = self._read_segmented_plate_text(image)
            if segmented_text:
                return segmented_text, segmented_conf
        return self._read_full_plate_text(image)

    def _detect_plate_format(self, image: np.ndarray) -> str:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        saturation = hsv[:, :, 1]
        value = hsv[:, :, 2]
        red_mask_1 = cv2.inRange(hsv, (0, 60, 40), (15, 255, 255))
        red_mask_2 = cv2.inRange(hsv, (160, 60, 40), (180, 255, 255))
        red_mask = cv2.bitwise_or(red_mask_1, red_mask_2)
        white_mask = cv2.inRange(hsv, (0, 0, 130), (180, 80, 255))

        red_ratio = float(cv2.countNonZero(red_mask)) / max(1, image.shape[0] * image.shape[1])
        white_ratio = float(cv2.countNonZero(white_mask)) / max(1, image.shape[0] * image.shape[1])
        if red_ratio > white_ratio:
            return "traditional"
        return "modern"

    def _split_plate_regions(self, image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        height = image.shape[0]
        split_y = max(1, min(height - 1, int(height * 0.40)))
        top_region = image[:split_y, :].copy()
        bottom_region = image[split_y:, :].copy()
        return top_region, bottom_region

    def _read_top_plate_text(self, image: np.ndarray) -> tuple[str | None, float | None]:
        if image.size == 0:
            return None, None
        candidates = self._ocr_variants(image)
        if not candidates:
            return None, None
        best = max(candidates, key=lambda candidate: candidate.confidence)
        normalized = self._normalize_traditional_top_text(best.text)
        self._debug(f"[plate-ocr] raw top: {best.text!r}")
        self._debug(f"[plate-ocr] cleaned top: {normalized!r}")
        if not normalized or best.confidence < self.config.ocr.minimum_confidence:
            return None, best.confidence
        return normalized, best.confidence

    def _read_bottom_plate_digits(self, image: np.ndarray) -> tuple[str | None, float | None]:
        if image.size == 0:
            return None, None
        segmented_text, segmented_conf = self._read_segmented_plate_digits(image)
        if segmented_text:
            return segmented_text, segmented_conf

        candidates = self._ocr_variants(image)
        if not candidates:
            return None, None
        best = max(candidates, key=lambda candidate: candidate.confidence)
        normalized = self._normalize_bottom_digits(best.text)
        self._debug(f"[plate-ocr] raw bottom: {best.text!r}")
        self._debug(f"[plate-ocr] cleaned bottom: {normalized!r}")
        if not normalized or best.confidence < self.config.ocr.minimum_confidence:
            return None, best.confidence
        return normalized, best.confidence

    def _read_modern_plate_text(self, image: np.ndarray) -> tuple[str | None, float | None]:
        focus_region = self._crop_modern_plate_center(image)
        candidates = self._ocr_variants(focus_region)
        if not candidates:
            return None, None
        best = max(candidates, key=lambda candidate: candidate.confidence)
        normalized = self._normalize_modern_plate_text(best.text)
        self._debug(f"[plate-ocr] raw modern full: {best.text!r}")
        self._debug(f"[plate-ocr] cleaned modern full: {normalized!r}")
        if (
            not normalized
            or len(normalized) < 4
            or best.confidence < self.config.ocr.minimum_confidence
        ):
            return None, best.confidence
        return normalized, best.confidence

    def _crop_modern_plate_center(self, image: np.ndarray) -> np.ndarray:
        height, width = image.shape[:2]
        x1 = max(0, int(width * 0.18))
        x2 = min(width, int(width * 0.95))
        y1 = max(0, int(height * 0.22))
        y2 = min(height, int(height * 0.92))
        if x2 <= x1 or y2 <= y1:
            return image
        return image[y1:y2, x1:x2].copy()

    def _read_segmented_plate_digits(self, image: np.ndarray) -> tuple[str | None, float | None]:
        if self.char_detector is None:
            return None, None
        detections = self.char_detector.predict(image, verbose=False)
        if not detections:
            return None, None

        filtered = self._filter_character_detections(image, detections)
        self._debug(f"[plate-ocr] bottom char boxes before filtering: {len(detections)}")
        self._debug(f"[plate-ocr] bottom char boxes after filtering: {len(filtered)}")
        if not filtered:
            return None, None

        ordered = sorted(filtered, key=lambda detection: detection.xyxy[0])[:10]
        digits: list[str] = []
        confidences: list[float] = []
        for detection in ordered:
            char_bbox = BoundingBox(*detection.xyxy)
            char_crop, _ = self._crop(image, char_bbox)
            if char_crop.size == 0:
                continue
            text, confidence = self._read_single_character(char_crop)
            if not text:
                continue
            normalized_digit = self._normalize_bottom_digits(text)
            if not normalized_digit:
                continue
            digits.append(normalized_digit[0])
            confidences.append(confidence or 0.0)

        assembled = self._normalize_bottom_digits("".join(digits))
        self._debug(f"[plate-ocr] raw bottom segmented: {''.join(digits)!r}")
        self._debug(f"[plate-ocr] cleaned bottom segmented: {assembled!r}")
        if not assembled:
            return None, None
        mean_confidence = sum(confidences) / len(confidences) if confidences else None
        if mean_confidence is not None and mean_confidence < self.config.ocr.minimum_confidence:
            return None, mean_confidence
        return assembled, mean_confidence

    def _read_segmented_plate_text(self, image: np.ndarray) -> tuple[str | None, float | None]:
        if self.char_detector is None:
            return None, None
        detections = self.char_detector.predict(image, verbose=False)
        if not detections:
            return None, None

        filtered = self._filter_character_detections(image, detections)
        self._debug(f"[plate-ocr] char boxes before filtering: {len(detections)}")
        self._debug(f"[plate-ocr] char boxes after filtering: {len(filtered)}")
        if not filtered:
            return None, None

        ordered = sorted(filtered, key=lambda detection: detection.xyxy[0])[:10]
        characters: list[str] = []
        confidences: list[float] = []
        for detection in ordered:
            char_bbox = BoundingBox(*detection.xyxy)
            char_crop, _ = self._crop(image, char_bbox)
            if char_crop.size == 0:
                continue
            text, confidence = self._read_single_character(char_crop)
            if not text:
                continue
            characters.append(text[0])
            confidences.append(confidence or 0.0)

        assembled = self._postprocess_segmented_text("".join(characters))
        normalized = self._normalize_plate_text(assembled)
        self._debug(f"[plate-ocr] raw segmented: {assembled!r}")
        self._debug(f"[plate-ocr] cleaned segmented: {normalized!r}")
        if not normalized:
            return None, None
        mean_confidence = sum(confidences) / len(confidences) if confidences else None
        if mean_confidence is not None and mean_confidence < self.config.ocr.minimum_confidence:
            return None, mean_confidence
        return normalized, mean_confidence

    def _read_single_character(self, image: np.ndarray) -> tuple[str | None, float | None]:
        candidates = self._ocr_variants(image)
        if not candidates:
            return None, None
        best = max(candidates, key=lambda candidate: candidate.confidence)
        normalized = self._normalize_plate_text(best.text)
        self._debug(f"[plate-ocr] raw char: {best.text!r}")
        self._debug(f"[plate-ocr] cleaned char: {normalized!r}")
        if not normalized or best.confidence < self.config.ocr.minimum_confidence:
            return None, best.confidence
        return normalized[0], best.confidence

    def _read_full_plate_text(self, image: np.ndarray) -> tuple[str | None, float | None]:
        candidates = self._ocr_variants(image)
        if not candidates:
            return None, None
        best = max(candidates, key=lambda candidate: candidate.confidence)
        normalized = self._normalize_plate_text(best.text)
        self._debug(f"[plate-ocr] raw full: {best.text!r}")
        self._debug(f"[plate-ocr] cleaned full: {normalized!r}")
        if not normalized or best.confidence < self.config.ocr.minimum_confidence:
            return None, best.confidence
        return normalized, best.confidence

    def _filter_character_detections(self, image: np.ndarray, detections):
        plate_height, plate_width = image.shape[:2]
        min_width = max(3.0, plate_width * 0.02)
        max_width = max(min_width, plate_width * 0.35)
        min_height = max(8.0, plate_height * 0.18)
        max_height = plate_height * 0.98

        filtered = []
        for detection in detections:
            if detection.confidence < self.config.detection.char_confidence_threshold:
                continue
            x1, y1, x2, y2 = detection.xyxy
            width = x2 - x1
            height = y2 - y1
            if width < min_width or width > max_width:
                continue
            if height < min_height or height > max_height:
                continue
            aspect_ratio = width / max(height, 1.0)
            if aspect_ratio < 0.08 or aspect_ratio > 1.2:
                continue
            filtered.append(detection)

        filtered.sort(key=lambda detection: (detection.confidence, -(detection.xyxy[2] - detection.xyxy[0])), reverse=True)
        return filtered[:10]

    def _ocr_variants(self, image: np.ndarray):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        scaled = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        equalized = cv2.equalizeHist(scaled)
        _, thresholded = cv2.threshold(equalized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        candidates = []
        for variant in (scaled, equalized, thresholded):
            candidates.extend(self.ocr_reader.read(variant))
        return candidates

    def _normalize_plate_text(self, text: str) -> str:
        cleaned_characters: list[str] = []
        for character in text.strip():
            if self._is_allowed_plate_character(character):
                cleaned_characters.append(character.upper() if character.isascii() else character)
            elif character.isspace():
                cleaned_characters.append(" ")
        cleaned = " ".join("".join(cleaned_characters).split())
        if not cleaned:
            return ""
        return cleaned[:8]

    def _normalize_bottom_digits(self, text: str) -> str:
        digit_map = {
            "0": "०",
            "1": "१",
            "2": "२",
            "3": "३",
            "4": "४",
            "5": "५",
            "6": "६",
            "7": "७",
            "8": "८",
            "9": "९",
            "०": "०",
            "१": "१",
            "२": "२",
            "३": "३",
            "४": "४",
            "५": "५",
            "६": "६",
            "७": "७",
            "८": "८",
            "९": "९",
            "O": "०",
            "o": "०",
            "Q": "०",
            "Z": "२",
            "z": "२",
            "S": "५",
            "s": "५",
            "T": "७",
            "?": "७",
        }
        digits = [digit_map[character] for character in text if character in digit_map]
        if not digits:
            return ""
        return "".join(digits[:4])

    def _normalize_traditional_top_text(self, text: str) -> str:
        cleaned_characters: list[str] = []
        for character in text.strip():
            if "\u0900" <= character <= "\u097f":
                cleaned_characters.append(character)
            elif character.isspace():
                cleaned_characters.append(" ")
        cleaned = " ".join("".join(cleaned_characters).split())
        return cleaned[:12]

    def _normalize_modern_plate_text(self, text: str) -> str:
        cleaned = "".join(
            character.upper()
            for character in text
            if ("A" <= character.upper() <= "Z") or character.isdigit() or ("\u0966" <= character <= "\u096f")
        )
        if not cleaned:
            return ""
        return cleaned[:8]

    def _postprocess_segmented_text(self, text: str) -> str:
        if not text:
            return ""
        cleaned = self._normalize_plate_text(text)
        result: list[str] = []
        digit_mode = False
        for character in cleaned:
            if character.isspace():
                continue
            if self._is_digit_character(character):
                digit_mode = True
                result.append(character)
                continue
            if digit_mode:
                continue
            if self._is_letter_character(character):
                result.append(character)
        return "".join(result)

    def _is_allowed_plate_character(self, character: str) -> bool:
        if self._is_digit_character(character) or self._is_letter_character(character):
            return True
        return False

    def _is_digit_character(self, character: str) -> bool:
        return character.isdigit() or ("\u0966" <= character <= "\u096f")

    def _is_letter_character(self, character: str) -> bool:
        return ("A" <= character.upper() <= "Z") or ("\u0900" <= character <= "\u097f")

    def _update_plate_history(self, track: TrackState, value: str) -> str:
        readings = track.metadata.get("plate_readings")
        if not isinstance(readings, deque):
            readings = deque(maxlen=5)
        readings.append(value)
        track.metadata["plate_readings"] = readings
        counts = Counter(readings)
        smoothed = counts.most_common(1)[0][0]
        track.metadata["plate_stable"] = counts[smoothed] >= 3
        track.metadata["plate_last_processed_frame"] = track.last_seen_frame
        return smoothed

    def _can_skip_plate_ocr(self, track: TrackState) -> bool:
        interval = max(1, self.config.ocr.frame_interval)
        last_attempt = track.metadata.get("plate_last_attempt_frame")
        if isinstance(last_attempt, int) and (track.last_seen_frame - last_attempt) < interval:
            return True

        if not track.plate_text:
            return False

        last_success = track.metadata.get("plate_last_success_frame")
        cooldown = max(interval, self.config.ocr.stable_cooldown_frames)
        if isinstance(last_success, int) and (track.last_seen_frame - last_success) < cooldown:
            return True

        if not track.metadata.get("plate_stable", False):
            return False
        last_processed = track.metadata.get("plate_last_processed_frame")
        if not isinstance(last_processed, int):
            return False
        return (track.last_seen_frame - last_processed) < cooldown

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
