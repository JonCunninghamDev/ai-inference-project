# Engineering Run: Issue #21 Private Worker Metrics Export

Date: 2026-09-29  
Issue: #21  
Pull request: #22  
Engineering Platform: `v1.0.0` / `b107c9306161b395cbcaffebb55e47850b999560`

## Outcome

Implemented an opt-in, private-only Prometheus listener for distributed worker
metrics without creating or changing cloud infrastructure.

The listener is disabled by default, binds to 127.0.0.1:9101 by default, and
rejects wildcard/public/hostname binds. Worker lifecycle management starts and
stops the listener only when explicitly enabled.

## Delivery measurements

| Metric | Result |
| --- | --- |
| issue created | 2026-09-29 20:47:05 UTC |
| implementation PR created | 2026-09-29 20:50:25 UTC |
| issue-to-PR lead time | 3m 20s |
| first required CI | run 14 / 36629185733 |
| first CI result | failure: 6 failed, 275 passed |
| corrected required CI | run 15 / 36629376165 |
| corrected-head result | 281 passed in 29.45s |
| failed required-CI runs before corrected head | 1 |
| reviewer-requested rework | 0 |
| network-exposure human gate | approved before implementation |
| AWS/GPU/IAM/security-group/VPN mutations | 0 |
| rollbacks | 0 |

## Verification failure

Run 14 failed because the existing `TestRAGWorker._make_mock_config` fixture
predated the new metrics settings. Python Mock auto-created truthy attributes
for `worker_metrics_enabled`, `worker_metrics_host`, and
`worker_metrics_port`. The worker therefore attempted to instantiate the
listener with a Mock object as the bind host.

The production code's secure validation correctly rejected that value. The
repair updated the worker test fixture with the real secure defaults:

    metrics_enabled=True
    worker_metrics_enabled=False
    worker_metrics_host=127.0.0.1
    worker_metrics_port=9101

No production security rule was weakened to satisfy the tests.

## Governance observations

- The network-exposure gate was explicitly separated from GPU/cloud-spend
  authorization.
- The implementation defaults to no new listener, so merge alone does not
  alter runtime exposure.
- The listener rejects wildcard/public binds at process level.
- Remote scraping still requires a separately reviewed private infrastructure
  path; this issue does not silently open a security group.
- CI exposed fixture drift before the change reached `develop`.
- The repair aligned tests with secure defaults rather than relaxing the
  private-bind contract.

## Process interpretation

This run provides a useful contrast with issue #19. The failure was not a syntax
serialization error; it was compatibility drift in an older test fixture.

That suggests two separate process-improvement categories are emerging:

1. fast syntax/compile preflight for malformed source;
2. fixture/schema synchronization when configuration contracts expand.

Neither is yet promoted into the shared Engineering Platform. More measured
consumer runs should determine whether they recur enough to justify a reusable
platform check.
