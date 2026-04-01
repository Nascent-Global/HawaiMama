from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from math import hypot
from statistics import mean
from typing import Any, Deque, Iterable, Sequence


class TrafficClass(str, Enum):
    PERSON = "person"
    MOTORCYCLE = "motorcycle"
    CAR = "car"
    BUS = "bus"
    TRUCK = "truck"
    UNKNOWN = "unknown"


class HelmetState(str, Enum):
    UNKNOWN = "unknown"
    PRESENT = "present"
    ABSENT = "absent"
    NOT_APPLICABLE = "not_applicable"


class PlateState(str, Enum):
    UNKNOWN = "unknown"
    DETECTED = "detected"
    READABLE = "readable"
    UNREADABLE = "unreadable"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class FrameContext:
    frame_index: int
    fps: float
    width: int
    height: int
    timestamp_seconds: float


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Axis-aligned bounding box in pixel coordinates."""

    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        if self.x2 < self.x1 or self.y2 < self.y1:
            raise ValueError("BoundingBox requires x2 >= x1 and y2 >= y1")

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    @property
    def diagonal(self) -> float:
        return hypot(self.width, self.height)

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)

    @classmethod
    def from_xywh(cls, x: float, y: float, width: float, height: float) -> "BoundingBox":
        return cls(x, y, x + width, y + height)

    def clamp(self, max_width: float, max_height: float) -> "BoundingBox":
        return BoundingBox(
            max(0.0, min(self.x1, max_width)),
            max(0.0, min(self.y1, max_height)),
            max(0.0, min(self.x2, max_width)),
            max(0.0, min(self.y2, max_height)),
        )

    def expand(self, padding: float) -> "BoundingBox":
        return BoundingBox(
            self.x1 - padding,
            self.y1 - padding,
            self.x2 + padding,
            self.y2 + padding,
        )

    def translate(self, dx: float, dy: float) -> "BoundingBox":
        return BoundingBox(self.x1 + dx, self.y1 + dy, self.x2 + dx, self.y2 + dy)

    def contains_point(self, point: tuple[float, float]) -> bool:
        x, y = point
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def intersection(self, other: "BoundingBox") -> "BoundingBox | None":
        x1 = max(self.x1, other.x1)
        y1 = max(self.y1, other.y1)
        x2 = min(self.x2, other.x2)
        y2 = min(self.y2, other.y2)
        if x2 < x1 or y2 < y1:
            return None
        return BoundingBox(x1, y1, x2, y2)

    def intersection_area(self, other: "BoundingBox") -> float:
        intersection = self.intersection(other)
        return 0.0 if intersection is None else intersection.area

    def iou(self, other: "BoundingBox") -> float:
        intersection = self.intersection_area(other)
        if intersection == 0.0:
            return 0.0
        union = self.area + other.area - intersection
        return 0.0 if union <= 0.0 else intersection / union

    def coverage_ratio(self, other: "BoundingBox") -> float:
        """Return how much of this box is covered by the other box."""

        if self.area <= 0.0:
            return 0.0
        return self.intersection_area(other) / self.area

    def distance_to_point(self, point: tuple[float, float]) -> float:
        x, y = point
        cx, cy = self.center
        return hypot(cx - x, cy - y)

    def distance_to_box(self, other: "BoundingBox") -> float:
        cx, cy = self.center
        ox, oy = other.center
        return hypot(cx - ox, cy - oy)


@dataclass(slots=True)
class Detection:
    """Single model output for one detected object."""

    label: TrafficClass | str
    confidence: float
    bbox: BoundingBox
    track_id: int | None = None
    frame_index: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized_label(self) -> str:
        return self.label.value if isinstance(self.label, Enum) else str(self.label)


@dataclass(slots=True)
class TrackState:
    """Mutable state kept per tracked object across frames."""

    track_id: int
    label: TrafficClass | str
    bbox: BoundingBox
    confidence: float = 0.0
    first_seen_frame: int = 0
    last_seen_frame: int = 0
    center_history: Deque[tuple[float, float]] = field(
        default_factory=lambda: deque(maxlen=30)
    )
    bbox_history: Deque[BoundingBox] = field(default_factory=lambda: deque(maxlen=30))
    displacement_history_px: Deque[float] = field(default_factory=lambda: deque(maxlen=20))
    speed_history_kmh: Deque[float] = field(default_factory=lambda: deque(maxlen=20))
    estimated_speed_kmh: float | None = None
    helmet_state: HelmetState = HelmetState.UNKNOWN
    plate_state: PlateState = PlateState.UNKNOWN
    plate_text: str | None = None
    plate_confidence: float | None = None
    plate_bbox: BoundingBox | None = None
    face_bbox: BoundingBox | None = None
    face_confidence: float | None = None
    associated_person_ids: set[int] = field(default_factory=set)
    active_violation_codes: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.record_bbox(self.bbox)

    @property
    def latest_center(self) -> tuple[float, float]:
        return self.bbox.center

    @property
    def label_name(self) -> str:
        return self.label.value if isinstance(self.label, Enum) else str(self.label)

    def record_bbox(self, bbox: BoundingBox) -> None:
        self.bbox = bbox
        self.bbox_history.append(bbox)
        self.center_history.append(bbox.center)

    def update_from_detection(
        self, detection: Detection, frame_index: int, *, keep_speed: bool = True
    ) -> None:
        self.label = detection.label
        self.confidence = detection.confidence
        self.last_seen_frame = frame_index
        self.record_bbox(detection.bbox)
        if not keep_speed:
            self.speed_history_kmh.clear()
            self.estimated_speed_kmh = None
        self.metadata.update(detection.metadata)

    def record_speed(self, speed_kmh: float | None) -> None:
        if speed_kmh is None:
            return
        self.speed_history_kmh.append(speed_kmh)
        self.estimated_speed_kmh = speed_kmh

    def record_displacement(self, displacement_px: float) -> None:
        self.displacement_history_px.append(displacement_px)

    def smoothed_speed(self, window: int = 5) -> float | None:
        samples = list(self.speed_history_kmh)[-window:]
        if not samples:
            return self.estimated_speed_kmh
        return mean(samples)

    def age_in_frames(self, current_frame: int) -> int:
        return max(0, current_frame - self.last_seen_frame)

    def mark_plate(
        self,
        *,
        text: str | None,
        confidence: float | None,
        state: PlateState,
        bbox: BoundingBox | None = None,
    ) -> None:
        self.plate_text = text
        self.plate_confidence = confidence
        self.plate_state = state
        self.plate_bbox = bbox

    def mark_helmet_state(self, state: HelmetState) -> None:
        self.helmet_state = state

    def mark_face(self, bbox: BoundingBox | None, confidence: float | None) -> None:
        self.face_bbox = bbox
        self.face_confidence = confidence

    def attach_person(self, person_track_id: int) -> None:
        self.associated_person_ids.add(person_track_id)

    def detach_person(self, person_track_id: int) -> None:
        self.associated_person_ids.discard(person_track_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "label": self.label_name,
            "bbox": self.bbox.as_tuple(),
            "confidence": self.confidence,
            "first_seen_frame": self.first_seen_frame,
            "last_seen_frame": self.last_seen_frame,
            "estimated_speed_kmh": self.estimated_speed_kmh,
            "helmet_state": self.helmet_state.value,
            "plate_state": self.plate_state.value,
            "plate_text": self.plate_text,
            "plate_confidence": self.plate_confidence,
            "associated_person_ids": sorted(self.associated_person_ids),
            "active_violation_codes": sorted(self.active_violation_codes),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class AssociationCandidate:
    """Scored candidate match between two tracked objects."""

    left_id: int
    right_id: int
    score: float
    overlap_ratio: float
    center_distance: float


@dataclass(slots=True)
class FrameState:
    """Snapshot of the per-frame tracker output."""

    frame_index: int
    timestamp_s: float | None = None
    tracks: dict[int, TrackState] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def active_tracks(self) -> list[TrackState]:
        return list(self.tracks.values())

    def get_track(self, track_id: int) -> TrackState | None:
        return self.tracks.get(track_id)

    def upsert_track(self, track: TrackState) -> None:
        self.tracks[track.track_id] = track

    def remove_track(self, track_id: int) -> None:
        self.tracks.pop(track_id, None)


def mean_box_center(boxes: Sequence[BoundingBox]) -> tuple[float, float] | None:
    if not boxes:
        return None
    xs = [box.center[0] for box in boxes]
    ys = [box.center[1] for box in boxes]
    return (mean(xs), mean(ys))


def clamp_track_ids(track_ids: Iterable[int]) -> list[int]:
    return sorted({int(track_id) for track_id in track_ids})


TrafficTrack = TrackState
