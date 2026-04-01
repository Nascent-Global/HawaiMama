from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

import cv2
import numpy as np

from .domain import FrameContext, TrafficClass, TrackState
from .violations import ViolationFinding, ViolationSeverity, violation_codes


ColorRGB = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class AnnotationLine:
    label: str
    value: str

    def as_text(self) -> str:
        return f"{self.label}: {self.value}"


@dataclass(frozen=True, slots=True)
class AnnotationStyle:
    normal_color: ColorRGB = (0, 200, 0)
    warning_color: ColorRGB = (0, 180, 255)
    violation_color: ColorRGB = (0, 0, 255)
    text_color: ColorRGB = (255, 255, 255)
    background_color: ColorRGB = (20, 20, 20)
    thickness: int = 2
    line_thickness: int = 1
    font_scale: float = 0.5


@dataclass(frozen=True, slots=True)
class TrackAnnotation:
    track_id: int
    bbox: tuple[float, float, float, float]
    title: str
    lines: tuple[AnnotationLine, ...] = ()
    color: ColorRGB = (0, 200, 0)
    severity: ViolationSeverity | None = None
    violation_codes: tuple[str, ...] = ()

    def as_text_lines(self) -> list[str]:
        return [self.title, *[line.as_text() for line in self.lines]]


class AnnotationRenderer(Protocol):
    """Interface for renderers that can consume annotation specs."""

    def render_track(self, annotation: TrackAnnotation) -> object: ...

    def render_frame(self, annotations: Sequence[TrackAnnotation]) -> object: ...


def _label_name(track: TrackState) -> str:
    return track.label_name


def _display_label(track: TrackState) -> str:
    label = _label_name(track).lower()
    if label == TrafficClass.MOTORCYCLE.value:
        return "Bike"
    if label == TrafficClass.CAR.value:
        return "Car"
    if label == TrafficClass.BUS.value:
        return "Bus"
    if label == TrafficClass.TRUCK.value:
        return "Truck"
    if label == TrafficClass.PERSON.value:
        return "Person"
    return _label_name(track).title()


def _format_speed(track: TrackState) -> str:
    speed = track.smoothed_speed()
    if speed is None:
        speed = track.estimated_speed_kmh
    return "Estimating" if speed is None else f"{speed:.1f} km/h"


def _format_plate(track: TrackState) -> str:
    if track.plate_text:
        return track.plate_text
    if track.plate_state.value != "unknown":
        return track.plate_state.value.replace("_", " ").title()
    return "N/A"


def _join_violation_codes(findings: Sequence[ViolationFinding]) -> str:
    codes = violation_codes(findings)
    return ", ".join(code.value for code in codes) if codes else "None"


def _highest_severity(findings: Sequence[ViolationFinding]) -> ViolationSeverity | None:
    if not findings:
        return None
    order = {
        ViolationSeverity.INFO: 0,
        ViolationSeverity.WARNING: 1,
        ViolationSeverity.CRITICAL: 2,
    }
    return max(findings, key=lambda finding: order[finding.severity]).severity


def choose_annotation_color(
    findings: Sequence[ViolationFinding],
    *,
    style: AnnotationStyle | None = None,
) -> ColorRGB:
    style = style or AnnotationStyle()
    if not findings:
        return style.normal_color
    if any(finding.severity == ViolationSeverity.CRITICAL for finding in findings):
        return style.violation_color
    return style.warning_color


def build_track_annotation(
    track: TrackState,
    findings: Sequence[ViolationFinding] = (),
    *,
    style: AnnotationStyle | None = None,
) -> TrackAnnotation:
    style = style or AnnotationStyle()
    color = choose_annotation_color(findings, style=style)
    title = f"ID: {track.track_id} | {_display_label(track)} | {_format_speed(track)}"
    lines = (
        AnnotationLine("Plate", _format_plate(track)),
        AnnotationLine("Violations", _join_violation_codes(findings)),
    )
    if track.face_bbox is not None:
        lines = (*lines, AnnotationLine("Face", "Captured"))
    if track.helmet_state.value != "unknown":
        lines = (*lines, AnnotationLine("Helmet", track.helmet_state.value.replace("_", " ").title()))
    return TrackAnnotation(
        track_id=track.track_id,
        bbox=track.bbox.as_tuple(),
        title=title,
        lines=lines,
        color=color,
        severity=_highest_severity(findings),
        violation_codes=tuple(code.value for code in violation_codes(findings)),
    )


def annotation_summary(annotation: TrackAnnotation) -> str:
    return " | ".join(annotation.as_text_lines())


def annotations_for_tracks(
    tracks: Sequence[TrackState],
    violations_by_track: dict[int, Sequence[ViolationFinding]] | None = None,
    *,
    style: AnnotationStyle | None = None,
) -> list[TrackAnnotation]:
    style = style or AnnotationStyle()
    violations_by_track = violations_by_track or {}
    return [
        build_track_annotation(track, violations_by_track.get(track.track_id, ()), style=style)
        for track in tracks
    ]


def annotate_frame(
    frame: np.ndarray,
    tracks: Sequence[TrackState],
    context: FrameContext,
    violations_by_track: dict[int, Sequence[ViolationFinding]] | None = None,
    *,
    style: AnnotationStyle | None = None,
) -> np.ndarray:
    style = style or AnnotationStyle()
    annotated = frame.copy()
    for annotation in annotations_for_tracks(tracks, violations_by_track, style=style):
        x1, y1, x2, y2 = (int(value) for value in annotation.bbox)
        cv2.rectangle(
            annotated,
            (x1, y1),
            (x2, y2),
            annotation.color,
            style.thickness,
        )

        lines = annotation.as_text_lines()
        line_height = 18
        text_sizes = [
            cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, style.font_scale, style.line_thickness)[0]
            for line in lines
        ]
        panel_width = max((size[0] for size in text_sizes), default=0) + 10
        panel_height = len(lines) * line_height + 8
        panel_x1 = max(0, x1)
        panel_y1 = y1 - panel_height - 4
        if panel_y1 < 0:
            panel_y1 = min(max(0, y2 + 4), max(0, annotated.shape[0] - panel_height))
        panel_x2 = min(annotated.shape[1], panel_x1 + panel_width)
        panel_y2 = min(annotated.shape[0], panel_y1 + panel_height)
        cv2.rectangle(
            annotated,
            (panel_x1, panel_y1),
            (panel_x2, panel_y2),
            style.background_color,
            thickness=-1,
        )
        cv2.rectangle(
            annotated,
            (panel_x1, panel_y1),
            (panel_x2, panel_y2),
            annotation.color,
            thickness=1,
        )

        baseline = panel_y1 + 16
        for line in lines:
            cv2.putText(
                annotated,
                line,
                (panel_x1 + 5, baseline),
                cv2.FONT_HERSHEY_SIMPLEX,
                style.font_scale,
                style.text_color,
                style.line_thickness,
                cv2.LINE_AA,
            )
            baseline += line_height

    footer = f"Frame {context.frame_index} | {context.timestamp_seconds:.2f}s"
    cv2.putText(
        annotated,
        footer,
        (12, annotated.shape[0] - 12),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        style.text_color,
        2,
        cv2.LINE_AA,
    )
    return annotated
