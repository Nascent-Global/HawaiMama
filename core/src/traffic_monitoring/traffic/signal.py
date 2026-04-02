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
    next_lane: str | None = None
    decision_scores: dict[str, float] | None = None
    emergency_override: bool = False

    def to_dict(self) -> dict[str, str | float | dict[str, float] | None]:
        payload: dict[str, str | float | dict[str, float] | None] = {
            "active_lane": self.active_lane,
            "state": self.state.value,
            "time_remaining": round(self.time_remaining, 2),
        }
        if self.next_lane is not None:
            payload["next_lane"] = self.next_lane
        if self.decision_scores is not None:
            payload["decision_scores"] = {
                lane: round(score, 2) for lane, score in self.decision_scores.items()
            }
        payload["emergency_override"] = self.emergency_override
        return payload


class SignalStateMachine:
    def __init__(
        self,
        lane_order: list[str],
        *,
        initial_active_lane: str,
        min_green_time: float,
        max_green_time: float,
        yellow_time: float,
        priority_queue_weight: float,
        priority_wait_weight: float,
        fairness_weight: float,
        max_priority_score: float,
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
        self.priority_queue_weight = priority_queue_weight
        self.priority_wait_weight = priority_wait_weight
        self.fairness_weight = fairness_weight
        self.max_priority_score = max_priority_score
        self.last_served_at_seconds = {lane: 0.0 for lane in self.lane_order}
        self.last_decision_scores: dict[str, float] = {}
        self.next_lane_candidate: str | None = None
        self.emergency_override_active = False

    def update(
        self,
        timestamp_seconds: float,
        lane_metrics: dict[str, dict[str, float | int]],
        emergency_lane: str | None = None,
    ) -> SignalSnapshot:
        elapsed = max(0.0, timestamp_seconds - self.state_started_at_seconds)

        if emergency_lane is not None:
            if emergency_lane == self.current_active_lane:
                self.emergency_override_active = True
            elif self.current_state == SignalState.GREEN:
                self.next_lane_candidate = emergency_lane
                self.current_state = SignalState.YELLOW
                self.state_started_at_seconds = timestamp_seconds
                elapsed = 0.0
                self.emergency_override_active = True
            elif self.current_state == SignalState.YELLOW:
                self.next_lane_candidate = emergency_lane
                self.emergency_override_active = True

        if self.current_state == SignalState.GREEN:
            if elapsed >= self.max_green_time:
                self.next_lane_candidate = self._select_next_lane(timestamp_seconds, lane_metrics)
                self.current_state = SignalState.YELLOW
                self.state_started_at_seconds = timestamp_seconds
                elapsed = 0.0
                self.emergency_override_active = False
        elif self.current_state == SignalState.YELLOW:
            if elapsed >= self.yellow_time:
                self.current_active_lane = self.next_lane_candidate or self._next_lane()
                self.last_served_at_seconds[self.current_active_lane] = timestamp_seconds
                self.current_state = SignalState.GREEN
                self.state_started_at_seconds = timestamp_seconds
                if emergency_lane is None or self.current_active_lane != emergency_lane:
                    self.emergency_override_active = False
                self.next_lane_candidate = None
                elapsed = 0.0

        time_remaining = self._time_remaining(timestamp_seconds)
        return SignalSnapshot(
            active_lane=self.current_active_lane,
            state=self.current_state,
            time_remaining=time_remaining,
            next_lane=self.next_lane_candidate,
            decision_scores=self.last_decision_scores or None,
            emergency_override=self.emergency_override_active,
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

    def _select_next_lane(
        self,
        timestamp_seconds: float,
        lane_metrics: dict[str, dict[str, float | int]],
    ) -> str:
        scores: dict[str, float] = {}
        for lane in self.lane_order:
            metrics = lane_metrics.get(lane, {})
            queue_length = float(metrics.get("queue", 0))
            avg_wait_time = float(metrics.get("avg_wait", 0.0))
            starvation_bonus = max(
                0.0,
                timestamp_seconds - self.last_served_at_seconds.get(lane, 0.0),
            ) * self.fairness_weight
            raw_score = (
                self.priority_queue_weight * queue_length
                + self.priority_wait_weight * avg_wait_time
                + starvation_bonus
            )
            scores[lane] = min(raw_score, self.max_priority_score)

        self.last_decision_scores = scores
        return max(
            self.lane_order,
            key=lambda lane: (
                scores.get(lane, 0.0),
                lane != self.current_active_lane,
                -self.lane_order.index(lane),
            ),
        )
