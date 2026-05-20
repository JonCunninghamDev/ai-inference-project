"""
Reconciliation scheduler for the secure inference platform.

Runs the reconciliation engine periodically in a background thread.
Can be started in demo mode or as a standalone process.

Usage:
    from ai_inference.core.reconciliation_scheduler import ReconciliationScheduler

    scheduler = ReconciliationScheduler(engine, interval_seconds=30)
    scheduler.start()   # non-blocking, runs in background thread
    scheduler.stop()    # graceful shutdown
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from ai_inference.core.logging import get_logger
from ai_inference.core.metrics import MetricsCollector
from ai_inference.core.reconciliation import ReconciliationEngine

logger = get_logger("reconciliation_scheduler")


class ReconciliationScheduler:
    """Runs reconciliation on a fixed interval in a background thread."""

    def __init__(
        self,
        engine: ReconciliationEngine,
        interval_seconds: float = 30.0,
        metrics: Optional[MetricsCollector] = None,
    ) -> None:
        self.engine = engine
        self.interval_seconds = interval_seconds
        self._metrics = metrics or MetricsCollector()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._pass_count = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def pass_count(self) -> int:
        return self._pass_count

    def start(self) -> None:
        """Start the scheduler in a background daemon thread."""
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="reconciliation-scheduler")
        self._thread.start()
        logger.info("scheduler started", interval_seconds=self.interval_seconds)

    def stop(self) -> None:
        """Signal the scheduler to stop and wait for it."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self.interval_seconds + 1)
            logger.info("scheduler stopped", total_passes=self._pass_count)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                events = self.engine.run_once()
                self._pass_count += 1
                stale = len(events)
                healed = sum(1 for e in events if not e.dry_run and e.action.value != "skip")
                failed = sum(1 for e in events if e.action.value == "mark_failed" and not e.dry_run)
                notified = sum(1 for e in events if e.notified)
                self._metrics.record_reconciliation_pass(
                    stale_count=stale, healed_count=healed,
                    failed_count=failed, notified_count=notified,
                )
                if stale > 0:
                    logger.info(
                        "reconciliation pass complete",
                        stale_count=stale, healed_count=healed,
                        failed_count=failed, notified_count=notified,
                    )
            except Exception as e:
                logger.error("reconciliation pass failed", error=str(e))

            self._stop_event.wait(self.interval_seconds)
