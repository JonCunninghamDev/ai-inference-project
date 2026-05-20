"""Unit tests for dashboard data loading and aggregation."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_inference.dashboard import compute_stats, load_metrics


@pytest.fixture
def sample_metrics(tmp_path):
    path = tmp_path / "metrics.jsonl"
    now = datetime.now(timezone.utc).isoformat()
    events = [
        {"timestamp": now, "metric": "request_accepted", "component": "gateway", "model": "small", "event_type": "general_inference", "request_id": "r1"},
        {"timestamp": now, "metric": "request_accepted", "component": "gateway", "model": "small", "event_type": "general_inference", "request_id": "r2"},
        {"timestamp": now, "metric": "request_accepted", "component": "gateway", "model": "large", "event_type": "code_generation", "request_id": "r3"},
        {"timestamp": now, "metric": "inference_completed", "component": "worker", "model": "small", "request_id": "r1", "duration_ms": 150},
        {"timestamp": now, "metric": "inference_completed", "component": "worker", "model": "small", "request_id": "r2", "duration_ms": 200},
        {"timestamp": now, "metric": "inference_failed", "component": "worker", "model": "large", "request_id": "r3", "error": "timeout"},
        {"timestamp": now, "metric": "queue_wait_time", "component": "worker", "request_id": "r1", "wait_ms": 50},
        {"timestamp": now, "metric": "queue_wait_time", "component": "worker", "request_id": "r2", "wait_ms": 80},
    ]
    with open(path, "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    return path


class TestLoadMetrics:
    def test_loads_valid_jsonl(self, sample_metrics):
        events = load_metrics(sample_metrics)
        assert len(events) == 8

    def test_missing_file_returns_empty(self, tmp_path):
        events = load_metrics(tmp_path / "nonexistent.jsonl")
        assert events == []

    def test_handles_malformed_lines(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text('{"valid": true}\nnot json\n{"also": "valid"}\n')
        events = load_metrics(path)
        assert len(events) == 2


class TestComputeStats:
    def test_total_requests(self, sample_metrics):
        events = load_metrics(sample_metrics)
        stats = compute_stats(events)
        assert stats["total_requests"] == 3

    def test_completed_and_failed(self, sample_metrics):
        events = load_metrics(sample_metrics)
        stats = compute_stats(events)
        assert stats["completed"] == 2
        assert stats["failed"] == 1

    def test_avg_duration(self, sample_metrics):
        events = load_metrics(sample_metrics)
        stats = compute_stats(events)
        assert stats["avg_duration_ms"] == 175.0  # (150 + 200) / 2

    def test_model_breakdown(self, sample_metrics):
        events = load_metrics(sample_metrics)
        stats = compute_stats(events)
        assert stats["model_breakdown"]["small"] == 2
        assert stats["model_breakdown"]["large"] == 1

    def test_queue_wait(self, sample_metrics):
        events = load_metrics(sample_metrics)
        stats = compute_stats(events)
        assert stats["avg_queue_wait_ms"] == 65.0  # (50 + 80) / 2

    def test_empty_events(self):
        stats = compute_stats([])
        assert stats["total_requests"] == 0
        assert stats["avg_duration_ms"] == 0.0
