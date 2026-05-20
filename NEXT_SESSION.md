# NEXT SESSION

## Current working identity

Package: `ai_inference`. Repository: `ai-inference`. The rename from `air-gapped-rag` is complete.

## Current architecture state

```text
Client
  → Inference Gateway API (FastAPI)
    → Admission Control (system-wide backpressure)
    → Tenant Policy Engine (per-tenant rate/concurrency limits)
    → Deterministic Model Router
  → SQS / In-Process Queue
  → Dynamic Batcher
  → GPU-Aware Scheduler
  → Circuit Breaker (protects downstream)
  → vLLM Batch Adapter (concurrent inference)
  → Result Store (InMemory or DynamoDB)
  → Client polls GET /v1/inference/{request_id}

Background:
  → Reconciliation Engine (heals stale requests)
  → Autoscaler (scaling decisions based on metrics)
  → Structured Logging + JSONL Metrics Sink
```

## Completed modules

| # | Module | Key file |
|---|--------|----------|
| 1 | Model Routing | `src/ai_inference/inference/router.py` |
| 2 | Inference Gateway API | `src/ai_inference/gateway/api.py` |
| 3 | Dynamic Batching | `src/ai_inference/inference/batching.py` |
| 4 | GPU-Aware Scheduling | `src/ai_inference/inference/gpu_scheduler.py` |
| 5 | Result Store + Retrieval | `src/ai_inference/core/result_store.py` |
| 6 | Reconciliation + Replay | `src/ai_inference/core/reconciliation.py` |
| 7 | Structured Logging | `src/ai_inference/core/logging.py` |
| 8 | Observability Metrics | `src/ai_inference/core/metrics.py` |
| 9 | Admission Control | `src/ai_inference/gateway/admission.py` |
| 10 | Tenant-Aware Policies | `src/ai_inference/gateway/tenant.py` |
| 11 | vLLM Batch Adapter | `src/ai_inference/inference/vllm_adapter.py` |
| 12 | Worker Pool Autoscaling | `src/ai_inference/core/autoscaler.py` |
| 13 | Circuit Breaker | `src/ai_inference/inference/circuit_breaker.py` |
| 14 | Worker Execution Integration | `src/ai_inference/core/worker.py` + `src/ai_inference/demo.py` |
| 15 | Audit Trail | `src/ai_inference/core/audit.py` |
| 16 | Latency-Aware Routing | `src/ai_inference/inference/latency.py` |
| 17 | Priority Queues | `src/ai_inference/core/priority_queue.py` |
| 18 | Gateway Authentication | `src/ai_inference/gateway/auth.py` |
| 19 | End-to-End Integration Test | `tests/unit/test_integration.py` |
| 20 | Reconciliation Scheduler | `src/ai_inference/core/reconciliation_scheduler.py` |
| 21 | Audit Trail API | `src/ai_inference/gateway/api.py` |
| 22 | Health Endpoint Enrichment | `src/ai_inference/gateway/api.py` |
| 23 | Request TTL | `src/ai_inference/core/ttl.py` |
| 24 | Production Worker Wiring | `src/ai_inference/core/worker.py` + `src/ai_inference/core/config.py` |
| 25 | Autoscaler Executor | `src/ai_inference/core/scaling_executor.py` |

## What changed this session

### Worker execution integration (Module 14)

- Wired `CircuitBreaker` into `RAGWorker.process_batch()` — fast-fails entire batch when circuit is open
- Wired `InferenceAdapter` (vLLM batch adapter) into `process_batch()` — replaces sequential `perform_inference_with_model` calls
- Worker constructor now accepts optional `inference_adapter`, `circuit_breaker`, `metrics`, and `tenant_engine`
- Added `_initialize_inference_adapter()` — creates `VllmBatchAdapter` from config when no adapter is injected
- Added `_release_tenant()` — automatically decrements tenant concurrency on request completion
- Demo worker refactored: uses `MockVllmAdapter` + `CircuitBreaker` instead of inline `_mock_inference()`
- Both production and demo paths now use the same adapter protocol boundary
- All 145 existing tests still pass — no behavioral regressions

### Known gaps closed

