from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from .domain import FrameContext, TrackState
from .violations import ViolationFinding


class ViolationRecorder:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self.records: list[dict[str, object]] = []

    def record(
        self,
        context: FrameContext,
        tracks: Sequence[TrackState],
        findings_by_track: dict[int, Sequence[ViolationFinding]],
    ) -> None:
        for track in tracks:
            findings = findings_by_track.get(track.track_id, ())
            if not findings:
                continue
            self.records.append(
                {
                    "frame_index": context.frame_index,
                    "timestamp_seconds": round(context.timestamp_seconds, 3),
                    "track_id": track.track_id,
                    "vehicle_type": track.label_name,
                    "speed_kmh": round(track.smoothed_speed() or track.estimated_speed_kmh or 0.0, 2),
                    "plate_text": track.plate_text,
                    "plate_state": track.plate_state.value,
                    "violations": [finding.code.value for finding in findings],
                }
            )

    def flush(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(json.dumps(self.records, indent=2), encoding="utf-8")
