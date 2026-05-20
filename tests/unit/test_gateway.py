from fastapi.testclient import TestClient

from ai_inference.gateway.api import GatewaySettings, create_app


class FakePublisher:
    def __init__(self):
        self.messages = []

    def publish(self, payload):
        self.messages.append(payload)


def build_client():
    publisher = FakePublisher()
    settings = GatewaySettings(
        queue_url="https://sqs.us-east-1.amazonaws.com/123/inference",
        default_model="small-local",
        small_model="small-local",
        large_model="large-local",
        small_context_tokens=2048,
        large_context_tokens=32768,
    )
    app = create_app(settings=settings, publisher=publisher)
    return TestClient(app), publisher


def test_health_reports_gateway_state():
    client, _ = build_client()
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["component"] == "inference_gateway"
    assert body["queue_configured"] is True
    assert body["models"] == ["small-local", "large-local"]


def test_submit_inference_enqueues_normalized_payload():
    client, publisher = build_client()
    response = client.post(
        "/v1/inference",
        json={
            "prompt": "Summarize this document",
            "context": "short context",
            "event_type": "general_inference",
            "priority": 5,
            "metadata": {"tenant": "demo"},
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["routing"]["model_name"] == "small-local"
    assert body["routing"]["reason"] == "default_small_model"
    assert len(publisher.messages) == 1
    assert publisher.messages[0]["prompt"] == "Summarize this document"
    assert publisher.messages[0]["requested_model"] == "small-local"
    assert publisher.messages[0]["metadata"] == {"tenant": "demo"}


def test_gateway_exposes_routing_decision_for_complex_work():
    client, publisher = build_client()
    response = client.post(
        "/v1/inference",
        json={
            "prompt": "Analyze the legal risk",
            "context": "short context",
            "event_type": "legal_review",
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["routing"]["model_name"] == "large-local"
    assert body["routing"]["reason"] == "complex_task_type"
    assert publisher.messages[0]["routing"]["model_name"] == "large-local"


def test_idempotency_key_is_stable_when_not_supplied():
    client, _ = build_client()
    payload = {"prompt": "Same", "context": "Same context"}

    first = client.post("/v1/inference", json=payload).json()
    second = client.post("/v1/inference", json=payload).json()

    assert first["idempotency_key"] == second["idempotency_key"]
    assert first["request_id"] != second["request_id"]


def test_publisher_failure_returns_503():
    class BrokenPublisher:
        def publish(self, payload):
            raise RuntimeError("queue unavailable")

    settings = GatewaySettings(queue_url="https://example.com/queue")
    client = TestClient(create_app(settings=settings, publisher=BrokenPublisher()))

    response = client.post("/v1/inference", json={"prompt": "hello"})

    assert response.status_code == 503
    assert "queue unavailable" in response.json()["detail"]
