"""
Observability metrics for the secure inference platform.

Emits structured metric events at key lifecycle points. Supports a local
JSONL sink for air-gapped environments and a protocol boundary for
CloudWatch or Prometheus backends.

Usage:
    from ai_inference.core.metrics import MetricsCollector, JsonlMetricsSink

    sink = JsonlMetricsSink("/var/log/inference-metrics.jsonl")
    metrics = MetricsCollector(sink)

    metrics.record_request_accepted(request_id="abc", model="demo-small", event_type="general")
    metrics.record_inference_completed(request_id="abc", model="demo-small", duration_ms=152)
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol


# ---------------------------------------------------------------------------
# Metric event
# ---------------------------------------------------------------------------


@dataclass
class MetricEvent:
    """A single quantitative observation."""

    timestamp: str
    event_type: str
    component: str
    fields: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        base = {"timestamp": self.timestamp, "metric": self.event_type, "component": self.component}
        base.update(self.fields)
        return base


# ---------------------------------------------------------------------------
# Sink protocol and implementations
# ---------------------------------------------------------------------------


class MetricsSink(Protocol):
    def emit(self, event: MetricEvent) -> None: ...


class JsonlMetricsSink:
    """Appends metric events as newline-delimited JSON to a local file.

    Suitable for air-gapped environments where CloudWatch is unavailable.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: MetricEvent) -> None:
        with open(self._path, "a") as f:
            f.write(json.dumps(event.to_dict(), default=str) + "\n")


class InMemoryMetricsSink:
    """Collects events in memory. Useful for testing and demo mode."""

    def __init__(self) -> None:
        self.events: List[MetricEvent] = []

    def emit(self, event: MetricEvent) -> None:
        self.events.append(event)


class NullMetricsSink:
    """Discards all events. Use when metrics are disabled."""

    def emit(self, event: MetricEvent) -> None:
        pass


# ---------------------------------------------------------------------------
# Collector — the interface components use
# ---------------------------------------------------------------------------


class MetricsCollector:
    """Emits metric events to a configured sink."""

    def __init__(self, sink: Optional[MetricsSink] = None) -> None:
        self._sink: MetricsSink = sink or NullMetricsSink()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _emit(self, metric_name: str, component: str, **fields: Any) -> None:
        self._sink.emit(MetricEvent(
            timestamp=self._now(),
            event_type=metric_name,
            component=component,
            fields=fields,
        ))

    # --- Gateway metrics ---

    def record_request_accepted(self, request_id: str, model: str, event_type: str, estimated_tokens: int) -> None:
        self._emit("request_accepted", "gateway",
                   request_id=request_id, model=model, event_type=event_type, estimated_tokens=estimated_tokens)

    def record_request_rejected(self, reason: str) -> None:
        self._emit("request_rejected", "gateway", reason=reason)

    # --- Worker / inference metrics ---

    def record_inference_started(self, request_id: str, model: str, batch_id: str) -> None:
        self._emit("inference_started", "worker",
                   request_id=request_id, model=model, batch_id=batch_id)

    def record_inference_completed(self, request_id: str, model: str, duration_ms: float) -> None:
        self._emit("inference_completed", "worker",
                   request_id=request_id, model=model, duration_ms=duration_ms)

    def record_inference_failed(self, request_id: str, model: str, error: str) -> None:
        self._emit("inference_failed", "worker",
                   request_id=request_id, model=model, error=error)

    # --- Batch metrics ---

    def record_batch_built(self, batch_id: str, model: str, size: int, total_tokens: int, reason: str) -> None:
        self._emit("batch_built", "worker",
                   batch_id=batch_id, model=model, size=size, total_tokens=total_tokens, reason=reason)

    # --- GPU scheduling metrics ---

    def record_scheduling_decision(self, batch_id: str, model: str, scheduled: bool, device_id: Optional[str] = None, reason: str = "") -> None:
        self._emit("scheduling_decision", "scheduler",
                   batch_id=batch_id, model=model, scheduled=scheduled, device_id=device_id, reason=reason)

    # --- Reconciliation metrics ---

    def record_reconciliation_pass(self, stale_count: int, healed_count: int, failed_count: int, notified_count: int) -> None:
        self._emit("reconciliation_pass", "reconciliation",
                   stale_count=stale_count, healed_count=healed_count, failed_count=failed_count, notified_count=notified_count)

    # --- Latency metrics ---

    def record_queue_wait_time(self, request_id: str, wait_ms: float) -> None:
        self._emit("queue_wait_time", "worker", request_id=request_id, wait_ms=wait_ms)
