# Engineering and Runtime Evidence

This repository tracks two distinct evidence streams: how engineering work is delivered and how the inference platform behaves at runtime.

The objective is to detect both improvement and regression without conflating software-delivery efficiency with serving-system performance.

## Baseline

Baseline date: 2026-09-29.

Repository state at baseline:

- `main` and `develop` synchronized at `5e3b5b7043291508d7f3a79e61fe43633e2a0577`;
- Engineering Platform target pin: `v1.0.0` / `b107c9306161b395cbcaffebb55e47850b999560`;
- repository README reports 245 passing unit tests in the latest released verification;
- current production-performance evidence is intentionally absent;
- the legacy Air-Gapped RAG CI/CD workflow existed before adoption and allowed automatic development deployment; adoption retires that path.

The adoption PR's Platform Consumer CI becomes the independent verification point for the unit-suite baseline.

## Engineering-delivery evidence

For meaningful implementation PRs, retain enough issue/PR/CI evidence to derive:

| Metric | Definition |
| --- | --- |
| issue-to-PR lead time | issue creation or work-start time to first implementation PR |
| PR-to-green time | PR creation to first complete required-CI success |
| CI attempts | number of required-CI runs before merge |
| implementation commits | commits produced on the temporary branch before merge |
| verification failures | deterministic validation failures requiring code/config changes |
| review rework | post-review commits required before acceptance |
| human gates | consequential actions that required explicit human approval |
| rollback count | merged changes reverted because accepted behavior regressed |
| abandoned work | task branches/approaches intentionally discarded before merge |

These metrics are descriptive. A faster run is not automatically better if it increases rework, rollback, or escaped defects.

## Inference-runtime evidence

Production Evidence v1 will establish reproducible measurements for:

| Area | Metrics |
| --- | --- |
| request latency | p50, p95, p99 end-to-end latency |
| LLM responsiveness | TTFT p50/p95/p99 |
| generation | TPOT and output tokens/second |
| capacity | requests/second and concurrent requests |
| queueing | queue depth and queue-wait distribution |
| batching | average/effective batch size and batch wait |
| admission | accepted/rejected requests and rejection rate |
| reliability | success, failure, timeout, and recovery rates |
| GPU | utilization, memory use, thermals/power where available |
| vLLM | running/waiting requests, KV-cache utilization, prefill/decode observations |
| recovery | time to circuit-break/recover and stale-request reconciliation outcomes |
| cost | instance/runtime cost normalized to a declared request/token workload |

## Reproducibility requirements

A performance result is not comparable unless it records at minimum:

- git commit;
- model and exact model version/revision;
- serving runtime and relevant configuration;
- instance/GPU type and count;
- input-token and requested-output-token distribution;
- concurrency/load-generation pattern;
- duration/sample count;
- batching/admission settings;
- measurement source and metric definitions.

Comparisons should change one primary variable at a time where practical.

## Regression rules

A change is a runtime regression when it worsens a declared target metric outside an explicitly accepted tradeoff under the same benchmark definition.

Examples:

- throughput improves while p95 TTFT exceeds the declared SLO: record both, do not call the change an unqualified improvement;
- admission control increases rejection rate while keeping accepted-request p99 bounded during overload: record the tradeoff;
- engineering lead time falls while CI retries or rollback frequency rises: do not treat speed alone as process improvement.

## Evidence storage

As measurements become available, store reproducible summaries under:

- `docs/evidence/engineering-runs/`
- `docs/evidence/inference-benchmarks/`

Raw high-volume telemetry may live in external monitoring/storage, but repository summaries must identify the exact query/export/run needed to reproduce the reported result.
