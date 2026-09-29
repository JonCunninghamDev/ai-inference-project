# Repository Steering

This repository adopts Engineering Platform v1.0.0, pinned to immutable commit `b107c9306161b395cbcaffebb55e47850b999560`.

## Authority and startup

At the start of engineering work:

1. Verify repository and branch state.
2. Read `README.md`, this file, `engineering-policy.json`, and the active issue.
3. Read `docs/engineering-platform/operating-contract-v1.md`.
4. Inspect open pull requests, CI, review state, and partially completed work before creating a branch.
5. Use repository state rather than conversational memory as the durable source of truth.

Instruction precedence is: safety/tool constraints, direct human instruction, accepted issue criteria, repository product/architecture docs, repository-local steering, pinned Engineering Platform contract.

## Branch model

Exactly two long-lived branches are expected:

- `main`: production/released state.
- `develop`: integration state and base for normal engineering work.

Normal work is:

```text
sync main -> develop when needed
develop -> temporary feature/fix branch
temporary branch -> PR -> develop
green required CI -> merge
delete temporary branch
```

Production promotion is separate:

```text
develop -> PR -> main
full required CI
explicit human approval
merge commit
sync resulting main history back into develop
```

Do not implement directly on `main` or `develop`. Do not use a direct-to-main hotfix route.

## Validation

The required shared check is `Platform Consumer CI`, pinned by immutable Engineering Platform release commit. It runs the complete unit suite under Python 3.12.

Use narrow deterministic tests while developing, then the complete repository-required validation before merge. Do not claim success from queued CI, compilation alone, or mocked happy paths.

## Human gates

Explicit human approval is required before:

- creating or materially resizing cloud resources;
- creating or enabling GPU resources or material recurring cloud spend;
- changing IAM authority, credentials, secrets, authentication, or authorization;
- changing security-group, firewall, VPN, public/private network exposure, or equivalent network trust boundaries;
- destructive infrastructure or data operations;
- production deployment;
- `develop -> main` release promotion;
- backward-incompatible public contracts;
- ambiguous cross-repository changes.

Prepare the proposed change, validation evidence, expected cost/risk, and rollback path before requesting the gate.

## Deployment safety

CI must not deploy infrastructure merely because code is pushed to `develop` or `main`. Deployment is a separately authorized action. The retired legacy Air-Gapped RAG workflow is not an authoritative deployment path.

## Evidence discipline

This project distinguishes implemented behavior, locally/CI-verified behavior, and production evidence.

Engineering-process evidence and inference-runtime evidence are tracked according to `docs/engineering-evidence.md`. Performance or reliability claims must identify the model, hardware, workload, configuration, and measurement window needed to reproduce the result.

## Platform upgrades

Do not follow moving Engineering Platform branches. Upgrade only to a verified published release through a focused PR that records current/target pins, compatibility impact, complete consumer CI evidence, and rollback instructions.
