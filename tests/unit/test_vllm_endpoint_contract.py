import pytest

from ai_inference.inference.vllm_adapter import VllmEndpointConfig


@pytest.mark.parametrize(
    ("configured", "server", "api", "metrics"),
    [
        (
            "http://localhost:8000",
            "http://localhost:8000",
            "http://localhost:8000/v1",
            "http://localhost:8000/metrics",
        ),
        (
            "http://localhost:8000/",
            "http://localhost:8000",
            "http://localhost:8000/v1",
            "http://localhost:8000/metrics",
        ),
        (
            "http://vllm.internal:8000/v1/",
            "http://vllm.internal:8000",
            "http://vllm.internal:8000/v1",
            "http://vllm.internal:8000/metrics",
        ),
    ],
)
def test_vllm_endpoint_normalization(
    configured: str,
    server: str,
    api: str,
    metrics: str,
) -> None:
    endpoint = VllmEndpointConfig(configured)

    assert endpoint.server_url == server
    assert endpoint.api_base_url == api
    assert endpoint.metrics_url == metrics
    assert endpoint.health_url == server + "/health"


def test_vllm_endpoint_rejects_non_http_scheme() -> None:
    with pytest.raises(ValueError):
        VllmEndpointConfig("localhost:8000")
