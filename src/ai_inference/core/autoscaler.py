"""
Worker pool autoscaling for the secure inference platform.

Uses metrics signals (queue wait time, scheduling deferrals, worker
utilization) to make scaling decisions. Emits decisions as metrics
and logs for observability.

All scaling actions default to dry-run (log only, no actual scaling).
Enable execution by setting `dry_run=False` in the policy.

Usage:
    from ai_inference.core.autoscaler import AutoscalingPolicy, Autoscaler, ClusterState

    policy = AutoscalingPolicy(min_workers=1, max_workers=10, target_queue_wait_ms=2000)
    scaler = Autoscaler(policy)

    decision = scaler.evaluate(ClusterState(
        current_workers=2,
        avg_queue_wait_ms=5000,
        scheduling_deferrals=3,
        pending_count=20,
    ))
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ai_inference.core.logging import get_logger
from ai_inference.core.metrics import MetricsCollector

logger = get_logger("autoscaler")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class AutoscalingPolicy:
    """Controls when and how the worker pool scales."""

    min_workers: int = 1
    max_workers: int = 10
    target_queue_wait_ms: float = 2000.0
    target_utilization_percent: float = 70.0
    scale_up_threshold_deferrals: int = 2
    scale_down_idle_seconds: float = 120.0
    cooldown_seconds: float = 60.0
    dry_run: bool = True


# ---------------------------------------------------------------------------
# Decision types
# ---------------------------------------------------------------------------


class ScalingAction(str, Enum):
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    HOLD = "hold"


@dataclass
class ScalingDecision:
    action: ScalingAction
    reason: str
    current_workers: int
    desired_workers: int
    dry_run: bool


# ---------------------------------------------------------------------------
# Cluster state — what the autoscaler observes
# ---------------------------------------------------------------------------


@dataclass
class ClusterState:
    """Current cluster signals. Populated by the caller."""

    current_workers: int = 1
    avg_queue_wait_ms: float = 0.0
    scheduling_deferrals: int = 0
    pending_count: int = 0
    processing_count: int = 0
    idle_seconds: float = 0.0
    utilization_percent: float = 0.0


# ---------------------------------------------------------------------------
# Autoscaler
# ---------------------------------------------------------------------------


class Autoscaler:
    """Evaluates cluster state and produces scaling decisions."""

    def __init__(self, policy: Optional[AutoscalingPolicy] = None, metrics: Optional[MetricsCollector] = None) -> None:
        self.policy = policy or AutoscalingPolicy()
        self._metrics = metrics or MetricsCollector()
        self._last_scale_time: float = 0.0

    def _in_cooldown(self) -> bool:
        return (time.time() - self._last_scale_time) < self.policy.cooldown_seconds

    def evaluate(self, state: ClusterState) -> ScalingDecision:
        """Evaluate cluster state and return a scaling decision."""

        # Cooldown check
        if self._in_cooldown():
            return ScalingDecision(
                action=ScalingAction.HOLD,
                reason="In cooldown period",
                current_workers=state.current_workers,
                desired_workers=state.current_workers,
                dry_run=self.policy.dry_run,
            )

        # Scale up triggers
        if state.avg_queue_wait_ms > self.policy.target_queue_wait_ms:
            return self._scale_up(state, f"Queue wait {state.avg_queue_wait_ms:.0f}ms exceeds target {self.policy.target_queue_wait_ms:.0f}ms")

        if state.scheduling_deferrals >= self.policy.scale_up_threshold_deferrals:
            return self._scale_up(state, f"Scheduling deferrals {state.scheduling_deferrals} exceeds threshold {self.policy.scale_up_threshold_deferrals}")

        if state.utilization_percent > self.policy.target_utilization_percent:
            return self._scale_up(state, f"Utilization {state.utilization_percent:.0f}% exceeds target {self.policy.target_utilization_percent:.0f}%")

        # Scale down trigger
        if state.idle_seconds > self.policy.scale_down_idle_seconds and state.current_workers > self.policy.min_workers:
            return self._scale_down(state, f"Idle {state.idle_seconds:.0f}s exceeds threshold {self.policy.scale_down_idle_seconds:.0f}s")

        return ScalingDecision(
            action=ScalingAction.HOLD,
            reason="Within targets",
            current_workers=state.current_workers,
            desired_workers=state.current_workers,
            dry_run=self.policy.dry_run,
        )

    def _scale_up(self, state: ClusterState, reason: str) -> ScalingDecision:
        desired = min(state.current_workers + 1, self.policy.max_workers)
        if desired == state.current_workers:
            return ScalingDecision(
                action=ScalingAction.HOLD,
                reason=f"Already at max workers ({self.policy.max_workers})",
                current_workers=state.current_workers,
                desired_workers=state.current_workers,
                dry_run=self.policy.dry_run,
            )

        decision = ScalingDecision(
            action=ScalingAction.SCALE_UP,
            reason=reason,
            current_workers=state.current_workers,
            desired_workers=desired,
            dry_run=self.policy.dry_run,
        )
        self._record(decision)
        return decision

    def _scale_down(self, state: ClusterState, reason: str) -> ScalingDecision:
        desired = max(state.current_workers - 1, self.policy.min_workers)
        if desired == state.current_workers:
            return ScalingDecision(
                action=ScalingAction.HOLD,
                reason=f"Already at min workers ({self.policy.min_workers})",
                current_workers=state.current_workers,
                desired_workers=state.current_workers,
                dry_run=self.policy.dry_run,
            )

        decision = ScalingDecision(
            action=ScalingAction.SCALE_DOWN,
            reason=reason,
            current_workers=state.current_workers,
            desired_workers=desired,
            dry_run=self.policy.dry_run,
        )
        self._record(decision)
        return decision

    def _record(self, decision: ScalingDecision) -> None:
        self._last_scale_time = time.time()
        prefix = "[DRY RUN] " if decision.dry_run else ""
        logger.info(
            f"{prefix}scaling decision",
            action=decision.action.value,
            reason=decision.reason,
            current=decision.current_workers,
            desired=decision.desired_workers,
        )
        self._metrics._emit("scaling_decision", "autoscaler",
                            action=decision.action.value,
                            reason=decision.reason,
                            current_workers=decision.current_workers,
                            desired_workers=decision.desired_workers,
                            dry_run=decision.dry_run)
