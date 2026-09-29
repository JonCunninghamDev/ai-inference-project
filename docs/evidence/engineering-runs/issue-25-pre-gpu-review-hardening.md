# Engineering Run: Issue #25 Pre-GPU Review Hardening

Date: 2026-09-29  
Issue: #25  
Pull request: #28  
Engineering Platform: `v1.0.0` / `b107c9306161b395cbcaffebb55e47850b999560`

## Outcome

Converted an external review into explicit pre-spend controls without opening
the GPU/cloud-spend gate.

The change restores blocking syntax, Bandit, and coverage checks; corrects k6
admission/saturation semantics; replaces the fixed 200-VU cap with an explicit
arrival-rate allocation model; and makes the first GPU gateway/metrics topology
loopback-only.

Known debt discovered or reaffirmed during the review is tracked separately:

- #26: Black/isort/flake8/mypy green blocking gate plus persistent coverage history;
- #27: authenticated/private gateway metrics before any public gateway deployment;
- #29: repair or retire the malformed legacy integration suite.

## Delivery measurements

| Metric | Result |
| --- | --- |
| issue created | 2026-09-29 21:39:43 UTC |
| implementation PR created | 2026-09-29 21:42:42 UTC |
| issue-to-PR lead time | 2m 59s |
| first required CI | run 21 / 36635076878 |
| first CI result | failure during compile preflight |
| corrected required CI | run 22 / 36635187143 |
| corrected test execution | 283 passed in 56.37s |
| measured unit coverage | 80% / 2526 statements, 497 missed |
| Bandit medium/high scan | no issues identified |
| failed required-CI runs before corrected head | 1 |
| human GPU/cloud-spend gate crossed | 0 |
| AWS/GPU/IAM/network mutations | 0 |
| cloud spend | $0 |
| rollbacks | 0 |

## Verification failure

Run 21 failed before Bandit or pytest because the newly restored compile
preflight scanned the legacy integration suite and exposed a pre-existing
malformed file:

    tests/integration/test_end_to_end.py

The file contains literal `\n` escape text and is not part of the currently
verified unit suite. The repository already documents the older integration
surface as requiring repair.

The correction did not remove compile validation. Instead:

- required compile validation remains blocking for `src` and `tests/unit`;
- integration repair/retirement is explicitly tracked in #29;
- once that surface is repaired, repository-wide compile/test discovery can be
  expanded deliberately.

## External-review findings

### Security/quality CI

Resolved for the pre-spend gate:

- `python -m compileall -q src tests/unit` is blocking;
- `bandit -r src -ll` is blocking;
- unit coverage is emitted in required CI;
- deployment commands and AWS credential configuration remain absent.

Deferred transparently:

- Black/isort/flake8/mypy are not yet green and blocking;
- persistent coverage artifact/service history is not yet restored.

Those items are issue #26 rather than an implicit claim of completion.

### Saturation semantics

HTTP 429 admission rejection no longer records a false accepted-terminal result.
The benchmark now measures:

- accepted-request terminal success;
- admission rejection rate and count;
- unexpected submission failure;
- poll failure;
- terminal latency;
- dropped iterations.

An admission rejection threshold is optional per rate. This allows deliberate
overload points to show controlled rejection without falsely failing accepted
work reliability.

### Load-generator capacity

k6 preallocates VUs from rate × expected terminal seconds × headroom. Dynamic
maxVUs expansion is not used. Any `dropped_iterations > 0` invalidates that
rate point, preventing a load-generator ceiling from being mislabeled as
service saturation.

### Gateway metrics exposure

The first GPU profile now machine-encodes:

- no public inbound;
- gateway bind 127.0.0.1;
- gateway metrics loopback-only;
- vLLM loopback;
- worker metrics loopback;
- no security-group inbound rules.

Future public gateway metrics protection remains explicitly tracked in #27.

## Governance interpretation

This review materially improved the planned experiment before spend:

- the review was not treated as approval to execute the GPU gate;
- security scanning returned to required CI rather than remaining a README claim;
- a misleading benchmark pass/fail definition was corrected before generating
  real performance evidence;
- pre-existing integration debt surfaced by the new gate was tracked rather
  than suppressed;
- follow-up quality/public-metrics work has durable issue ownership.

The spend authorization remains false throughout this run.
