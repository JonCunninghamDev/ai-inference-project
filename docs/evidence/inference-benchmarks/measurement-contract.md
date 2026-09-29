# Production Evidence v1 Measurement Contract

Status: contract verified in CI; no hardware performance results yet
Date established: 2026-09-29
Issue: #19

## Purpose

This contract defines what will be measured when the project reaches the first
hardware-backed vLLM run. It intentionally separates client-observed lifecycle
latency, platform control-plane metrics, vLLM engine metrics, and GPU metrics.

No value in this document is evidence of production performance.

## Endpoint contract

The worker configuration uses VLLM_URL as the server root, for example:

    http://127.0.0.1:8000

The inference adapter normalizes that root into:

    OpenAI-compatible API: http://127.0.0.1:8000/v1
    vLLM metrics:          http://127.0.0.1:8000/metrics
    vLLM health:           http://127.0.0.1:8000/health

Callers may also provide a URL ending in /v1; the platform normalizes it back
to the same server root before deriving the metrics endpoint.

## Metric sources

### 1. Client/load generator

The k6 workload submits POST /v1/inference and polls
GET /v1/inference/{request_id} until completed, failed, or timed out.

Primary metrics:

- inference_terminal_latency_ms: submit start through observed terminal result.
- inference_terminal_success: completed terminal results divided by attempted iterations.
- inference_rejected_total: HTTP 429 admission/tenant rejections.
- http_req_duration and http_req_failed: HTTP-level behavior from k6.

Important: inference_terminal_latency_ms is not TTFT. The public API is
asynchronous and polling-based, so client-visible TTFT is not currently
observable. TTFT comes from the vLLM engine metrics below until a future
streaming/synchronous path is implemented.

### 2. AI inference platform metrics

The gateway exposes Prometheus text format at /metrics.

Bounded metric families currently include:

- ai_inference_gateway_requests_total
- ai_inference_worker_requests_total
- ai_inference_queue_wait_seconds
- ai_inference_inference_duration_seconds
- ai_inference_batch_size
- ai_inference_batch_estimated_tokens
- ai_inference_scheduling_decisions_total
- ai_inference_reconciliation_requests_total

Request IDs and raw error strings are deliberately excluded from Prometheus
labels to prevent unbounded cardinality.

Process boundary note:

- In demo mode, gateway and demo worker share one MetricsCollector, so the
  gateway /metrics endpoint can contain both control-plane and worker aggregates.
- In a distributed deployment, gateway and worker are separate processes.
- Issue #21 adds an opt-in worker metrics listener with a private-only bind
  contract. It is disabled by default, binds to 127.0.0.1 by default, and
  rejects wildcard/public bind addresses.
- A remote Prometheus deployment still requires a separately approved private
  network/security-group path. The process listener does not authorize public
  exposure.

### 3. vLLM native metrics

Current vLLM production metrics are expected at /metrics. The initial dashboard
and benchmark queries should include at least:

- vllm:num_requests_running
- vllm:num_requests_waiting
- vllm:kv_cache_usage_perc
- vllm:prompt_tokens_total
- vllm:generation_tokens_total
- vllm:time_to_first_token_seconds
- vllm:request_time_per_output_token_seconds
- vllm:e2e_request_latency_seconds
- vllm:request_queue_time_seconds
- vllm:request_prefill_time_seconds
- vllm:request_decode_time_seconds

The exact metric inventory must be captured from the deployed vLLM /metrics
endpoint because availability can change with vLLM version and enabled features.

### 4. NVIDIA GPU metrics

DCGM Exporter is expected to expose Prometheus metrics at /metrics on port 9400.
Initial GPU evidence should include at least:

- DCGM_FI_DEV_GPU_UTIL
- DCGM_FI_DEV_FB_USED
- DCGM_FI_DEV_FB_FREE
- DCGM_FI_DEV_GPU_TEMP
- DCGM_FI_DEV_POWER_USAGE

The effective runtime /metrics output is authoritative because GPU, driver,
DCGM, exporter version, and collector configuration determine availability.

## Prometheus baseline

config/observability/prometheus.yml defines a single-node baseline with four
scrape jobs:

- 127.0.0.1:8080 for the inference gateway
- 127.0.0.1:9101 for the worker
- 127.0.0.1:8000 for vLLM
- 127.0.0.1:9400 for DCGM Exporter

This is a configuration contract only. It does not deploy Prometheus, open
ports, or alter network policy. A real distributed deployment must replace
targets with approved reachable addresses.

## Benchmark profile

benchmarks/profiles/production-evidence-v1.json defines the first planned
hardware-backed profile. The model and exact revision remain unset until the
GPU provisioning gate, so model choice cannot silently change between runs.

The initial load sequence is arrival-rate based:

    1, 5, 10, 25, 50, 100, 200 requests/second

Each level should run long enough to reach a stable operating regime. The
profile currently specifies five minutes per level. If the deployed service
saturates earlier, record the saturation point and stop escalating rather than
turning the benchmark into an uncontrolled failure test.

## Comparison rules

A result is comparable only when it records:

- git commit
- model and exact revision
- vLLM version and serving arguments
- GPU/instance type and count
- input and requested output token distribution
- arrival rate or concurrency model
- batching and admission settings
- run duration and sample count
- metric scrape interval
- k6 parameters
- any failure injection in effect

Change one primary variable at a time where practical.

## External contracts reviewed

- vLLM production metrics documentation:
  https://docs.vllm.ai/en/stable/usage/metrics/
- vLLM metrics design:
  https://docs.vllm.ai/en/latest/design/metrics/
- NVIDIA DCGM Exporter:
  https://docs.nvidia.com/datacenter/dcgm/latest/reference/command-line-reference/dcgm-exporter.html
- NVIDIA DCGM Exporter metrics:
  https://docs.nvidia.com/datacenter/dcgm/latest/reference/dcgm-exporter-metrics.html
- Grafana k6 thresholds:
  https://grafana.com/docs/k6/latest/using-k6/thresholds/


## CI verification

The pre-GPU measurement contract and its deterministic tests were verified on
the corrected implementation head:

- commit: `1b092785fce676ae86e6aa82cd6629ffbb0c69ef`
- GitHub Actions run: `36626756651`
- Engineering Platform reusable workflow:
  `b107c9306161b395cbcaffebb55e47850b999560`
- Python: 3.12
- unit suite: **264 passed in 24.33s**
- result: `success`
- AWS/GPU resources created: none
- IAM/network changes: none

This verification establishes configuration and measurement-path correctness
only. It does not establish model throughput, TTFT, TPOT, saturation behavior,
GPU efficiency, or production reliability.
