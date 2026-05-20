"""Unit tests for gateway authentication."""
import pytest

from ai_inference.gateway.auth import ApiKeyAuthProvider, AuthResult, NoAuthProvider


class TestNoAuthProvider:
    def test_always_authenticates(self):
        provider = NoAuthProvider()
        result = provider.authenticate(None)
        assert result.authenticated is True

    def test_ignores_header(self):
        provider = NoAuthProvider()
        result = provider.authenticate("Bearer anything")
        assert result.authenticated is True


class TestApiKeyAuthProvider:
    def _provider(self):
        return ApiKeyAuthProvider(keys={
            "sk-valid-key-1": "tenant-a",
            "sk-valid-key-2": "tenant-b",
        })

    def test_valid_key(self):
        result = self._provider().authenticate("Bearer sk-valid-key-1")
        assert result.authenticated is True
        assert result.tenant_id == "tenant-a"

    def test_valid_key_second_tenant(self):
        result = self._provider().authenticate("Bearer sk-valid-key-2")
        assert result.authenticated is True
        assert result.tenant_id == "tenant-b"

    def test_missing_header(self):
        result = self._provider().authenticate(None)
        assert result.authenticated is False
        assert "Missing" in result.reason

    def test_empty_header(self):
        result = self._provider().authenticate("")
        assert result.authenticated is False

    def test_invalid_format_no_bearer(self):
        result = self._provider().authenticate("sk-valid-key-1")
        assert result.authenticated is False
        assert "format" in result.reason.lower()

    def test_invalid_key(self):
        result = self._provider().authenticate("Bearer sk-wrong-key")
        assert result.authenticated is False
        assert "Invalid API key" in result.reason

    def test_case_insensitive_bearer(self):
        result = self._provider().authenticate("bearer sk-valid-key-1")
        assert result.authenticated is True


class TestGatewayAuthIntegration:
    """Test auth wired into the gateway."""

    @pytest.fixture
    def client_with_auth(self):
        from fastapi.testclient import TestClient
        from ai_inference.gateway.api import GatewaySettings, create_app
        from ai_inference.gateway.auth import ApiKeyAuthProvider

        class FakePublisher:
            def publish(self, payload):
                pass

        settings = GatewaySettings(queue_url="fake://test", default_model="test-model")
        auth = ApiKeyAuthProvider(keys={"sk-test-key": "tenant-x"})
        app = create_app(settings=settings, publisher=FakePublisher(), auth_provider=auth)
        return TestClient(app)

    def test_request_without_auth_returns_401(self, client_with_auth):
        resp = client_with_auth.post("/v1/inference", json={
            "prompt": "hello", "context": "world"
        })
        assert resp.status_code == 401

    def test_request_with_invalid_key_returns_401(self, client_with_auth):
        resp = client_with_auth.post(
            "/v1/inference",
            json={"prompt": "hello", "context": "world"},
            headers={"Authorization": "Bearer sk-wrong"},
        )
        assert resp.status_code == 401

    def test_request_with_valid_key_returns_202(self, client_with_auth):
        resp = client_with_auth.post(
            "/v1/inference",
            json={"prompt": "hello", "context": "world"},
            headers={"Authorization": "Bearer sk-test-key"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
