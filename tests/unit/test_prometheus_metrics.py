from __future__ import annotations

from fastapi.testclient import TestClient

from ai_inference.core.metrics import MetricsCollector, PrometheusMetricsSink
from ai_inference.gateway.api import GatewaySettings, create_app


class StubPublisher:
    def publish(self, payload):
        self.payload = payload


def test_prometheus_sink_exposes_bounded_counters_and_histograms() -> None:
    sink = PrometheusMetricsSink()
    metrics = MetricsCollector(sink)

    metrics.record_request_accepted(
        request_id="request-secret-123",
        model="model-a",
        event_type="benchmark",
        estimated_tokens=500,
    )
    metrics.record_inference_completed(
        request_id="request-secret-123",
        model="model-a",
        duration_ms=250.0,
    )
    metrics.record_queue_wait_time(
        request_id="request-secret-123",
        wait_ms=125.0,
    )
    metrics.record_inference_failed(
        request_id="request-secret-456",
        model="model-a",
        error="dynamic downstream error with request-specific detail",
    )

    payload = metrics.render_prometheus()

    assert "# TYPE ai_inference_gateway_requests_total counter" in payload
    assert "# TYPE ai_inference_inference_duration_seconds histogram" in payload
    assert "ai_inference_queue_wait_seconds_bucket" in payload
    assert 'outcome="accepted"' in payload
    assert 'outcome="failed"' in payload

    assert "request-secret-123" not in payload
    assert "request-secret-456" not in payload
    assert "dynamic downstream error" not in payload


def test_prometheus_histogram_buckets_are_cumulative() -> None:
    sink = PrometheusMetricsSink()
    metrics = MetricsCollector(sink)

    metrics.record_inference_completed("r1", "model-a", 50.0)
    metrics.record_inference_completed("r2", "model-a", 1500.0)

    payload = metrics.render_prometheus()

    assert (
        'ai_inference_inference_duration_seconds_bucket'
        '{le="0.05",model="model-a"} 1'
    ) in payload
    assert (
        'ai_inference_inference_duration_seconds_bucket'
        '{le="2.5",model="model-a"} 2'
    ) in payload
    assert (
        'ai_inference_inference_duration_seconds_count{model="model-a"} 2'
    ) in payload


def test_gateway_metrics_endpoint_returns_prometheus_text() -> None:
    sink = PrometheusMetricsSink()
    metrics = MetricsCollector(sink)
    metrics.record_request_accepted(
        request_id="r1",
        model="demo-small",
        event_type="benchmark",
        estimated_tokens=10,
    )

    app = create_app(
        settings=GatewaySettings(
            queue_url="in-process://test",
            default_model="demo-small",
        ),
        publisher=StubPublisher(),
        metrics=metrics,
    )
    client = TestClient(app)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "version=0.0.4" in response.headers["content-type"]
    assert "ai_inference_gateway_requests_total" in response.text
