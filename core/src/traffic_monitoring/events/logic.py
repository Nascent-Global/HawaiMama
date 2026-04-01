from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Sequence

from traffic_monitoring.config import TrafficMonitoringConfig
from traffic_monitoring.domain import FrameContext, HelmetState, PlateState, TrafficClass, TrackState


class ViolationCode(str, Enum):
    NO_HELMET = "no_helmet"
    OVERSPEED = "overspeed"
    WRONG_LANE = "wrong_lane"
    PLATE_MISSING = "plate_missing"
    PLATE_UNREADABLE = "plate_unreadable"


class ViolationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class ViolationFinding:
    code: ViolationCode
    severity: ViolationSeverity
    message: str
    track_id: int
    frame_index: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ViolationContext:
    overspeed_threshold_kmh: float = 40.0
    helmet_stability_frames: int = 5
    require_plate: bool = True
    plate_min_length: int = 4
    wrong_lane_track_ids: set[int] = field(default_factory=set)
    treat_unreadable_plate_as_violation: bool = True

    def is_wrong_lane(self, track_id: int) -> bool:
        return track_id in self.wrong_lane_track_ids


VEHICLE_CLASSES = {
    TrafficClass.MOTORCYCLE.value,
    TrafficClass.CAR.value,
    TrafficClass.BUS.value,
    TrafficClass.TRUCK.value,
}


def _label_name(track: TrackState) -> str:
    return track.label_name.lower()


def _is_vehicle(track: TrackState) -> bool:
    return _label_name(track) in VEHICLE_CLASSES


def _safe_speed(track: TrackState) -> float | None:
    smoothed = track.smoothed_speed()
    return smoothed if smoothed is not None else track.estimated_speed_kmh


def evaluate_track_violations(
    track: TrackState,
    context: ViolationContext | None = None,
    *,
    frame_index: int | None = None,
) -> list[ViolationFinding]:
    context = context or ViolationContext()
    findings: list[ViolationFinding] = []

    if not _is_vehicle(track):
        return findings

    speed = _safe_speed(track)
    if speed is not None and speed >= context.overspeed_threshold_kmh:
        findings.append(
            ViolationFinding(
                code=ViolationCode.OVERSPEED,
                severity=ViolationSeverity.CRITICAL,
                message=f"Speed {speed:.1f} km/h exceeds threshold {context.overspeed_threshold_kmh:.1f} km/h",
                track_id=track.track_id,
                frame_index=frame_index,
                evidence={
                    "speed_kmh": round(speed, 2),
                    "threshold_kmh": round(context.overspeed_threshold_kmh, 2),
                },
            )
        )

    if _label_name(track) == TrafficClass.MOTORCYCLE.value:
        if (
            track.helmet_state == HelmetState.ABSENT
            and track.helmet_stable_absent_frames >= context.helmet_stability_frames
            and (track.last_seen_frame - track.first_seen_frame + 1) >= context.helmet_stability_frames
        ):
            findings.append(
                ViolationFinding(
                    code=ViolationCode.NO_HELMET,
                    severity=ViolationSeverity.CRITICAL,
                    message="Motorcycle rider appears to be without a helmet",
                    track_id=track.track_id,
                    frame_index=frame_index,
                    evidence={
                        "helmet_state": track.helmet_state.value,
                        "stable_absent_frames": track.helmet_stable_absent_frames,
                    },
                )
            )

    if context.require_plate:
        if track.plate_state in {PlateState.MISSING, PlateState.UNKNOWN} and not track.plate_text:
            findings.append(
                ViolationFinding(
                    code=ViolationCode.PLATE_MISSING,
                    severity=ViolationSeverity.WARNING,
                    message="No license plate detected for the tracked vehicle",
                    track_id=track.track_id,
                    frame_index=frame_index,
                    evidence={"plate_state": track.plate_state.value},
                )
            )
        elif track.plate_state == PlateState.UNREADABLE:
            if context.treat_unreadable_plate_as_violation:
                findings.append(
                    ViolationFinding(
                        code=ViolationCode.PLATE_UNREADABLE,
                        severity=ViolationSeverity.WARNING,
                        message="License plate was detected but OCR could not read it",
                        track_id=track.track_id,
                        frame_index=frame_index,
                        evidence={
                            "plate_state": track.plate_state.value,
                            "plate_confidence": track.plate_confidence,
                        },
                    )
                )
        elif track.plate_text:
            normalized = track.plate_text.strip()
            if len(normalized) < context.plate_min_length:
                findings.append(
                    ViolationFinding(
                        code=ViolationCode.PLATE_UNREADABLE,
                        severity=ViolationSeverity.WARNING,
                        message="License plate text is too short to be trusted",
                        track_id=track.track_id,
                        frame_index=frame_index,
                        evidence={
                            "plate_text": track.plate_text,
                            "plate_length": len(normalized),
                        },
                    )
                )

    if context.is_wrong_lane(track.track_id):
        findings.append(
            ViolationFinding(
                code=ViolationCode.WRONG_LANE,
                severity=ViolationSeverity.CRITICAL,
                message="Vehicle appears to be in the wrong lane",
                track_id=track.track_id,
                frame_index=frame_index,
                evidence={"track_id": track.track_id},
            )
        )

    return findings


