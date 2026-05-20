"""Tests for admission control and backpressure."""
from fastapi.testclient import TestClient

from ai_inference.core.metrics import InMemoryMetricsSink, MetricsCollector
from ai_inference.core.result_store import InMemoryResultStore, InferenceResult, RequestStatus
from ai_inference.gateway.admission import (
    AdmissionController,
    AdmissionDecision,
    AdmissionPolicy,
    SystemLoad,
)
from ai_inference.gateway.api import GatewaySettings, create_app


# --- Unit tests for AdmissionController ---


def test_admit_when_within_capacity():
    controller = AdmissionController(AdmissionPolicy(max_queue_depth=100, max_pending_requests=50))
    result = controller.check(SystemLoad(queue_depth=10, pending_count=5, processing_count=2))
    assert result.decision == AdmissionDecision.ADMIT


def test_reject_queue_depth():
    controller = AdmissionController(AdmissionPolicy(max_queue_depth=10))
    result = controller.check(SystemLoad(queue_depth=10, pending_count=0, processing_count=0))
    assert result.decision == AdmissionDecision.REJECT_QUEUE_DEPTH
    assert result.retry_after_seconds == 10


def test_reject_pending():
    controller = AdmissionController(AdmissionPolicy(max_pending_requests=5))
    result = controller.check(SystemLoad(queue_depth=0, pending_count=5, processing_count=0))
    assert result.decision == AdmissionDecision.REJECT_PENDING
    assert result.retry_after_seconds == 5


def test_reject_processing():
    controller = AdmissionController(AdmissionPolicy(max_processing_requests=3))
    result = controller.check(SystemLoad(queue_depth=0, pending_count=0, processing_count=3))
    assert result.decision == AdmissionDecision.REJECT_PROCESSING
    assert result.retry_after_seconds == 15


def test_disabled_always_admits():
    controller = AdmissionController(AdmissionPolicy(enabled=False, max_queue_depth=0))
    result = controller.check(SystemLoad(queue_depth=999, pending_count=999, processing_count=999))
    assert result.decision == AdmissionDecision.DISABLED


def test_rejection_emits_metric():
    sink = InMemoryMetricsSink()
    metrics = MetricsCollector(sink)
    controller = AdmissionController(AdmissionPolicy(max_queue_depth=5), metrics=metrics)
    controller.check(SystemLoad(queue_depth=10))
    assert len(sink.events) == 1
    assert sink.events[0].event_type == "request_rejected"


def test_queue_depth_checked_first():
    """Queue depth is the first gate — even if pending/processing are also over."""
    controller = AdmissionController(AdmissionPolicy(max_queue_depth=5, max_pending_requests=5, max_processing_requests=5))
    result = controller.check(SystemLoad(queue_depth=10, pending_count=10, processing_count=10))
    assert result.decision == AdmissionDecision.REJECT_QUEUE_DEPTH


# --- Gateway integration tests ---


class FakePublisher:
    def __init__(self):
        self.messages = []

    def publish(self, payload):
        self.messages.append(payload)


def _build_client(policy=None):
    store = InMemoryResultStore()
    publisher = FakePublisher()
    settings = GatewaySettings(
        queue_url="https://sqs.us-east-1.amazonaws.com/123/inference",
        default_model="small-local",
        small_model="small-local",
        large_model="large-local",
        small_context_tokens=2048,
        large_context_tokens=32768,
    )
    admission = AdmissionController(policy or AdmissionPolicy())
    app = create_app(settings=settings, publisher=publisher, result_store=store, admission=admission)
    return TestClient(app), store, publisher


def test_gateway_admits_under_capacity():
    client, _, publisher = _build_client()
    resp = client.post("/v1/inference", json={"prompt": "hello"})
    assert resp.status_code == 202
    assert len(publisher.messages) == 1


def test_gateway_rejects_when_pending_exceeds_limit():
    client, store, publisher = _build_client(AdmissionPolicy(max_pending_requests=2))

    # Seed 2 pending requests
    for i in range(2):
        store.put(InferenceResult(request_id=f"r{i}", status=RequestStatus.PENDING, accepted_at="t"))

    resp = client.post("/v1/inference", json={"prompt": "hello"})
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert resp.headers["Retry-After"] == "5"
    assert len(publisher.messages) == 0


def test_gateway_admits_after_requests_complete():
    client, store, publisher = _build_client(AdmissionPolicy(max_pending_requests=2))

    # Seed 2 pending, then complete one
    store.put(InferenceResult(request_id="r0", status=RequestStatus.PENDING, accepted_at="t"))
    store.put(InferenceResult(request_id="r1", status=RequestStatus.COMPLETED, accepted_at="t"))

    resp = client.post("/v1/inference", json={"prompt": "hello"})
    assert resp.status_code == 202


def test_gateway_disabled_admission_always_accepts():
    client, store, _ = _build_client(AdmissionPolicy(enabled=False, max_pending_requests=0))

    # Even with impossible limits, disabled means accept
    store.put(InferenceResult(request_id="r0", status=RequestStatus.PENDING, accepted_at="t"))
    resp = client.post("/v1/inference", json={"prompt": "hello"})
    assert resp.status_code == 202
