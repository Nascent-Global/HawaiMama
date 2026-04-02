from __future__ import annotations

import json
from dataclasses import dataclass
from math import hypot
from pathlib import Path

from traffic_monitoring.domain import FrameContext
from traffic_monitoring.domain import TrackState

Point = tuple[int, int]
Polygon = tuple[Point, ...]
Line = tuple[Point, Point]


def load_named_rois(path: Path) -> dict[str, Polygon]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    roi_payload = raw.get("rois", raw)
    rois: dict[str, Polygon] = {}
    for name, points in roi_payload.items():
        rois[name] = tuple((int(point[0]), int(point[1])) for point in points)
    return rois


def load_stop_lines(path: Path) -> dict[str, Line]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    line_payload = raw.get("stop_lines", {})
    stop_lines: dict[str, Line] = {}
    for name, points in line_payload.items():
        if len(points) != 2:
            continue
        stop_lines[name] = (
            (int(points[0][0]), int(points[0][1])),
            (int(points[1][0]), int(points[1][1])),
        )
    return stop_lines


def point_in_polygon(point: tuple[float, float], polygon: Polygon) -> bool:
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


@dataclass(frozen=True, slots=True)
class LaneMetricsSnapshot:
    lane_counts: dict[str, int]
    lane_metrics: dict[str, dict[str, float | int]]
    emergency_lane: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "lane_counts": dict(self.lane_counts),
            "lane_metrics": {lane: dict(values) for lane, values in self.lane_metrics.items()},
        }
        if self.emergency_lane is not None:
            payload["emergency_lane"] = self.emergency_lane
        return payload


class LaneAssignmentEngine:
    def __init__(
        self,
        roi_config_path: Path,
        *,
        stop_speed_threshold_px: float,
        stop_frames_threshold: int,
        stop_line_distance_px: float,
        emergency_labels: tuple[str, ...],
        emergency_keywords: tuple[str, ...],
    ) -> None:
        self.roi_config_path = roi_config_path
        self.rois = load_named_rois(roi_config_path) if roi_config_path.exists() else {}
        self.stop_lines = load_stop_lines(roi_config_path) if roi_config_path.exists() else {}
        self.stop_speed_threshold_px = stop_speed_threshold_px
        self.stop_frames_threshold = stop_frames_threshold
        self.stop_line_distance_px = stop_line_distance_px
        self.emergency_labels = {label.lower() for label in emergency_labels}
        self.emergency_keywords = tuple(keyword.lower() for keyword in emergency_keywords)

    def evaluate(
        self,
        tracks: list[TrackState],
        context: FrameContext,
    ) -> LaneMetricsSnapshot:
        lane_counts = {name: 0 for name in self.rois}
        lane_queues = {name: 0 for name in self.rois}
        lane_wait_totals = {name: 0.0 for name in self.rois}
        emergency_lane: str | None = None
        for track in tracks:
            if track.label_name == "person":
                track.metadata["approach"] = None
                track.metadata["is_stopped"] = False
                track.metadata["wait_time"] = 0.0
                track.metadata["is_emergency"] = False
                continue
            lane_name = self._assign_lane(track)
            track.metadata["approach"] = lane_name
            if lane_name is not None:
                lane_counts[lane_name] += 1
                is_emergency = self._is_emergency_vehicle(track)
                track.metadata["is_emergency"] = is_emergency
                if emergency_lane is None and is_emergency:
                    emergency_lane = lane_name
                if self._is_stopped_in_lane(track, lane_name, context):
                    lane_queues[lane_name] += 1
                    lane_wait_totals[lane_name] += float(track.metadata.get("wait_time", 0.0))
            else:
                track.metadata["is_stopped"] = False
                track.metadata["wait_time"] = 0.0
                track.metadata.pop("wait_started_at", None)
                track.metadata["is_emergency"] = False
        lane_metrics: dict[str, dict[str, float | int]] = {}
        for lane_name in self.rois:
            queue_count = lane_queues[lane_name]
            lane_metrics[lane_name] = {
                "count": lane_counts[lane_name],
                "queue": queue_count,
                "avg_wait": round(
                    (lane_wait_totals[lane_name] / queue_count) if queue_count else 0.0,
                    2,
                ),
            }
        return LaneMetricsSnapshot(
            lane_counts=lane_counts,
            lane_metrics=lane_metrics,
            emergency_lane=emergency_lane,
        )

    def _assign_lane(self, track: TrackState) -> str | None:
        point = track.bottom_center()
        for lane_name, polygon in self.rois.items():
            if point_in_polygon(point, polygon):
                return lane_name
        return None

    def _is_stopped_in_lane(
        self,
        track: TrackState,
        lane_name: str,
        context: FrameContext,
    ) -> bool:
        movement = self._recent_bottom_center_movement(track)
        stopped_frames = int(track.metadata.get("stopped_frames", 0))
        if movement is not None and movement < self.stop_speed_threshold_px:
            stopped_frames += 1
        else:
            stopped_frames = 0
        track.metadata["stopped_frames"] = stopped_frames

        stop_line = self.stop_lines.get(lane_name)
        near_stop_line = True
        if stop_line is not None:
            near_stop_line = (
                point_to_line_distance(track.bottom_center(), stop_line) <= self.stop_line_distance_px
            )
        is_stopped = stopped_frames >= self.stop_frames_threshold and near_stop_line
        if is_stopped:
            wait_started_at = track.metadata.get("wait_started_at")
            if wait_started_at is None:
                wait_started_at = context.timestamp_seconds
                track.metadata["wait_started_at"] = wait_started_at
            track.metadata["wait_time"] = round(
                max(0.0, context.timestamp_seconds - float(wait_started_at)),
                2,
            )
        else:
            track.metadata["wait_time"] = 0.0
            track.metadata.pop("wait_started_at", None)
        track.metadata["is_stopped"] = is_stopped
        return is_stopped

    def _recent_bottom_center_movement(self, track: TrackState) -> float | None:
        if len(track.bbox_history) < 2:
            return None
        previous = track.bbox_history[-2]
        current = track.bbox_history[-1]
        previous_point = ((previous.x1 + previous.x2) / 2.0, previous.y2)
        current_point = ((current.x1 + current.x2) / 2.0, current.y2)
        return hypot(current_point[0] - previous_point[0], current_point[1] - previous_point[1])

    def _is_emergency_vehicle(self, track: TrackState) -> bool:
        label = track.label_name.lower()
        if label in self.emergency_labels:
            return True
        candidates = [label]
        if track.plate_text:
            candidates.append(track.plate_text.lower())
        raw_label = track.metadata.get("raw_label")
        if raw_label:
            candidates.append(str(raw_label).lower())
        return any(keyword in candidate for candidate in candidates for keyword in self.emergency_keywords)


def point_to_line_distance(point: tuple[float, float], line: Line) -> float:
    px, py = point
    (x1, y1), (x2, y2) = line
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return hypot(px - x1, py - y1)
    numerator = abs(dy * px - dx * py + x2 * y1 - y2 * x1)
    denominator = hypot(dx, dy)
    return numerator / denominator
