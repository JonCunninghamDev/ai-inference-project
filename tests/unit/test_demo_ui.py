from fastapi.testclient import TestClient

from ai_inference.demo_ui import attach_demo_ui
from ai_inference.gateway.api import GatewaySettings, create_app


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


def test_demo_home_guides_user_to_real_api_and_swagger():
    client = build_demo_client()

    response = client.get("/")

    assert response.status_code == 200
    assert "Secure AI inference, visible end to end." in response.text
    assert 'href="/docs"' in response.text
    assert "POST /v1/inference" in response.text
    assert "Priority queue" in response.text
    assert "Audit trail" in response.text


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
