"""
vLLM batch inference adapter for the secure inference platform.

Replaces sequential per-request inference calls with concurrent batch
execution. Provides a protocol boundary so the real vLLM client, a mock,
or a future TensorRT-LLM backend can be swapped without changing worker logic.

Usage:
    from ai_inference.inference.vllm_adapter import VllmBatchAdapter, MockVllmAdapter

    adapter = VllmBatchAdapter(base_url="http://localhost:8000")
    results = adapter.infer_batch(model="llama-3.1-8b", prompts=[...], contexts=[...])
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional, Protocol


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class InferenceInput:
    """A single inference request within a batch."""

    request_id: str
    prompt: str
    context: str


@dataclass
class InferenceOutput:
    """Result of a single inference call."""

    request_id: str
    text: Optional[str]
    error: Optional[str] = None
    duration_ms: float = 0.0

    @property
    def success(self) -> bool:
        return self.text is not None and self.error is None


# ---------------------------------------------------------------------------
# Adapter protocol
# ---------------------------------------------------------------------------


class InferenceAdapter(Protocol):
    def infer_batch(self, model: str, inputs: List[InferenceInput], temperature: float = 0.1, max_tokens: int = 2048) -> List[InferenceOutput]: ...


# ---------------------------------------------------------------------------
# Real vLLM adapter (concurrent HTTP calls)
# ---------------------------------------------------------------------------


class VllmBatchAdapter:
    """Sends batch items concurrently to a vLLM-compatible OpenAI API server.

    vLLM's server handles internal batching on the GPU side. Sending
    requests concurrently from the client maximizes server-side batch
    utilization without waiting for sequential round trips.
    """

    def __init__(self, base_url: str = "http://localhost:8000", max_workers: int = 8) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError("openai package required for VllmBatchAdapter") from e
        self._client = OpenAI(base_url=base_url, api_key="local-airgap", timeout=60.0)
        self._max_workers = max_workers

    def _infer_single(self, model: str, inp: InferenceInput, temperature: float, max_tokens: int) -> InferenceOutput:
        t0 = time.time()
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": f"Use ONLY the following context: {inp.context}"},
                    {"role": "user", "content": inp.prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = response.choices[0].message.content
            return InferenceOutput(request_id=inp.request_id, text=text, duration_ms=(time.time() - t0) * 1000)
        except Exception as e:
            return InferenceOutput(request_id=inp.request_id, text=None, error=str(e), duration_ms=(time.time() - t0) * 1000)

    def infer_batch(self, model: str, inputs: List[InferenceInput], temperature: float = 0.1, max_tokens: int = 2048) -> List[InferenceOutput]:
        results: List[InferenceOutput] = []
        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(inputs))) as pool:
            futures = {
                pool.submit(self._infer_single, model, inp, temperature, max_tokens): inp.request_id
                for inp in inputs
            }
            for future in as_completed(futures):
                results.append(future.result())
        # Return in original input order
        order = {inp.request_id: i for i, inp in enumerate(inputs)}
        results.sort(key=lambda r: order.get(r.request_id, 0))
        return results


# ---------------------------------------------------------------------------
# Mock adapter (for testing and demo mode)
# ---------------------------------------------------------------------------


class MockVllmAdapter:
    """Returns deterministic mock responses with simulated latency."""

    def __init__(self, latency_ms: float = 100.0, failure_rate: float = 0.0) -> None:
        self._latency_ms = latency_ms
        self._failure_rate = failure_rate
        self._call_count = 0

    def infer_batch(self, model: str, inputs: List[InferenceInput], temperature: float = 0.1, max_tokens: int = 2048) -> List[InferenceOutput]:
        import random
        results: List[InferenceOutput] = []
        for inp in inputs:
            self._call_count += 1
            time.sleep(self._latency_ms / 1000.0)
            if random.random() < self._failure_rate:
                results.append(InferenceOutput(
                    request_id=inp.request_id, text=None,
                    error="Mock inference failure", duration_ms=self._latency_ms,
                ))
            else:
                results.append(InferenceOutput(
                    request_id=inp.request_id,
                    text=f"[{model}] Response to: {inp.prompt[:80]}",
                    duration_ms=self._latency_ms,
                ))
        return results
