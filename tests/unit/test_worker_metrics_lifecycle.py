from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from ai_inference.core.worker import RAGWorker


def test_worker_run_starts_and_cleanup_stops_metrics_server() -> None:
    worker = object.__new__(RAGWorker)
    worker.config = SimpleNamespace(
        aws_region="us-east-1",
        queue_url="https://example.invalid/queue",
        ssm_kill_switch="/test/kill-switch",
        health_check_enabled=False,
    )
    worker.logger = Mock()
    worker.metrics_server = Mock()
    worker.metrics_server.bound_host = "127.0.0.1"
    worker.metrics_server.bound_port = 9101
    worker.health = Mock()
    worker.health.get_status.return_value = {"healthy": True}
    worker.ai_client = None

    with patch("ai_inference.core.worker.shutdown_event") as shutdown:
        shutdown.is_set.return_value = True
        worker.run()

    worker.metrics_server.start.assert_called_once_with()
    worker.metrics_server.stop.assert_called_once_with()
