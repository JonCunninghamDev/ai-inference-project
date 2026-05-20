# Inference Platform Module Log

This file tracks the platform evolution at the module level.

## Module 1: Model Routing

Status: complete

Purpose: establish an explainable model selection layer before optimizing batching, scheduling, latency, or cost.

Key files:

- `src/ai_inference/inference/router.py`
- `tests/unit/test_router.py`

Core idea: every request should receive a deterministic routing decision with a reason code.

## Module 2: Inference Gateway API

Status: complete

Purpose: add a stable platform entry point that separates client request intake from isolated model execution.

Key files:

- `src/ai_inference/gateway/api.py`
- `tests/unit/test_gateway.py`

Core idea: the gateway is the control plane. It validates requests, runs model routing, returns routing visibility, derives idempotency keys, and publishes normalized work to the queue.

## Module 3: Dynamic Batching

Status: complete

Purpose: improve throughput by grouping compatible inference requests while preserving latency and policy boundaries.

Key files:

- `src/ai_inference/inference/batching.py`
- `tests/unit/test_batching.py`
- `src/ai_inference/core/worker.py`

Core idea: batching should be deterministic, explainable, and conservative before it becomes aggressive. Requests are grouped only when they share the same routed model and event type, are batchable, are not high priority, and fit within the batch size and token budget.

## Module 4: GPU Aware Scheduling

Status: complete

Purpose: add an explicit capacity check before a worker commits a batch to a model.

Key files:

- `src/ai_inference/inference/gpu_scheduler.py`
- `tests/unit/test_gpu_scheduler.py`
- `src/ai_inference/core/worker.py`
- `src/ai_inference/core/config.py`

Core idea: the platform should not treat every worker as equally capable. Before execution, a batch is checked against model resource profiles, GPU memory reserve, utilization limits, device health, and model-specific maximum batch size. This starts as deterministic local policy, with an intentional extension point for NVML, Kubernetes device plugins, or fleet inventory APIs later.

## Module 5: Observability and Latency Metrics

Status: recommended next

Purpose: measure the system before adding autoscaling, latency-aware routing, or more aggressive scheduling.

Planned capabilities:

- queue wait time metrics
- model latency metrics
- batch size metrics
- estimated token load metrics
- GPU scheduling decision metrics
- success and failure counters by model
- local JSONL metrics sink for air gapped operation
- clear extension point for CloudWatch or Prometheus exporters