- ✅ Circuit breaker wired into production worker loop
- ✅ vLLM batch adapter wired into production worker loop
- ✅ `tenant.release()` called automatically on request completion
- ✅ Demo mode uses same adapter protocol as production

### Audit trail (Module 15)

- Added `src/ai_inference/core/audit.py` with `AuditEvent`, `AuditLog` protocol, and three implementations:
  - `InMemoryAuditLog` — append-only in-memory for dev/demo
  - `JsonlAuditLog` — append-only local file for air-gapped environments
  - `NullAuditLog` — no-op when auditing is disabled
- Gateway emits `accepted` audit event with model, reason, tokens, event_type, tenant
- Worker emits `completed` and `failed` audit events with model, batch_id, duration/error
- Demo mode wired with shared `InMemoryAuditLog` between gateway and worker
- 11 new tests covering all implementations, append-only behavior, JSONL format, parent dir creation

### Latency-aware routing (Module 16)

- Added `src/ai_inference/inference/latency.py` with `LatencyTracker`, `LatencyPolicy`, `ModelLatencyStats`
- Sliding window per-model P95 latency tracking with configurable window size, threshold, and min samples
- Router extended with optional `latency_tracker` parameter and `LATENCY_AVOIDANCE` reason code
- When default model is degraded, router selects a non-degraded alternative that fits the token budget
- Explicit requests, high-priority, and complex tasks are never overridden by latency
- If all models are degraded, falls through to normal default (no avoidance loop)
- Demo worker wired: feeds observed durations to tracker, router consults tracker on each request
- 14 new tests covering tracker behavior, routing integration, and override protection

### Priority queues (Module 17)

- Added `src/ai_inference/core/priority_queue.py` with `PriorityInferenceQueue` and `PriorityLane`
- Three lanes (HIGH/NORMAL/LOW) with strict drain ordering
- `priority_to_lane()` maps request priority 1-10 to lanes
- `get_batch()` respects priority order when draining multiple items
- Demo mode publisher routes into correct lane based on request priority
- Demo worker uses `queue.get_batch()` instead of manual Queue drain loop
- 13 new tests covering lane ordering, FIFO within lanes, batch draining, edge cases

### Gateway authentication (Module 18)

- Added `src/ai_inference/gateway/auth.py` with `AuthProvider` protocol, `ApiKeyAuthProvider`, `NoAuthProvider`
- API key maps to tenant identity — auth-derived tenant takes precedence over metadata
- Gateway checks auth before admission control (gate order: auth → admission → tenant → routing)
- Returns 401 for missing/invalid credentials
- Demo mode uses `NoAuthProvider` (open access)
- 12 new tests covering both providers and gateway integration

### End-to-end integration test (Module 19)

- Added `tests/unit/test_integration.py` with full platform lifecycle tests
- Starts gateway, priority queue, and worker in-process with auth enabled
- 11 tests covering: full lifecycle, priority ordering, auth rejection, audit trail, metrics, routing, batching, pending status, 404

### Reconciliation scheduler (Module 20)

- Added `src/ai_inference/core/reconciliation_scheduler.py` with `ReconciliationScheduler`
- Background daemon thread running `engine.run_once()` on configurable interval
- Emits `reconciliation_pass` metrics per cycle
- Graceful start/stop, idempotent start
- Demo mode wired: runs every 15s in dry-run mode
- 5 new tests covering start/stop, multiple passes, metrics emission, idempotency

### Audit trail API + health enrichment + request TTL (Modules 21–23)

- `GET /v1/audit/{request_id}` returns the full lifecycle trail as JSON (404 for unknown)
- `GET /health` now includes `requests.pending`, `requests.processing`, and `admission` state
- Added `src/ai_inference/core/ttl.py` with `RequestTTL` — checks if accepted_at exceeds max age
- Worker checks TTL before inference: expired requests are marked failed, deleted from queue, audit event emitted
- 7 new TTL tests + 3 new integration tests for audit API and health endpoint

### Production worker wiring (Module 24)

