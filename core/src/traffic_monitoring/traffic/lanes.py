from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from traffic_monitoring.domain import TrackState

Point = tuple[int, int]
Polygon = tuple[Point, ...]


def load_named_rois(path: Path) -> dict[str, Polygon]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rois: dict[str, Polygon] = {}
    for name, points in raw.items():
        rois[name] = tuple((int(point[0]), int(point[1])) for point in points)
    return rois


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

    def to_dict(self) -> dict[str, dict[str, int]]:
        return {"lane_counts": dict(self.lane_counts)}


class LaneAssignmentEngine:
    def __init__(self, roi_config_path: Path) -> None:
        self.roi_config_path = roi_config_path
        self.rois = load_named_rois(roi_config_path) if roi_config_path.exists() else {}

    def evaluate(self, tracks: list[TrackState]) -> LaneMetricsSnapshot:
        lane_counts = {name: 0 for name in self.rois}
        for track in tracks:
            if track.label_name == "person":
                track.metadata["approach"] = None
                continue
            lane_name = self._assign_lane(track)
            track.metadata["approach"] = lane_name
            if lane_name is not None:
                lane_counts[lane_name] += 1
        return LaneMetricsSnapshot(lane_counts=lane_counts)

    def _assign_lane(self, track: TrackState) -> str | None:
        point = track.bottom_center()
        for lane_name, polygon in self.rois.items():
            if point_in_polygon(point, polygon):
                return lane_name
        return None
