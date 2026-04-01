from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SignalState(str, Enum):
    RED = "RED"
    GREEN = "GREEN"
    YELLOW = "YELLOW"


@dataclass(frozen=True, slots=True)
class SignalSnapshot:
    active_lane: str
    state: SignalState
    time_remaining: float

    def to_dict(self) -> dict[str, str | float]:
        return {
            "active_lane": self.active_lane,
            "state": self.state.value,
            "time_remaining": round(self.time_remaining, 2),
        }


class SignalStateMachine:
    def __init__(
        self,
        lane_order: list[str],
        *,
        initial_active_lane: str,
        min_green_time: float,
        max_green_time: float,
        yellow_time: float,
    ) -> None:
        self.lane_order = lane_order or [initial_active_lane]
        self.current_active_lane = (
            initial_active_lane if initial_active_lane in self.lane_order else self.lane_order[0]
        )
        self.current_state = SignalState.GREEN
        self.state_started_at_seconds = 0.0
        self.min_green_time = min_green_time
        self.max_green_time = max(max_green_time, min_green_time)
        self.yellow_time = yellow_time

    def update(self, timestamp_seconds: float) -> SignalSnapshot:
        elapsed = max(0.0, timestamp_seconds - self.state_started_at_seconds)

        if self.current_state == SignalState.GREEN:
            if elapsed >= self.max_green_time:
                self.current_state = SignalState.YELLOW
                self.state_started_at_seconds = timestamp_seconds
                elapsed = 0.0
        elif self.current_state == SignalState.YELLOW:
            if elapsed >= self.yellow_time:
                self.current_active_lane = self._next_lane()
                self.current_state = SignalState.GREEN
                self.state_started_at_seconds = timestamp_seconds
                elapsed = 0.0

        time_remaining = self._time_remaining(timestamp_seconds)
        return SignalSnapshot(
            active_lane=self.current_active_lane,
            state=self.current_state,
            time_remaining=time_remaining,
        )

    def _time_remaining(self, timestamp_seconds: float) -> float:
        elapsed = max(0.0, timestamp_seconds - self.state_started_at_seconds)
        if self.current_state == SignalState.GREEN:
            return max(0.0, self.max_green_time - elapsed)
        if self.current_state == SignalState.YELLOW:
            return max(0.0, self.yellow_time - elapsed)
        return 0.0

    def _next_lane(self) -> str:
        if not self.lane_order:
            return self.current_active_lane
        current_index = self.lane_order.index(self.current_active_lane)
        next_index = (current_index + 1) % len(self.lane_order)
        return self.lane_order[next_index]
