"""
End-to-end integration test for the secure inference platform.

Starts the gateway and worker in-process (demo mode components),
submits requests at different priorities, and verifies the full
lifecycle: auth → admission → tenant → routing → priority queue →
batching → scheduling → circuit breaker → inference → result retrieval.
"""
import time

import pytest
from fastapi.testclient import TestClient

from ai_inference.core.audit import InMemoryAuditLog
from ai_inference.core.metrics import InMemoryMetricsSink, MetricsCollector
from ai_inference.core.priority_queue import PriorityInferenceQueue
from ai_inference.core.result_store import InMemoryResultStore
from ai_inference.gateway.api import GatewaySettings, create_app
from ai_inference.gateway.auth import ApiKeyAuthProvider
from ai_inference.inference.batching import BatchCandidate, BatchingPolicy, DynamicBatcher
from ai_inference.inference.circuit_breaker import CircuitBreaker, CircuitBreakerPolicy
from ai_inference.inference.gpu_scheduler import (
    GPUDeviceSnapshot,
    GPUScheduler,
    ModelResourceProfile,
    SchedulingPolicy,
)
from ai_inference.inference.latency import LatencyPolicy, LatencyTracker
from ai_inference.inference.router import InferenceRequest, ModelProfile, ModelRouter
from ai_inference.inference.vllm_adapter import InferenceInput, MockVllmAdapter

import json
from typing import Any, Dict, List, Mapping


class InProcessPublisher:
    """Publishes to the priority queue."""

    def __init__(self, queue: PriorityInferenceQueue):
        self._queue = queue

    def publish(self, payload: Mapping[str, Any]) -> None:
        priority = payload.get("priority", 5)
        self._queue.put(json.dumps(payload), priority=priority)


class IntegrationWorker:
    """Minimal worker for integration tests — processes queue synchronously."""

    def __init__(self, result_store, metrics, audit):
        self.result_store = result_store
        self.metrics = metrics
        self.audit = audit
        self.latency_tracker = LatencyTracker(LatencyPolicy(window_size=50, p95_threshold_ms=2000.0))
        self.router = ModelRouter(
            profiles=[
                ModelProfile(name="test-small", max_context_tokens=4096, priority=10, description="fast"),
                ModelProfile(name="test-large", max_context_tokens=32768, priority=20, description="capable"),
            ],
            default_model="test-small",
            latency_tracker=self.latency_tracker,
        )
        self.batcher = DynamicBatcher(BatchingPolicy(max_batch_size=4, max_batch_tokens=12000))
        self.scheduler = GPUScheduler(
            model_profiles={
                "test-small": ModelResourceProfile(model_name="test-small", required_memory_mb=4096, expected_utilization_percent=20.0, max_batch_size=8),
                "test-large": ModelResourceProfile(model_name="test-large", required_memory_mb=16384, expected_utilization_percent=50.0, max_batch_size=2),
            },
            policy=SchedulingPolicy(memory_reserve_mb=1024, max_gpu_utilization_percent=92.0),
        )
        self.circuit_breaker = CircuitBreaker(CircuitBreakerPolicy(failure_threshold=3), metrics=metrics)
        self.adapter = MockVllmAdapter(latency_ms=10.0, failure_rate=0.0)
        self._gpu = GPUDeviceSnapshot(device_id="gpu-0", name="test-gpu", total_memory_mb=49152, used_memory_mb=0, utilization_percent=0.0)

    def process_queue(self, queue: PriorityInferenceQueue) -> List[str]:
        """Drain and process all items. Returns list of request_ids in processing order."""
        from datetime import datetime, timezone
        from ai_inference.core.audit import AuditEvent
        from ai_inference.core.result_store import InferenceResult, RequestStatus

        processed_ids = []
        batch_raw = queue.get_batch(max_size=self.batcher.policy.max_batch_size, timeout=0.1)
        if not batch_raw:
            return processed_ids

        candidates = []
        raw_by_id = {}
        for raw in batch_raw:
            body = json.loads(raw)
            request_id = body["event_id"]
            routing = self.router.route(InferenceRequest(
                prompt=body["prompt"],
                context=body.get("context", ""),
                event_type=body.get("event_type", "general_inference"),
                priority=body.get("priority", 5),
                requested_model=body.get("requested_model"),
            ))
            candidates.append(BatchCandidate(
                request_id=request_id,
                prompt=body["prompt"],
                context=body.get("context", ""),
                model_name=routing.model_name,
                event_type=body.get("event_type", "general_inference"),
                priority=body.get("priority", 5),
                estimated_tokens=routing.estimated_tokens,
                batchable=routing.batchable,
                raw_payload=body,
            ))
            raw_by_id[request_id] = body

        batches = self.batcher.build_batches(candidates)

        for batch in batches:
            decision = self.scheduler.schedule(model_name=batch.model_name, devices=[self._gpu], batch_size=batch.size)
            if not decision.scheduled:
                continue

            if not self.circuit_breaker.allow_request():
                for c in batch.candidates:
                    self.result_store.put(InferenceResult(
                        request_id=c.request_id, status=RequestStatus.FAILED,
                        accepted_at=raw_by_id[c.request_id].get("timestamp", ""),
                        completed_at=datetime.now(timezone.utc).isoformat(),
                        model_name=batch.model_name, error="Circuit breaker open",
                    ))
                continue

            inputs = [InferenceInput(request_id=c.request_id, prompt=c.prompt, context=c.context) for c in batch.candidates]
            outputs = self.adapter.infer_batch(model=batch.model_name, inputs=inputs)

            for output in outputs:
                raw = raw_by_id[output.request_id]
                now = datetime.now(timezone.utc).isoformat()
                if output.success:
                    self.circuit_breaker.record_success()
                    self.latency_tracker.record(batch.model_name, output.duration_ms)
                    self.result_store.put(InferenceResult(
                        request_id=output.request_id, status=RequestStatus.COMPLETED,
                        accepted_at=raw.get("timestamp", ""), completed_at=now,
                        model_name=batch.model_name, result=output.text,
                    ))
                    self.audit.record(AuditEvent(
                        request_id=output.request_id, event="completed", component="worker",
                        detail={"model": batch.model_name, "duration_ms": output.duration_ms},
                    ))
                else:
                    self.circuit_breaker.record_failure()
                    self.result_store.put(InferenceResult(
                        request_id=output.request_id, status=RequestStatus.FAILED,
                        accepted_at=raw.get("timestamp", ""), completed_at=now,
                        model_name=batch.model_name, error=output.error,
                    ))
                processed_ids.append(output.request_id)

        return processed_ids


