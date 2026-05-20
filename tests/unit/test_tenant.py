"""Tests for tenant-aware policies."""
import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_inference.core.metrics import InMemoryMetricsSink, MetricsCollector
from ai_inference.gateway.api import GatewaySettings, create_app
from ai_inference.gateway.tenant import TenantPolicy, TenantPolicyEngine


# --- Unit tests for TenantPolicyEngine ---


def test_admit_within_limits():
    engine = TenantPolicyEngine()
    result = engine.check("tenant-a")
    assert result.allowed is True
    assert result.tenant_id == "tenant-a"


def test_rate_limit_exceeded():
    engine = TenantPolicyEngine(default_policy=TenantPolicy(max_requests_per_minute=3))
    for _ in range(3):
        assert engine.check("t1").allowed is True
    result = engine.check("t1")
    assert result.allowed is False
    assert "Rate limit" in result.reason
    assert result.retry_after_seconds >= 1


def test_concurrency_limit_exceeded():
    engine = TenantPolicyEngine(default_policy=TenantPolicy(max_concurrent=2))
    assert engine.check("t1").allowed is True
    assert engine.check("t1").allowed is True
    result = engine.check("t1")
    assert result.allowed is False
    assert "Concurrency" in result.reason


def test_release_decrements_concurrency():
    engine = TenantPolicyEngine(default_policy=TenantPolicy(max_concurrent=1))
    assert engine.check("t1").allowed is True
    assert engine.check("t1").allowed is False

    engine.release("t1")
    assert engine.check("t1").allowed is True


def test_per_tenant_isolation():
    engine = TenantPolicyEngine(default_policy=TenantPolicy(max_requests_per_minute=2))
    assert engine.check("t1").allowed is True
    assert engine.check("t1").allowed is True
    assert engine.check("t1").allowed is False

    # t2 is independent
    assert engine.check("t2").allowed is True


def test_custom_policy_per_tenant():
    engine = TenantPolicyEngine(default_policy=TenantPolicy(max_requests_per_minute=1))
    engine.set_policy("vip", TenantPolicy(max_requests_per_minute=100))

    assert engine.check("vip").allowed is True
    assert engine.check("vip").allowed is True  # still under 100

    # default tenant hits limit at 1
    assert engine.check("basic").allowed is True
    assert engine.check("basic").allowed is False


def test_priority_boost():
    engine = TenantPolicyEngine()
    engine.set_policy("vip", TenantPolicy(priority_boost=3))

    result = engine.check("vip", request_priority=5)
    assert result.effective_priority == 8


def test_priority_boost_capped_at_10():
    engine = TenantPolicyEngine()
    engine.set_policy("vip", TenantPolicy(priority_boost=10))

    result = engine.check("vip", request_priority=7)
    assert result.effective_priority == 10


def test_extract_tenant_from_metadata():
    assert TenantPolicyEngine.extract_tenant({"tenant": "acme"}) == "acme"
    assert TenantPolicyEngine.extract_tenant({}) == "__default__"


def test_rejection_emits_metric():
    sink = InMemoryMetricsSink()
    metrics = MetricsCollector(sink)
    engine = TenantPolicyEngine(default_policy=TenantPolicy(max_requests_per_minute=1), metrics=metrics)
    engine.check("t1")
    engine.check("t1")  # rejected
    assert any("tenant_rate_limit" in e.fields.get("reason", "") for e in sink.events)


# --- Gateway integration ---


class FakePublisher:
    def __init__(self):
        self.messages = []

    def publish(self, payload):
        self.messages.append(payload)


def _build_client(tenant_engine=None):
    publisher = FakePublisher()
    settings = GatewaySettings(
        queue_url="https://sqs.us-east-1.amazonaws.com/123/inference",
        default_model="small-local",
        small_model="small-local",
        small_context_tokens=2048,
        large_context_tokens=32768,
    )
    app = create_app(settings=settings, publisher=publisher, tenant_engine=tenant_engine)
    return TestClient(app), publisher


def test_gateway_tenant_rate_limit():
    engine = TenantPolicyEngine(default_policy=TenantPolicy(max_requests_per_minute=2))
    client, publisher = _build_client(tenant_engine=engine)

    for _ in range(2):
        resp = client.post("/v1/inference", json={"prompt": "hi", "metadata": {"tenant": "acme"}})
        assert resp.status_code == 202

    resp = client.post("/v1/inference", json={"prompt": "hi", "metadata": {"tenant": "acme"}})
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_gateway_different_tenants_independent():
    engine = TenantPolicyEngine(default_policy=TenantPolicy(max_requests_per_minute=1))
    client, _ = _build_client(tenant_engine=engine)

    resp = client.post("/v1/inference", json={"prompt": "hi", "metadata": {"tenant": "a"}})
    assert resp.status_code == 202

    # tenant "a" is now rate limited
    resp = client.post("/v1/inference", json={"prompt": "hi", "metadata": {"tenant": "a"}})
    assert resp.status_code == 429

    # tenant "b" is fine
    resp = client.post("/v1/inference", json={"prompt": "hi", "metadata": {"tenant": "b"}})
    assert resp.status_code == 202
