from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from ai_inference.core.metrics import MetricsCollector, PrometheusMetricsSink
from ai_inference.core.worker_metrics_server import (
    WorkerMetricsServer,
    validate_private_bind_host,
)


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "127.0.0.2",
        "10.0.1.20",
        "172.16.1.20",
        "172.31.255.254",
        "192.168.10.10",
        "::1",
        "fd00::1",
    ],
)
def test_private_bind_hosts_are_allowed(host: str) -> None:
    assert validate_private_bind_host(host) == host


@pytest.mark.parametrize(
    "host",
    [
        "0.0.0.0",
        "::",
        "8.8.8.8",
        "1.1.1.1",
        "203.0.113.10",
        "worker.internal",
    ],
)
def test_wildcard_public_and_hostname_binds_are_rejected(host: str) -> None:
    with pytest.raises(ValueError):
        validate_private_bind_host(host)


def test_worker_metrics_server_exposes_metrics_only_on_metrics_path() -> None:
    metrics = MetricsCollector(PrometheusMetricsSink())
    metrics.record_inference_completed(
        request_id="request-id-must-not-be-a-label",
        model="test-model",
        duration_ms=125.0,
    )

    server = WorkerMetricsServer(metrics, host="127.0.0.1", port=0)
    server.start()

    try:
        assert server.running is True
        url = f"http://{server.bound_host}:{server.bound_port}/metrics"
        with urllib.request.urlopen(url, timeout=2) as response:
            payload = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/plain")
            assert "ai_inference_worker_requests_total" in payload
            assert "ai_inference_inference_duration_seconds" in payload
            assert "request-id-must-not-be-a-label" not in payload

        bad_url = f"http://{server.bound_host}:{server.bound_port}/health"
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(bad_url, timeout=2)
        assert exc.value.code == 404
    finally:
        server.stop()

    assert server.running is False


def test_worker_metrics_server_start_and_stop_are_idempotent() -> None:
    server = WorkerMetricsServer(
        MetricsCollector(PrometheusMetricsSink()),
        host="127.0.0.1",
        port=0,
    )

    server.start()
    port = server.bound_port
    server.start()
    assert server.bound_port == port
    assert server.running is True

    server.stop()
    server.stop()
    assert server.running is False
