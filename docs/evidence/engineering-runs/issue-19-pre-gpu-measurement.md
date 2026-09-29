# Engineering Run: Issue #19 Pre-GPU Measurement Path

Date: 2026-09-29  
Issue: #19  
Pull request: #20  
Engineering Platform: `v1.0.0` / `b107c9306161b395cbcaffebb55e47850b999560`

## Outcome

Established the pre-GPU observability and load-generation contract needed for
Production Evidence v1 without crossing a cloud-resource, GPU-spend, IAM, or
network-exposure human gate.

The change added bounded Prometheus control-plane metrics, normalized vLLM API
and metrics endpoints, Prometheus scrape targets for the gateway/vLLM/DCGM,
an asynchronous k6 lifecycle workload, and a reproducible benchmark profile.
It also records the production process-boundary limitation that worker metrics
are not yet exposed over a separately reachable listener.

## Delivery measurements

| Metric | Result |
| --- | --- |
| issue created | 2026-09-29 20:18:50 UTC |
| implementation PR created | 2026-09-29 20:27:56 UTC |
| issue-to-PR lead time | 9m 06s |
| commits present when PR opened | 16 |
| commits before evidence finalization | 20 |
| first required CI started | 2026-09-29 20:28:01 UTC |
| first required CI result | failure |
| failed required-CI runs before corrected head | 2 |
| first corrected-head green CI | run 10 / 36626756651 |
| PR-to-corrected-green time | 2m 50s |
| corrected-head test execution | 264 passed in 24.33s |
| review rework | 0 reviewer-requested changes |
| human consequential-action gates crossed | 0 |
| AWS/GPU/IAM/network mutations | 0 |
| rollbacks | 0 |

An additional required CI run is expected after this evidence-only commit.
That run validates the final evidence text and is not implementation rework.

## Verification failures

Two required-CI runs failed before the corrected head became green.

### Run 7: 36626528622

The initial PR head contained literal `\n` text in multiline Python import
statements in three files:

- `src/ai_inference/gateway/api.py`
- `src/ai_inference/core/worker.py`
- `src/ai_inference/demo.py`

Pytest stopped during collection with eight collection errors caused by Python
`SyntaxError`. This was an edit/serialization defect, not a model-serving
architecture failure.

### Run 8: 36626703707

The repair was applied sequentially across files. GitHub Actions triggered on
an intermediate branch head before all three malformed imports were corrected,
so that intermediate run also failed.

Run 9 was green after all malformed imports were repaired. Run 10 was green on
the final implementation head after the demo Prometheus composite sink was
wired correctly.

## Governance observations

The Engineering Platform controls affected the work in useful ways:

- the issue defined the non-goals before implementation;
- the work stayed on a temporary branch from `develop`;
- CI prevented malformed source from reaching `develop`;
- the worker metrics process-boundary problem was documented instead of being
  bypassed by opening a new listener;
- network exposure and GPU/cloud spending remained behind explicit human gates;
- the benchmark contract distinguishes asynchronous terminal latency from
  vLLM-native TTFT rather than making an unsupported client-latency claim.

The failed runs are retained as process evidence rather than omitted from the
record.

## Process improvement candidate

A fast syntax/compile preflight would have detected the malformed imports before
the complete unit suite was started. A future engineering-process improvement
should evaluate a deterministic check such as:

    python -m compileall -q src tests

This observation should be compared with future runs before changing the shared
Engineering Platform contract. It is evidence for a possible improvement, not
yet proof that a platform-wide change is warranted.

## Regression / progress interpretation

Runtime performance is still unmeasured because no real GPU/model workload has
been run.

Process signal is mixed:

- positive: scope/gates prevented accidental cloud or network changes and the
  final implementation reached 264 passing tests;
- negative: two CI runs were consumed by a source-edit syntax defect that a
  cheaper preflight could have detected.

This run therefore provides a useful regression datapoint for engineering
efficiency while still producing the intended technical result.
