"""Tests for observability metrics."""
import json
import tempfile
from pathlib import Path

from ai_inference.core.metrics import (
    InMemoryMetricsSink,
    JsonlMetricsSink,
    MetricsCollector,
    NullMetricsSink,
)


def _collector() -> tuple[MetricsCollector, InMemoryMetricsSink]:
    sink = InMemoryMetricsSink()
    return MetricsCollector(sink), sink


# --- Sink tests ---


def test_null_sink_does_not_crash():
    collector = MetricsCollector(NullMetricsSink())
    collector.record_request_accepted(request_id="r1", model="m", event_type="e", estimated_tokens=10)


def test_in_memory_sink_collects_events():
    collector, sink = _collector()
    collector.record_request_accepted(request_id="r1", model="m", event_type="e", estimated_tokens=10)
    assert len(sink.events) == 1
    assert sink.events[0].event_type == "request_accepted"


def test_jsonl_sink_writes_to_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "metrics.jsonl"
        sink = JsonlMetricsSink(path)
        collector = MetricsCollector(sink)

        collector.record_request_accepted(request_id="r1", model="m", event_type="e", estimated_tokens=5)
        collector.record_inference_completed(request_id="r1", model="m", duration_ms=100.5)

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["metric"] == "request_accepted"
        assert first["request_id"] == "r1"
        second = json.loads(lines[1])
        assert second["duration_ms"] == 100.5


# --- Gateway metrics ---


def test_request_accepted_fields():
    collector, sink = _collector()
    collector.record_request_accepted(request_id="r1", model="demo-small", event_type="security_review", estimated_tokens=42)

    event = sink.events[0]
    assert event.component == "gateway"
    d = event.to_dict()
    assert d["model"] == "demo-small"
    assert d["estimated_tokens"] == 42
    assert "timestamp" in d


def test_request_rejected():
    collector, sink = _collector()
    collector.record_request_rejected(reason="validation_error")
    assert sink.events[0].fields["reason"] == "validation_error"


# --- Inference metrics ---


def test_inference_started():
    collector, sink = _collector()
    collector.record_inference_started(request_id="r1", model="m", batch_id="b1")
    assert sink.events[0].event_type == "inference_started"
    assert sink.events[0].fields["batch_id"] == "b1"


def test_inference_completed():
    collector, sink = _collector()
    collector.record_inference_completed(request_id="r1", model="m", duration_ms=250.0)
    assert sink.events[0].fields["duration_ms"] == 250.0


def test_inference_failed():
    collector, sink = _collector()
    collector.record_inference_failed(request_id="r1", model="m", error="timeout")
    assert sink.events[0].fields["error"] == "timeout"


# --- Batch metrics ---


def test_batch_built():
    collector, sink = _collector()
    collector.record_batch_built(batch_id="b1", model="m", size=4, total_tokens=8000, reason="compatible")
    d = sink.events[0].to_dict()
    assert d["size"] == 4
    assert d["total_tokens"] == 8000
    assert d["component"] == "worker"


# --- Scheduling metrics ---


def test_scheduling_decision_scheduled():
    collector, sink = _collector()
    collector.record_scheduling_decision(batch_id="b1", model="m", scheduled=True, device_id="gpu-0", reason="capacity_available")
    d = sink.events[0].to_dict()
    assert d["scheduled"] is True
    assert d["device_id"] == "gpu-0"
    assert d["component"] == "scheduler"


def test_scheduling_decision_deferred():
    collector, sink = _collector()
    collector.record_scheduling_decision(batch_id="b1", model="m", scheduled=False, reason="memory_exceeded")
    assert sink.events[0].fields["scheduled"] is False


# --- Reconciliation metrics ---


def test_reconciliation_pass():
    collector, sink = _collector()
    collector.record_reconciliation_pass(stale_count=5, healed_count=3, failed_count=1, notified_count=1)
    d = sink.events[0].to_dict()
    assert d["stale_count"] == 5
    assert d["healed_count"] == 3
    assert d["component"] == "reconciliation"


# --- Queue wait time ---


def test_queue_wait_time():
    collector, sink = _collector()
    collector.record_queue_wait_time(request_id="r1", wait_ms=1200.0)
    assert sink.events[0].fields["wait_ms"] == 1200.0
    assert sink.events[0].component == "worker"


# --- Default collector uses NullSink ---


def test_default_collector_no_sink():
    collector = MetricsCollector()
    # Should not raise
    collector.record_request_accepted(request_id="r1", model="m", event_type="e", estimated_tokens=1)
