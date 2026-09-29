"""vLLM batch inference adapter for the secure inference platform."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional, Protocol


@dataclass(frozen=True)
class VllmEndpointConfig:
    """Normalize one vLLM server into API and observability endpoints."""

    server_url: str

    def __post_init__(self) -> None:
        normalized = self.server_url.rstrip("/")
        if normalized.endswith("/v1"):
            normalized = normalized[:-3]
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("vLLM server URL must start with http:// or https://")
        object.__setattr__(self, "server_url", normalized)

    @property
    def api_base_url(self) -> str:
        return f"{self.server_url}/v1"

    @property
    def metrics_url(self) -> str:
        return f"{self.server_url}/metrics"

    @property
    def health_url(self) -> str:
        return f"{self.server_url}/health"


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


class InferenceAdapter(Protocol):
    def infer_batch(
        self,
        model: str,
        inputs: List[InferenceInput],
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> List[InferenceOutput]: ...


class VllmBatchAdapter:
    """Send requests concurrently to a vLLM OpenAI-compatible API server.

    The platform performs no token-level batching here. vLLM owns continuous
    batching on the GPU server; this adapter only supplies concurrent requests.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        max_workers: int = 8,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("openai package required for VllmBatchAdapter") from exc

        self.endpoint = VllmEndpointConfig(base_url)
        self._client = OpenAI(
            base_url=self.endpoint.api_base_url,
            api_key="local-vllm",
            timeout=60.0,
        )
        self._max_workers = max_workers

    @property
    def api_base_url(self) -> str:
        return self.endpoint.api_base_url

    @property
    def metrics_url(self) -> str:
        return self.endpoint.metrics_url

    def _infer_single(
        self,
        model: str,
        inp: InferenceInput,
        temperature: float,
        max_tokens: int,
    ) -> InferenceOutput:
        t0 = time.time()
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": f"Use ONLY the following context: {inp.context}",
                    },
                    {"role": "user", "content": inp.prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = response.choices[0].message.content
            return InferenceOutput(
                request_id=inp.request_id,
                text=text,
                duration_ms=(time.time() - t0) * 1000,
            )
        except Exception as exc:
            return InferenceOutput(
                request_id=inp.request_id,
                text=None,
                error=str(exc),
                duration_ms=(time.time() - t0) * 1000,
            )

    def infer_batch(
        self,
        model: str,
        inputs: List[InferenceInput],
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> List[InferenceOutput]:
        if not inputs:
            return []

        results: List[InferenceOutput] = []
        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(inputs))) as pool:
            futures = {
                pool.submit(
                    self._infer_single,
                    model,
                    inp,
                    temperature,
                    max_tokens,
                ): inp.request_id
                for inp in inputs
            }
            for future in as_completed(futures):
                results.append(future.result())

        order = {inp.request_id: index for index, inp in enumerate(inputs)}
        results.sort(key=lambda result: order.get(result.request_id, 0))
        return results


class MockVllmAdapter:
    """Return deterministic mock responses with simulated latency."""

    def __init__(self, latency_ms: float = 100.0, failure_rate: float = 0.0) -> None:
        self._latency_ms = latency_ms
        self._failure_rate = failure_rate
        self._call_count = 0

    def infer_batch(
        self,
        model: str,
        inputs: List[InferenceInput],
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> List[InferenceOutput]:
        del temperature, max_tokens
        import random

        results: List[InferenceOutput] = []
        for inp in inputs:
            self._call_count += 1
            time.sleep(self._latency_ms / 1000.0)
            if random.random() < self._failure_rate:
                results.append(
                    InferenceOutput(
                        request_id=inp.request_id,
                        text=None,
                        error="Mock inference failure",
                        duration_ms=self._latency_ms,
                    )
                )
            else:
                results.append(
                    InferenceOutput(
                        request_id=inp.request_id,
                        text=f"[{model}] Response to: {inp.prompt[:80]}",
                        duration_ms=self._latency_ms,
                    )
                )
        return results
