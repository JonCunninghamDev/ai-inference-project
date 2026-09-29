"""Observability metrics for the secure inference platform.

Emits structured metric events at key lifecycle points. Supports JSONL,
in-memory, and Prometheus-compatible sinks without coupling platform logic to
one telemetry backend.
"""
from __future__ import annotations

import json
import math
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Tuple


PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@dataclass
class MetricEvent:
    """A single quantitative observation."""

    timestamp: str
    event_type: str
    component: str
    fields: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        base = {
            "timestamp": self.timestamp,
            "metric": self.event_type,
            "component": self.component,
        }
        base.update(self.fields)
        return base


class MetricsSink(Protocol):
    def emit(self, event: MetricEvent) -> None: ...


class JsonlMetricsSink:
    """Appends metric events as newline-delimited JSON to a local file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: MetricEvent) -> None:
        with open(self._path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), default=str) + "\n")


class InMemoryMetricsSink:
    """Collects events in memory. Useful for testing and demo mode."""

    def __init__(self) -> None:
        self.events: List[MetricEvent] = []

    def emit(self, event: MetricEvent) -> None:
        self.events.append(event)


class NullMetricsSink:
    """Discards all events. Use when metrics are disabled."""

    def emit(self, event: MetricEvent) -> None:
        del event


class CompositeMetricsSink:
    """Fan out each event to multiple sinks."""

    def __init__(self, sinks: Iterable[MetricsSink]) -> None:
        self._sinks = tuple(sinks)

    def emit(self, event: MetricEvent) -> None:
        for sink in self._sinks:
            sink.emit(event)

    def render_prometheus(self) -> str:
        rendered: List[str] = []
        for sink in self._sinks:
            renderer = getattr(sink, "render_prometheus", None)
            if callable(renderer):
                payload = renderer().strip()
                if payload:
                    rendered.append(payload)
        if not rendered:
            return ""
        return "\n".join(rendered) + "\n"


LabelSet = Tuple[Tuple[str, str], ...]


def _escape_label(value: object) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )


def _label_set(labels: Mapping[str, object]) -> LabelSet:
    return tuple(sorted((key, str(value)) for key, value in labels.items()))


def _format_labels(labels: LabelSet, extra: Mapping[str, object] | None = None) -> str:
    merged = dict(labels)
    if extra:
        merged.update({key: str(value) for key, value in extra.items()})
    if not merged:
        return ""
    body = ",".join(
        f'{key}="{_escape_label(value)}"' for key, value in sorted(merged.items())
    )
    return "{" + body + "}"


class _Histogram:
    def __init__(self, buckets: Iterable[float]) -> None:
        ordered = sorted({float(value) for value in buckets})
        self.buckets = tuple(ordered)
        self.counts = [0 for _ in self.buckets]
        self.count = 0
        self.total = 0.0

    def observe(self, value: float) -> None:
        numeric = float(value)
        self.count += 1
        self.total += numeric
        for index, boundary in enumerate(self.buckets):
            if numeric <= boundary:
                self.counts[index] += 1


class PrometheusMetricsSink:
    """Aggregate bounded platform events into Prometheus text exposition.

    Request IDs and other unbounded identifiers are deliberately excluded from
    labels to prevent high-cardinality time series.
    """

    _LATENCY_BUCKETS = (
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
        60.0,
    )
    _BATCH_SIZE_BUCKETS = (1, 2, 4, 8, 16, 32, 64)
    _TOKEN_BUCKETS = (128, 512, 1024, 4096, 8192, 16384, 32768, 65536)

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, Dict[LabelSet, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._histograms: Dict[str, Dict[LabelSet, _Histogram]] = defaultdict(dict)

    def _inc(self, name: str, labels: Mapping[str, object], value: float = 1.0) -> None:
        self._counters[name][_label_set(labels)] += float(value)

    def _observe(
        self,
        name: str,
        labels: Mapping[str, object],
        value: float,
        buckets: Iterable[float],
    ) -> None:
        key = _label_set(labels)
        histogram = self._histograms[name].get(key)
        if histogram is None:
            histogram = _Histogram(buckets)
            self._histograms[name][key] = histogram
        histogram.observe(float(value))

    def emit(self, event: MetricEvent) -> None:
        fields = event.fields
        with self._lock:
            if event.event_type == "request_accepted":
                self._inc(
                    "ai_inference_gateway_requests_total",
                    {
                        "outcome": "accepted",
                        "model": fields.get("model", ""),
                        "event_type": fields.get("event_type", ""),
                    },
                )
            elif event.event_type == "request_rejected":
                self._inc(
                    "ai_inference_gateway_requests_total",
                    {
                        "outcome": "rejected",
                        "model": "",
                        "event_type": "",
                    },
                )
            elif event.event_type == "inference_completed":
                model = fields.get("model", "")
                self._inc(
                    "ai_inference_worker_requests_total",
                    {"outcome": "completed", "model": model},
                )
                self._observe(
                    "ai_inference_inference_duration_seconds",
                    {"model": model},
                    float(fields.get("duration_ms", 0.0)) / 1000.0,
                    self._LATENCY_BUCKETS,
                )
            elif event.event_type == "inference_failed":
                self._inc(
                    "ai_inference_worker_requests_total",
                    {
                        "outcome": "failed",
                        "model": fields.get("model", ""),
                    },
                )
            elif event.event_type == "queue_wait_time":
                self._observe(
                    "ai_inference_queue_wait_seconds",
                    {},
                    float(fields.get("wait_ms", 0.0)) / 1000.0,
                    self._LATENCY_BUCKETS,
                )
            elif event.event_type == "batch_built":
                labels = {
                    "model": fields.get("model", ""),
                    "reason": fields.get("reason", ""),
                }
                self._observe(
                    "ai_inference_batch_size",
                    labels,
                    float(fields.get("size", 0)),
                    self._BATCH_SIZE_BUCKETS,
                )
                self._observe(
                    "ai_inference_batch_estimated_tokens",
                    labels,
                    float(fields.get("total_tokens", 0)),
                    self._TOKEN_BUCKETS,
                )
            elif event.event_type == "scheduling_decision":
                self._inc(
                    "ai_inference_scheduling_decisions_total",
                    {
                        "model": fields.get("model", ""),
                        "scheduled": str(bool(fields.get("scheduled"))).lower(),
                    },
                )
            elif event.event_type == "reconciliation_pass":
                for outcome, field_name in (
                    ("stale", "stale_count"),
                    ("healed", "healed_count"),
                    ("failed", "failed_count"),
                    ("notified", "notified_count"),
                ):
                    self._inc(
                        "ai_inference_reconciliation_requests_total",
                        {"outcome": outcome},
                        float(fields.get(field_name, 0)),
                    )

    @staticmethod
    def _counter_help(name: str) -> str:
        return {
            "ai_inference_gateway_requests_total": "Gateway requests by outcome.",
            "ai_inference_worker_requests_total": "Worker inference requests by terminal outcome.",
            "ai_inference_scheduling_decisions_total": "GPU scheduling decisions.",
            "ai_inference_reconciliation_requests_total": "Requests observed by reconciliation passes.",
        }.get(name, name)

    @staticmethod
    def _histogram_help(name: str) -> str:
        return {
            "ai_inference_inference_duration_seconds": "Worker-side model inference duration.",
            "ai_inference_queue_wait_seconds": "Time spent waiting before inference execution.",
            "ai_inference_batch_size": "Number of requests in a platform-built batch.",
            "ai_inference_batch_estimated_tokens": "Estimated tokens in a platform-built batch.",
        }.get(name, name)

    def render_prometheus(self) -> str:
        """Render the current aggregate in Prometheus text format 0.0.4."""
        lines: List[str] = []
        with self._lock:
            for name in sorted(self._counters):
                lines.append(f"# HELP {name} {self._counter_help(name)}")
                lines.append(f"# TYPE {name} counter")
                for labels, value in sorted(self._counters[name].items()):
                    lines.append(f"{name}{_format_labels(labels)} {value:g}")

            for name in sorted(self._histograms):
                lines.append(f"# HELP {name} {self._histogram_help(name)}")
                lines.append(f"# TYPE {name} histogram")
                for labels, histogram in sorted(self._histograms[name].items()):
                    for boundary, count in zip(
                        histogram.buckets, histogram.counts, strict=True
                    ):
                        boundary_text = f"{boundary:g}"
                        lines.append(
                            f"{name}_bucket"
                            f"{_format_labels(labels, {'le': boundary_text})} {count}"
                        )
                    lines.append(
                        f"{name}_bucket{_format_labels(labels, {'le': '+Inf'})} "
                        f"{histogram.count}"
                    )
                    lines.append(
                        f"{name}_count{_format_labels(labels)} {histogram.count}"
                    )
                    total = histogram.total
                    if math.isfinite(total):
                        lines.append(
                            f"{name}_sum{_format_labels(labels)} {total:g}"
                        )

        if not lines:
            return ""
        return "\n".join(lines) + "\n"


class MetricsCollector:
    """Emits metric events to a configured sink."""

    def __init__(self, sink: Optional[MetricsSink] = None) -> None:
        self._sink: MetricsSink = sink or NullMetricsSink()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _emit(self, metric_name: str, component: str, **fields: Any) -> None:
        self._sink.emit(
            MetricEvent(
                timestamp=self._now(),
                event_type=metric_name,
                component=component,
                fields=fields,
            )
        )

    def render_prometheus(self) -> str:
        renderer = getattr(self._sink, "render_prometheus", None)
        if not callable(renderer):
            return ""
        return str(renderer())

    def record_request_accepted(
        self, request_id: str, model: str, event_type: str, estimated_tokens: int
    ) -> None:
        self._emit(
            "request_accepted",
            "gateway",
            request_id=request_id,
            model=model,
            event_type=event_type,
            estimated_tokens=estimated_tokens,
        )

    def record_request_rejected(self, reason: str) -> None:
        self._emit("request_rejected", "gateway", reason=reason)

    def record_inference_started(
        self, request_id: str, model: str, batch_id: str
    ) -> None:
        self._emit(
            "inference_started",
            "worker",
            request_id=request_id,
            model=model,
            batch_id=batch_id,
        )

    def record_inference_completed(
        self, request_id: str, model: str, duration_ms: float
    ) -> None:
        self._emit(
            "inference_completed",
            "worker",
            request_id=request_id,
            model=model,
            duration_ms=duration_ms,
        )

    def record_inference_failed(
        self, request_id: str, model: str, error: str
    ) -> None:
        self._emit(
            "inference_failed",
            "worker",
            request_id=request_id,
            model=model,
            error=error,
        )

    def record_batch_built(
        self,
        batch_id: str,
        model: str,
        size: int,
        total_tokens: int,
        reason: str,
    ) -> None:
        self._emit(
            "batch_built",
            "worker",
            batch_id=batch_id,
            model=model,
            size=size,
            total_tokens=total_tokens,
            reason=reason,
        )

    def record_scheduling_decision(
        self,
        batch_id: str,
        model: str,
        scheduled: bool,
        device_id: Optional[str] = None,
        reason: str = "",
    ) -> None:
        self._emit(
            "scheduling_decision",
            "scheduler",
            batch_id=batch_id,
            model=model,
            scheduled=scheduled,
            device_id=device_id,
            reason=reason,
        )

    def record_reconciliation_pass(
        self,
        stale_count: int,
        healed_count: int,
        failed_count: int,
        notified_count: int,
    ) -> None:
        self._emit(
            "reconciliation_pass",
            "reconciliation",
            stale_count=stale_count,
            healed_count=healed_count,
            failed_count=failed_count,
            notified_count=notified_count,
        )

    def record_queue_wait_time(self, request_id: str, wait_ms: float) -> None:
        self._emit(
            "queue_wait_time",
            "worker",
            request_id=request_id,
            wait_ms=wait_ms,
        )
