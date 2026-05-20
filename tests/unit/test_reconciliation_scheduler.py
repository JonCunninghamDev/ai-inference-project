"""Unit tests for the reconciliation scheduler."""
import time

import pytest

from ai_inference.core.metrics import InMemoryMetricsSink, MetricsCollector
from ai_inference.core.reconciliation import ReconciliationConfig, ReconciliationEngine
from ai_inference.core.reconciliation_scheduler import ReconciliationScheduler
from ai_inference.core.result_store import InMemoryResultStore


class TestReconciliationScheduler:
    def _make_scheduler(self, interval=0.05):
        store = InMemoryResultStore()
        config = ReconciliationConfig(dry_run_enabled=True, stale_pending_timeout_seconds=0)
        engine = ReconciliationEngine(config=config, result_store=store)
        sink = InMemoryMetricsSink()
        metrics = MetricsCollector(sink)
        scheduler = ReconciliationScheduler(engine, interval_seconds=interval, metrics=metrics)
        return scheduler, store, sink

    def test_start_and_stop(self):
        scheduler, _, _ = self._make_scheduler()
        scheduler.start()
        assert scheduler.running is True
        time.sleep(0.1)
        scheduler.stop()
        assert scheduler.running is False

    def test_runs_multiple_passes(self):
        scheduler, _, _ = self._make_scheduler(interval=0.02)
        scheduler.start()
        time.sleep(0.1)
        scheduler.stop()
        assert scheduler.pass_count >= 2

    def test_emits_metrics(self):
        scheduler, _, sink = self._make_scheduler(interval=0.02)
        scheduler.start()
        time.sleep(0.08)
        scheduler.stop()
        event_types = [e.event_type for e in sink.events]
        assert "reconciliation_pass" in event_types

    def test_idempotent_start(self):
        scheduler, _, _ = self._make_scheduler()
        scheduler.start()
        scheduler.start()  # Should not create a second thread
        assert scheduler.running is True
        scheduler.stop()

    def test_stop_without_start(self):
        scheduler, _, _ = self._make_scheduler()
        scheduler.stop()  # Should not raise
        assert scheduler.running is False
