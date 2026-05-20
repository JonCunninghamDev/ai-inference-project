"""
Demo mode: runs the entire inference platform in a single process.

No AWS credentials required. No SQS, no DynamoDB, no vLLM server.
Demonstrates the full request lifecycle:

    submit → route → batch → schedule → infer → result retrieval

Usage:
    uv run python -m ai_inference.demo
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping

import uvicorn

from ai_inference.core.audit import AuditEvent, AuditLog, InMemoryAuditLog
from ai_inference.core.metrics import InMemoryMetricsSink, JsonlMetricsSink, MetricsCollector
from ai_inference.core.priority_queue import PriorityInferenceQueue
from ai_inference.core.reconciliation import ReconciliationConfig, ReconciliationEngine
from ai_inference.core.reconciliation_scheduler import ReconciliationScheduler
from ai_inference.core.result_store import InferenceResult, InMemoryResultStore, RequestStatus
from ai_inference.gateway.api import GatewaySettings, create_app
from ai_inference.inference.batching import BatchCandidate, BatchingPolicy, DynamicBatcher
from ai_inference.inference.circuit_breaker import CircuitBreaker, CircuitBreakerPolicy
from ai_inference.inference.gpu_scheduler import (
    GPUDeviceSnapshot,
    GPUScheduler,
    ModelResourceProfile,
    SchedulingPolicy,
)
from ai_inference.inference.router import InferenceRequest, ModelRouter, ModelProfile
from ai_inference.inference.latency import LatencyTracker, LatencyPolicy
from ai_inference.inference.vllm_adapter import InferenceInput, MockVllmAdapter


# ---------------------------------------------------------------------------
# In-process queue publisher (replaces SQS)
# ---------------------------------------------------------------------------

_work_queue: PriorityInferenceQueue = PriorityInferenceQueue()


class InProcessPublisher:
    """Publishes to the priority queue instead of SQS."""

    def __init__(self, queue: PriorityInferenceQueue):
        self._queue = queue

    def publish(self, payload: Mapping[str, Any]) -> None:
        priority = payload.get("priority", 5)
        self._queue.put(json.dumps(payload), priority=priority)


# ---------------------------------------------------------------------------
# Demo worker (processes from in-memory queue, writes to shared result store)
# ---------------------------------------------------------------------------


class DemoWorker:
    """Minimal worker that processes the in-memory queue with full platform logic."""

    def __init__(self, result_store: InMemoryResultStore, metrics: MetricsCollector, audit: AuditLog) -> None:
        self.result_store = result_store
        self.metrics = metrics
        self.audit = audit
        self.router = ModelRouter(
            profiles=[
                ModelProfile(name="demo-small", max_context_tokens=4096, priority=10, description="fast"),
                ModelProfile(name="demo-large", max_context_tokens=32768, priority=20, description="capable"),
            ],
            default_model="demo-small",
            latency_tracker=self.latency_tracker,
        )
        self.batcher = DynamicBatcher(BatchingPolicy(max_batch_size=4, max_batch_tokens=12000))
        self.scheduler = GPUScheduler(
            model_profiles={
                "demo-small": ModelResourceProfile(model_name="demo-small", required_memory_mb=4096, expected_utilization_percent=20.0, max_batch_size=8),
                "demo-large": ModelResourceProfile(model_name="demo-large", required_memory_mb=16384, expected_utilization_percent=50.0, max_batch_size=2),
            },
            policy=SchedulingPolicy(memory_reserve_mb=1024, max_gpu_utilization_percent=92.0),
        )
        self._gpu = GPUDeviceSnapshot(device_id="gpu-0", name="demo-gpu", total_memory_mb=49152, used_memory_mb=0, utilization_percent=0.0)
        self.circuit_breaker = CircuitBreaker(CircuitBreakerPolicy(failure_threshold=3, recovery_timeout_seconds=10.0), metrics=metrics)
        self.adapter = MockVllmAdapter(latency_ms=100.0, failure_rate=0.0)
        self.latency_tracker = LatencyTracker(LatencyPolicy(window_size=100, p95_threshold_ms=2000.0))

    def _process_batch(self, messages: List[str]) -> None:
        candidates: List[BatchCandidate] = []
        raw_by_id: Dict[str, dict] = {}

        for raw in messages:
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
            self.metrics.record_batch_built(
                batch_id=batch.batch_id, model=batch.model_name,
                size=batch.size, total_tokens=batch.total_estimated_tokens, reason=batch.reason,
            )
            decision = self.scheduler.schedule(model_name=batch.model_name, devices=[self._gpu], batch_size=batch.size)
            self.metrics.record_scheduling_decision(
                batch_id=batch.batch_id, model=batch.model_name,
                scheduled=decision.scheduled, device_id=decision.device_id, reason=decision.reason,
            )
            if not decision.scheduled:
                print(f"  ⏸  Batch deferred: {decision.reason}")
                for c in batch.candidates:
                    self.result_store.put(InferenceResult(
                        request_id=c.request_id, status=RequestStatus.FAILED,
                        accepted_at=raw_by_id[c.request_id].get("timestamp", ""),
                        completed_at=datetime.now(timezone.utc).isoformat(),
                        model_name=batch.model_name, error=f"GPU scheduling deferred: {decision.reason}",
                    ))
                continue

            # Circuit breaker gate
            if not self.circuit_breaker.allow_request():
                print(f"  ⚡ Circuit breaker OPEN — fast-failing batch {batch.batch_id[:8]}")
                for c in batch.candidates:
                    self.result_store.put(InferenceResult(
                        request_id=c.request_id, status=RequestStatus.FAILED,
                        accepted_at=raw_by_id[c.request_id].get("timestamp", ""),
                        completed_at=datetime.now(timezone.utc).isoformat(),
                        model_name=batch.model_name, error="Circuit breaker open",
                    ))
                    self.metrics.record_inference_failed(request_id=c.request_id, model=batch.model_name, error="circuit_breaker_open")
                continue

            print(f"  ▶  Batch {batch.batch_id[:8]} | model={batch.model_name} size={batch.size} device={decision.device_id}")

            # Mark processing
            for candidate in batch.candidates:
                self.result_store.put(InferenceResult(
                    request_id=candidate.request_id, status=RequestStatus.PROCESSING,
                    accepted_at=raw_by_id[candidate.request_id].get("timestamp", ""),
                    model_name=batch.model_name,
                ))
                self.metrics.record_inference_started(request_id=candidate.request_id, model=batch.model_name, batch_id=batch.batch_id)

            # Batch inference via adapter
            inputs = [InferenceInput(request_id=c.request_id, prompt=c.prompt, context=c.context) for c in batch.candidates]
            outputs = self.adapter.infer_batch(model=batch.model_name, inputs=inputs)

            for output in outputs:
                accepted_at = raw_by_id[output.request_id].get("timestamp", "")
                if output.success:
                    self.circuit_breaker.record_success()
                    self.latency_tracker.record(batch.model_name, output.duration_ms)
                    self.metrics.record_inference_completed(request_id=output.request_id, model=batch.model_name, duration_ms=output.duration_ms)
                    if accepted_at:
                        try:
                            wait_ms = (datetime.now(timezone.utc) - datetime.fromisoformat(accepted_at)).total_seconds() * 1000 - output.duration_ms
                            self.metrics.record_queue_wait_time(request_id=output.request_id, wait_ms=max(0, wait_ms))
                        except (ValueError, TypeError):
                            pass
                    self.result_store.put(InferenceResult(
                        request_id=output.request_id, status=RequestStatus.COMPLETED,
                        accepted_at=accepted_at,
                        completed_at=datetime.now(timezone.utc).isoformat(),
                        model_name=batch.model_name, result=output.text,
                    ))
                    self.audit.record(AuditEvent(
                        request_id=output.request_id, event="completed", component="worker",
                        detail={"model": batch.model_name, "duration_ms": output.duration_ms},
                    ))
                    print(f"     ✓ {output.request_id[:8]} → completed ({output.duration_ms:.0f}ms)")
                else:
                    self.circuit_breaker.record_failure()
                    self.metrics.record_inference_failed(request_id=output.request_id, model=batch.model_name, error=output.error or "unknown")
                    self.result_store.put(InferenceResult(
                        request_id=output.request_id, status=RequestStatus.FAILED,
                        accepted_at=accepted_at,
                        completed_at=datetime.now(timezone.utc).isoformat(),
                        model_name=batch.model_name, error=output.error,
                    ))
                    self.audit.record(AuditEvent(
                        request_id=output.request_id, event="failed", component="worker",
                        detail={"model": batch.model_name, "error": output.error},
                    ))
                    print(f"     ✗ {output.request_id[:8]} → failed: {output.error}")

    def run(self, queue: PriorityInferenceQueue) -> None:
        """Poll the priority queue forever."""
        print("  Worker ready — polling for work\n")
        while True:
            batch = queue.get_batch(max_size=self.batcher.policy.max_batch_size, timeout=0.5)
            if batch:
                self._process_batch(batch)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║   Secure Inference Platform — Demo Mode             ║")
    print("╠══════════════════════════════════════════════════════╣")
    print("║  Gateway:  http://localhost:8080                     ║")
    print("║  Health:   http://localhost:8080/health              ║")
    print("║  Submit:   POST /v1/inference                       ║")
    print("║  Poll:     GET  /v1/inference/{request_id}          ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    # Shared state
    result_store = InMemoryResultStore()
    jsonl_sink = JsonlMetricsSink("metrics.jsonl")
    metrics = MetricsCollector(jsonl_sink)
    audit = InMemoryAuditLog()
    publisher = InProcessPublisher(_work_queue)

    # Gateway
    settings = GatewaySettings(
        queue_url="in-process://demo",
        default_model="demo-small",
        small_model="demo-small",
        large_model="demo-large",
        small_context_tokens=4096,
        large_context_tokens=32768,
    )
    app = create_app(settings=settings, publisher=publisher, result_store=result_store, metrics=metrics, audit_log=audit)

    # Worker thread
    worker = DemoWorker(result_store, metrics, audit)
    worker_thread = threading.Thread(target=worker.run, args=(_work_queue,), daemon=True)
    worker_thread.start()

    # Reconciliation scheduler (dry-run in demo, heals nothing but logs stale requests)
    recon_config = ReconciliationConfig(dry_run_enabled=True, stale_pending_timeout_seconds=60)
    recon_engine = ReconciliationEngine(config=recon_config, result_store=result_store)
    recon_scheduler = ReconciliationScheduler(recon_engine, interval_seconds=15.0, metrics=metrics)
    recon_scheduler.start()

    # Run gateway (blocks)
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="warning")


if __name__ == "__main__":
    main()