def violation_codes(findings: Sequence[ViolationFinding]) -> list[ViolationCode]:
    return [finding.code for finding in findings]


def violation_messages(findings: Sequence[ViolationFinding]) -> list[str]:
    return [finding.message for finding in findings]


def highest_severity(findings: Sequence[ViolationFinding]) -> ViolationSeverity | None:
    if not findings:
        return None
    order = {
        ViolationSeverity.INFO: 0,
        ViolationSeverity.WARNING: 1,
        ViolationSeverity.CRITICAL: 2,
    }
    return max(findings, key=lambda finding: order[finding.severity]).severity


def has_violation(findings: Sequence[ViolationFinding], code: ViolationCode) -> bool:
    return any(finding.code == code for finding in findings)


def findings_by_track(
    findings: Iterable[ViolationFinding],
) -> dict[int, list[ViolationFinding]]:
    grouped: dict[int, list[ViolationFinding]] = {}
    for finding in findings:
        grouped.setdefault(finding.track_id, []).append(finding)
    return grouped


class ViolationEngine:
    def __init__(self, config: TrafficMonitoringConfig) -> None:
        self.config = config
        self._current_findings: dict[int, list[ViolationFinding]] = {}
        self._new_findings: dict[int, list[ViolationFinding]] = {}

    @property
    def current_findings(self) -> dict[int, list[ViolationFinding]]:
        return self._current_findings

    @property
    def new_findings(self) -> dict[int, list[ViolationFinding]]:
        return self._new_findings

    def evaluate(
        self,
        context: FrameContext,
        tracks: Sequence[TrackState],
    ) -> dict[int, list[ViolationFinding]]:
        violation_context = ViolationContext(
            overspeed_threshold_kmh=self.config.speed.overspeed_threshold_kmh,
            helmet_stability_frames=self.config.detection.helmet_stability_frames,
            require_plate=self.config.ocr.enforce_plate_rules,
            wrong_lane_track_ids=self._wrong_lane_track_ids(tracks),
            treat_unreadable_plate_as_violation=True,
        )

        findings: list[ViolationFinding] = []
        new_findings: list[ViolationFinding] = []
        for track in tracks:
            per_track = evaluate_track_violations(
                track,
                violation_context,
                frame_index=context.frame_index,
            )
            current_codes = {finding.code.value for finding in per_track}
            previous_codes = set(track.active_violation_codes)
            track.active_violation_codes = current_codes
            track.metadata["violations"] = sorted(current_codes)
            findings.extend(per_track)
            new_findings.extend(
                finding for finding in per_track if finding.code.value not in previous_codes
            )

        self._current_findings = findings_by_track(findings)
        self._new_findings = findings_by_track(new_findings)
        return self._current_findings

    def _wrong_lane_track_ids(self, tracks: Sequence[TrackState]) -> set[int]:
        if not self.config.wrong_lane.enabled or not self.config.wrong_lane.lane_polygons:
            return set()

        matching: set[int] = set()
        for track in tracks:
            if track.label_name not in self.config.wrong_lane.allowed_vehicle_classes:
                continue
            point = tuple(int(value) for value in track.latest_center)
            for polygon in self.config.wrong_lane.lane_polygons:
                if _point_in_polygon(point, polygon):
                    matching.add(track.track_id)
                    break
        return matching


def _point_in_polygon(point: tuple[int, int], polygon: Sequence[tuple[int, int]]) -> bool:
    x, y = point
    inside = False
    if len(polygon) < 3:
        return False
    previous_x, previous_y = polygon[-1]
    for current_x, current_y in polygon:
        intersects = ((current_y > y) != (previous_y > y)) and (
            x < (previous_x - current_x) * (y - current_y) / ((previous_y - current_y) or 1e-9) + current_x
        )
        if intersects:
            inside = not inside
        previous_x, previous_y = current_x, current_y
    return inside
