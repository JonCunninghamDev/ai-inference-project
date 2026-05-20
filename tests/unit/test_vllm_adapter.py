"""Tests for vLLM batch inference adapter."""
from ai_inference.inference.vllm_adapter import InferenceInput, MockVllmAdapter


def _inputs(n: int) -> list[InferenceInput]:
    return [InferenceInput(request_id=f"r{i}", prompt=f"prompt {i}", context=f"ctx {i}") for i in range(n)]


def test_mock_adapter_returns_all_results():
    adapter = MockVllmAdapter(latency_ms=1)
    results = adapter.infer_batch("test-model", _inputs(3))
    assert len(results) == 3
    assert all(r.success for r in results)


def test_mock_adapter_preserves_order():
    adapter = MockVllmAdapter(latency_ms=1)
    inputs = _inputs(5)
    results = adapter.infer_batch("m", inputs)
    assert [r.request_id for r in results] == [f"r{i}" for i in range(5)]


def test_mock_adapter_includes_model_in_response():
    adapter = MockVllmAdapter(latency_ms=1)
    results = adapter.infer_batch("demo-small", _inputs(1))
    assert "demo-small" in results[0].text


def test_mock_adapter_includes_prompt_in_response():
    adapter = MockVllmAdapter(latency_ms=1)
    inputs = [InferenceInput(request_id="r0", prompt="What is 2+2?", context="math")]
    results = adapter.infer_batch("m", inputs)
    assert "What is 2+2?" in results[0].text


def test_mock_adapter_failure_rate():
    adapter = MockVllmAdapter(latency_ms=1, failure_rate=1.0)
    results = adapter.infer_batch("m", _inputs(3))
    assert all(not r.success for r in results)
    assert all(r.error == "Mock inference failure" for r in results)


def test_mock_adapter_duration_populated():
    adapter = MockVllmAdapter(latency_ms=10)
    results = adapter.infer_batch("m", _inputs(1))
    assert results[0].duration_ms >= 10


def test_mock_adapter_single_item_batch():
    adapter = MockVllmAdapter(latency_ms=1)
    results = adapter.infer_batch("m", _inputs(1))
    assert len(results) == 1
    assert results[0].success


def test_mock_adapter_empty_batch():
    adapter = MockVllmAdapter(latency_ms=1)
    results = adapter.infer_batch("m", [])
    assert results == []


def test_inference_output_success_property():
    adapter = MockVllmAdapter(latency_ms=1)
    results = adapter.infer_batch("m", _inputs(1))
    assert results[0].success is True

    adapter_fail = MockVllmAdapter(latency_ms=1, failure_rate=1.0)
    results_fail = adapter_fail.infer_batch("m", _inputs(1))
    assert results_fail[0].success is False
