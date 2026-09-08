import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from ai_inference.core.audit import InMemoryAuditLog
from ai_inference.core.metrics import MetricsCollector
from ai_inference.core.result_store import InMemoryResultStore
from ai_inference.demo import DemoWorker
from ai_inference.demo_ui import attach_demo_ui
from ai_inference.gateway.api import GatewaySettings, create_app
from ai_inference.gateway.tenant import TenantPolicy, TenantPolicyEngine


class FakePublisher:
    def __init__(self):
        self.messages = []

    def publish(self, payload):
        self.messages.append(payload)


def build_demo_client() -> TestClient:
    settings = GatewaySettings(
        queue_url="in-process://test",
        default_model="demo-small",
        small_model="demo-small",
        large_model="demo-large",
    )
    app = create_app(settings=settings, publisher=FakePublisher())
    attach_demo_ui(app)
    return TestClient(app)


def test_demo_home_leads_with_nontechnical_guided_experience():
    client = build_demo_client()

    response = client.get("/")

    assert response.status_code == 200
    assert "See how a production-style AI request moves safely from request to result." in response.text
    assert "Start guided demo" in response.text
    assert "What happens to one AI request" in response.text
    assert "Request accepted" in response.text
    assert "Model chosen" in response.text
    assert "Compute checked" in response.text
    assert "Decisions recorded" in response.text
    assert "What you just saw" in response.text


def test_demo_home_keeps_engineering_tools_available_as_secondary_details():
    client = build_demo_client()

    response = client.get("/")

    assert response.status_code == 200
    assert "For engineers" in response.text
    assert 'href="/docs"' in response.text
    assert 'href="/openapi.json"' in response.text
    assert 'href="/health"' in response.text
    assert "Show technical activity" in response.text


def test_openapi_groups_operations_and_includes_demo_request_example():
    client = build_demo_client()

    schema = client.get("/openapi.json").json()

    assert schema["paths"]["/health"]["get"]["tags"] == ["Operations"]
    assert schema["paths"]["/v1/inference"]["post"]["tags"] == ["Inference"]
    assert schema["paths"]["/v1/audit/{request_id}"]["get"]["tags"] == ["Audit"]

    request_schema = schema["components"]["schemas"]["InferenceGatewayRequest"]
    example = request_schema["examples"][0]
    assert example["metadata"] == {"tenant": "swagger-demo"}
    assert example["priority"] == 5


def test_swagger_ui_is_configured_for_interactive_demo_use():
    client = build_demo_client()

    response = client.get("/docs")

    assert response.status_code == 200
    assert "displayRequestDuration" in response.text
    assert "tryItOutEnabled" in response.text


def test_demo_worker_releases_tenant_slot_after_terminal_result():
    tenant_engine = TenantPolicyEngine(default_policy=TenantPolicy(max_concurrent=1))
    assert tenant_engine.check("guided-demo").allowed is True

    worker = DemoWorker(
        result_store=InMemoryResultStore(),
        metrics=MetricsCollector(),
        audit=InMemoryAuditLog(),
        tenant_engine=tenant_engine,
    )
    payload = {
        "event_id": "request-1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt": "Explain deterministic routing",
        "context": "",
        "event_type": "general_inference",
        "priority": 5,
        "requested_model": "demo-small",
        "metadata": {"tenant": "guided-demo"},
    }

    worker._process_batch([json.dumps(payload)])

    assert tenant_engine.check("guided-demo").allowed is True
