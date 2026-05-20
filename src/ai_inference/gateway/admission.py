"""
Admission control for the secure inference platform.

Decides whether the gateway should accept, defer, or reject incoming
requests based on current system load signals. This prevents unbounded
work accumulation when the worker fleet cannot keep up.

All thresholds are configurable and default to permissive values.
Admission decisions are logged and metriced.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ai_inference.core.logging import get_logger
from ai_inference.core.metrics import MetricsCollector

logger = get_logger("admission")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class AdmissionPolicy:
    """Thresholds that control when the gateway rejects work."""

    max_queue_depth: int = 100
    max_pending_requests: int = 50
    max_processing_requests: int = 20
    enabled: bool = True


# ---------------------------------------------------------------------------
# Decision types
# ---------------------------------------------------------------------------


class AdmissionDecision(str, Enum):
    ADMIT = "admit"
    REJECT_QUEUE_DEPTH = "reject_queue_depth"
    REJECT_PENDING = "reject_pending"
    REJECT_PROCESSING = "reject_processing"
    DISABLED = "disabled"


@dataclass
class AdmissionResult:
    decision: AdmissionDecision
    reason: str
    retry_after_seconds: Optional[int] = None


# ---------------------------------------------------------------------------
# Load snapshot — what the admission controller observes
# ---------------------------------------------------------------------------


@dataclass
class SystemLoad:
    """Current system load signals. Populated by the caller."""

    queue_depth: int = 0
    pending_count: int = 0
    processing_count: int = 0


# ---------------------------------------------------------------------------
# Admission controller
# ---------------------------------------------------------------------------


class AdmissionController:
    """Evaluates whether a new request should be accepted."""

    def __init__(self, policy: Optional[AdmissionPolicy] = None, metrics: Optional[MetricsCollector] = None) -> None:
        self.policy = policy or AdmissionPolicy()
        self._metrics = metrics or MetricsCollector()

    def check(self, load: SystemLoad) -> AdmissionResult:
        if not self.policy.enabled:
            return AdmissionResult(decision=AdmissionDecision.DISABLED, reason="Admission control disabled")

        if load.queue_depth >= self.policy.max_queue_depth:
            result = AdmissionResult(
                decision=AdmissionDecision.REJECT_QUEUE_DEPTH,
                reason=f"Queue depth {load.queue_depth} exceeds limit {self.policy.max_queue_depth}",
                retry_after_seconds=10,
            )
            self._log_and_metric(result, load)
            return result

        if load.pending_count >= self.policy.max_pending_requests:
            result = AdmissionResult(
                decision=AdmissionDecision.REJECT_PENDING,
                reason=f"Pending requests {load.pending_count} exceeds limit {self.policy.max_pending_requests}",
                retry_after_seconds=5,
            )
            self._log_and_metric(result, load)
            return result

        if load.processing_count >= self.policy.max_processing_requests:
            result = AdmissionResult(
                decision=AdmissionDecision.REJECT_PROCESSING,
                reason=f"Processing requests {load.processing_count} exceeds limit {self.policy.max_processing_requests}",
                retry_after_seconds=15,
            )
            self._log_and_metric(result, load)
            return result

        return AdmissionResult(decision=AdmissionDecision.ADMIT, reason="Within capacity")

    def _log_and_metric(self, result: AdmissionResult, load: SystemLoad) -> None:
        logger.warning(
            "request rejected",
            decision=result.decision.value,
            reason=result.reason,
            queue_depth=load.queue_depth,
            pending=load.pending_count,
            processing=load.processing_count,
        )
        self._metrics.record_request_rejected(reason=result.decision.value)