- Config extended with: `result_store_table_name`, `result_store_ttl_days`, `request_ttl_seconds`, `circuit_breaker_failure_threshold`, `circuit_breaker_recovery_timeout_seconds`, `latency_window_size`, `latency_p95_threshold_ms`, `latency_min_samples`
- Worker initializes `DynamoResultStore` when table name is configured
- Worker initializes `CircuitBreaker`, `LatencyTracker`, `RequestTTL` from config
- Router receives latency tracker for latency-aware decisions
- Worker feeds latency observations to tracker on successful inference
- Worker test mock config updated with all new fields

### Autoscaler executor (Module 25)

- Added `src/ai_inference/core/scaling_executor.py` with `ScalingExecutor` protocol
- `LogOnlyExecutor` — logs without acting (dry-run default)
- `EcsScalingExecutor` — calls ECS `update_service`
- `AsgScalingExecutor` — calls ASG `set_desired_capacity`
- 8 new tests covering all executors, API calls, and failure handling

### Test count

```text
238 passed, 0 warnings
```

Command:

```bash
mise run test
```

## Recommended next module

The platform is feature-complete with 26 modules. All items from the original roadmap are implemented and tested.

Future enhancements (not blocking):

- **Streaming/SSE endpoint** for real-time result delivery
- **Multi-region replication** for disaster recovery
- **OAuth/mTLS** for production auth beyond API keys
- **SQS FIFO** with message group IDs for deployed priority queues
- **Grafana integration** as an alternative to Streamlit dashboard

Choose based on what would be most impactful for a demo or deployment.

## Known limitations

- Gateway and worker share result store only in demo mode. Deployed mode requires both to point at the same DynamoDB table (config-driven, not yet wired in worker startup).
- Heal mode resubmits with a generic payload. A future version should persist the original payload in the result store for faithful replay.
- Queue publisher does not use SQS message attributes, FIFO deduplication, or tenant metadata.
- The legacy `perform_inference` and `perform_inference_with_model` methods remain on `RAGWorker` for backward compatibility but are no longer used by `process_batch`.

## File reference

| Purpose | Path |
|---------|------|
| Gateway API | `src/ai_inference/gateway/api.py` |
| Model Router | `src/ai_inference/inference/router.py` |
| Dynamic Batcher | `src/ai_inference/inference/batching.py` |
| GPU Scheduler | `src/ai_inference/inference/gpu_scheduler.py` |
| Result Store | `src/ai_inference/core/result_store.py` |
| Reconciliation Scheduler | `src/ai_inference/core/reconciliation_scheduler.py` |
| Request TTL | `src/ai_inference/core/ttl.py` |
| Reconciliation | `src/ai_inference/core/reconciliation.py` |
| Admission Control | `src/ai_inference/gateway/admission.py` |
| Tenant Policies | `src/ai_inference/gateway/tenant.py` |
| Auth | `src/ai_inference/gateway/auth.py` |
| vLLM Batch Adapter | `src/ai_inference/inference/vllm_adapter.py` |
| Autoscaler | `src/ai_inference/core/autoscaler.py` |
| Circuit Breaker | `src/ai_inference/inference/circuit_breaker.py` |
| Structured Logger | `src/ai_inference/core/logging.py` |
| Metrics | `src/ai_inference/core/metrics.py` |
| Scaling Executor | `src/ai_inference/core/scaling_executor.py` |
| Priority Queue | `src/ai_inference/core/priority_queue.py` |
| Latency Tracker | `src/ai_inference/inference/latency.py` |
| Audit Trail | `src/ai_inference/core/audit.py` |
| Worker | `src/ai_inference/core/worker.py` |
| Config | `src/ai_inference/core/config.py` |
| CDK Stack | `src/ai_inference/infrastructure/ai_inference_stack.py` |
| Monitoring | `src/ai_inference/monitoring/monitoring.py` |
| Demo Mode | `src/ai_inference/demo.py` |
| Mock vLLM | `scripts/mock_vllm.py` |
| Tests | `tests/unit/` |
| Task Runner | `mise.toml` |
| Python Deps | `pyproject.toml` |

## Design rules

- README.md: reasoning, constraints, tradeoffs, platform intent. Not a stack inventory.
- NEXT_SESSION.md: engineering handoff. What changed, what passed, what is next, what risks remain.
- Each module should be testable in isolation without AWS credentials.
- Demo mode must always work with `mise run demo` and no external dependencies.