@pytest.fixture
def platform():
    """Set up the full platform in-process."""
    result_store = InMemoryResultStore()
    metrics_sink = InMemoryMetricsSink()
    metrics = MetricsCollector(metrics_sink)
    audit = InMemoryAuditLog()
    queue = PriorityInferenceQueue()
    publisher = InProcessPublisher(queue)
    auth = ApiKeyAuthProvider(keys={"sk-test": "tenant-a", "sk-vip": "tenant-b"})

    settings = GatewaySettings(
        queue_url="in-process://test",
        default_model="test-small",
        small_model="test-small",
        large_model="test-large",
        small_context_tokens=4096,
        large_context_tokens=32768,
    )
    app = create_app(
        settings=settings, publisher=publisher, result_store=result_store,
        metrics=metrics, audit_log=audit, auth_provider=auth,
    )
    client = TestClient(app)
    worker = IntegrationWorker(result_store, metrics, audit)

    return {
        "client": client,
        "worker": worker,
        "queue": queue,
        "result_store": result_store,
        "metrics_sink": metrics_sink,
        "audit": audit,
    }


class TestEndToEnd:
    def _submit(self, client, prompt="test prompt", priority=5, key="sk-test"):
        return client.post(
            "/v1/inference",
            json={"prompt": prompt, "context": "test context", "priority": priority},
            headers={"Authorization": f"Bearer {key}"},
        )

    def test_full_lifecycle(self, platform):
        """Submit → queue → process → poll result."""
        client = platform["client"]
        worker = platform["worker"]
        queue = platform["queue"]

        resp = self._submit(client)
        assert resp.status_code == 202
        request_id = resp.json()["request_id"]

        # Process
        worker.process_queue(queue)

        # Poll result
        result_resp = client.get(f"/v1/inference/{request_id}")
        assert result_resp.status_code == 200
        data = result_resp.json()
        assert data["status"] == "completed"
        assert data["result"] is not None
        assert data["model_name"] == "test-small"

    def test_priority_ordering(self, platform):
        """High-priority requests processed before normal."""
        client = platform["client"]
        worker = platform["worker"]
        queue = platform["queue"]

        # Submit normal first, then high priority
        normal_resp = self._submit(client, prompt="normal request", priority=5)
        high_resp = self._submit(client, prompt="urgent request", priority=1)

        normal_id = normal_resp.json()["request_id"]
        high_id = high_resp.json()["request_id"]

        # Queue should have high first
        batch = queue.get_batch(max_size=4, timeout=0.1)
        ids_in_order = [json.loads(item)["event_id"] for item in batch]
        assert ids_in_order[0] == high_id
        assert ids_in_order[1] == normal_id

    def test_auth_rejection(self, platform):
        """Invalid auth returns 401."""
        client = platform["client"]
        resp = self._submit(client, key="sk-invalid")
        assert resp.status_code == 401

    def test_no_auth_header_returns_401(self, platform):
        """Missing auth returns 401."""
        client = platform["client"]
        resp = client.post("/v1/inference", json={"prompt": "hello", "context": "world"})
        assert resp.status_code == 401

    def test_audit_trail_populated(self, platform):
        """Audit trail records accepted and completed events."""
        client = platform["client"]
        worker = platform["worker"]
        queue = platform["queue"]
        audit = platform["audit"]

        resp = self._submit(client)
        request_id = resp.json()["request_id"]
        worker.process_queue(queue)

        trail = audit.get_trail(request_id)
        events = [e.event for e in trail]
        assert "accepted" in events
        assert "completed" in events

    def test_metrics_emitted(self, platform):
        """Metrics sink captures lifecycle events."""
        client = platform["client"]
        worker = platform["worker"]
        queue = platform["queue"]
        sink = platform["metrics_sink"]

        self._submit(client)
        worker.process_queue(queue)

        event_types = [e.event_type for e in sink.events]
        assert "request_accepted" in event_types

    def test_routing_decision_in_response(self, platform):
        """Response includes routing decision details."""
        client = platform["client"]
        resp = self._submit(client)
        data = resp.json()
        assert data["routing"]["model_name"] == "test-small"
        assert data["routing"]["reason"] is not None
        assert data["routing"]["estimated_tokens"] > 0

    def test_complex_task_routes_to_large_model(self, platform):
        """Complex event types route to the large model."""
        client = platform["client"]
        worker = platform["worker"]
        queue = platform["queue"]

        resp = client.post(
            "/v1/inference",
            json={"prompt": "analyze this", "context": "data", "event_type": "code_generation", "priority": 5},
            headers={"Authorization": "Bearer sk-test"},
        )
        assert resp.status_code == 202
        assert resp.json()["routing"]["model_name"] == "test-large"

    def test_multiple_requests_batch_processed(self, platform):
        """Multiple compatible requests are batched together."""
        client = platform["client"]
        worker = platform["worker"]
        queue = platform["queue"]

        for i in range(3):
            self._submit(client, prompt=f"request {i}")

        processed = worker.process_queue(queue)
        assert len(processed) == 3

        # All should be completed
        for rid in processed:
            result = platform["result_store"].get(rid)
            assert result.status.value == "completed"

    def test_poll_pending_before_processing(self, platform):
        """Polling before worker runs shows pending status."""
        client = platform["client"]
        resp = self._submit(client)
        request_id = resp.json()["request_id"]

        result_resp = client.get(f"/v1/inference/{request_id}")
        assert result_resp.json()["status"] == "pending"

    def test_unknown_request_returns_404(self, platform):
        """Polling unknown request_id returns 404."""
        client = platform["client"]
        resp = client.get("/v1/inference/nonexistent-id")
        assert resp.status_code == 404

    def test_audit_trail_api(self, platform):
        """GET /v1/audit/{request_id} returns the trail."""
        client = platform["client"]
        worker = platform["worker"]
        queue = platform["queue"]

        resp = self._submit(client)
        request_id = resp.json()["request_id"]
        worker.process_queue(queue)

        audit_resp = client.get(f"/v1/audit/{request_id}")
        assert audit_resp.status_code == 200
        data = audit_resp.json()
        assert data["request_id"] == request_id
        assert len(data["events"]) >= 1
        assert data["events"][0]["event"] == "accepted"

    def test_audit_trail_api_404(self, platform):
        """Audit trail for unknown request returns 404."""
        client = platform["client"]
        resp = client.get("/v1/audit/nonexistent")
        assert resp.status_code == 404

    def test_health_endpoint_enriched(self, platform):
        """Health endpoint includes request counts and admission state."""
        client = platform["client"]
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "requests" in data
        assert "pending" in data["requests"]
        assert "processing" in data["requests"]
        assert "admission" in data
