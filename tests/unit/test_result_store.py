"""Tests for result store and retrieval endpoint."""
from fastapi.testclient import TestClient

from ai_inference.core.result_store import InferenceResult, InMemoryResultStore, RequestStatus
from ai_inference.gateway.api import GatewaySettings, create_app


class FakePublisher:
    def __init__(self):
        self.messages = []

    def publish(self, payload):
        self.messages.append(payload)


def build_client():
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
    app = create_app(settings=settings, publisher=publisher, result_store=store)
    return TestClient(app), store


# --- Result store unit tests ---


def test_store_put_and_get():
    store = InMemoryResultStore()
    record = InferenceResult(request_id="r1", status=RequestStatus.PENDING, accepted_at="2024-01-01T00:00:00Z")
    store.put(record)
    assert store.get("r1") == record


def test_store_get_missing_returns_none():
    store = InMemoryResultStore()
    assert store.get("nonexistent") is None


def test_store_put_overwrites():
    store = InMemoryResultStore()
    store.put(InferenceResult(request_id="r1", status=RequestStatus.PENDING, accepted_at="t0"))
    store.put(InferenceResult(request_id="r1", status=RequestStatus.COMPLETED, accepted_at="t0", result="done"))
    assert store.get("r1").status == RequestStatus.COMPLETED


# --- Gateway retrieval endpoint tests ---


def test_submit_creates_pending_record():
    client, store = build_client()
    resp = client.post("/v1/inference", json={"prompt": "hello"})
    request_id = resp.json()["request_id"]

    record = store.get(request_id)
    assert record is not None
    assert record.status == RequestStatus.PENDING
    assert record.model_name == "small-local"


def test_get_result_returns_pending():
    client, _ = build_client()
    resp = client.post("/v1/inference", json={"prompt": "hello"})
    request_id = resp.json()["request_id"]

    result = client.get(f"/v1/inference/{request_id}")
    assert result.status_code == 200
    assert result.json()["status"] == "pending"
    assert result.json()["request_id"] == request_id


def test_get_result_not_found():
    client, _ = build_client()
    result = client.get("/v1/inference/does-not-exist")
    assert result.status_code == 404


def test_get_result_after_completion():
    client, store = build_client()
    resp = client.post("/v1/inference", json={"prompt": "hello"})
    request_id = resp.json()["request_id"]

    # Simulate worker completing the request
    store.put(InferenceResult(
        request_id=request_id,
        status=RequestStatus.COMPLETED,
        accepted_at="2024-01-01T00:00:00Z",
        completed_at="2024-01-01T00:00:01Z",
        model_name="small-local",
        result="The answer is 42",
    ))

    result = client.get(f"/v1/inference/{request_id}")
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "completed"
    assert body["result"] == "The answer is 42"
    assert body["completed_at"] is not None


def test_get_result_after_failure():
    client, store = build_client()
    resp = client.post("/v1/inference", json={"prompt": "hello"})
    request_id = resp.json()["request_id"]

    store.put(InferenceResult(
        request_id=request_id,
        status=RequestStatus.FAILED,
        accepted_at="2024-01-01T00:00:00Z",
        completed_at="2024-01-01T00:00:01Z",
        error="GPU unavailable",
    ))

    result = client.get(f"/v1/inference/{request_id}")
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "failed"
    assert body["error"] == "GPU unavailable"
