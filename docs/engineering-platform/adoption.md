# Engineering Platform Adoption

## Verified release

This repository adopts the published Engineering Platform release below:

- repository: `JonCunninghamDev/engineering-platform`
- release: `v1.0.0`
- immutable release commit: `b107c9306161b395cbcaffebb55e47850b999560`
- adoption date: 2026-09-29

The release was verified against the Engineering Platform production branch and published GitHub release before adoption.

## Local synchronized surfaces

The consumer remains operable without runtime access to the Engineering Platform repository.

Local authoritative adoption files are:

- `AGENTS.md`: repository-specific steering and human gates;
- `engineering-policy.json`: machine-readable platform pin, branch roles, permissions, validation, and restrictions;
- `docs/engineering-platform/operating-contract-v1.md`: synchronized copy of the pinned shared operating contract;
- `.github/workflows/platform-consumer-ci.yml`: consumer CI invocation pinned to the immutable release commit;
- `docs/engineering-evidence.md`: repository-owned evidence definitions.

Product architecture, model-serving behavior, AWS design, workload definitions, SLOs, credentials, environments, and deployment decisions remain owned by this repository.

## CI contract

The repository calls the reusable Engineering Platform consumer workflow by immutable commit SHA, not a moving branch.

The consumer configuration:

- Python 3.12;
- `uv` installation enabled;
- install: `uv sync --frozen --extra dev --extra test`;
- test: `uv run pytest tests/unit -q`;
- no deployment action;
- no cloud credentials.

The stable required check is `Platform Consumer CI`.

## Deployment boundary

A CI pass is evidence that the repository's configured validation passed. It is not authorization to create AWS resources or deploy a model-serving environment.

Cloud/GPU provisioning, IAM or network changes, destructive infrastructure changes, production deployment, and release promotion remain explicit human gates.

## Upgrade process

For a future Engineering Platform release:

1. Verify the new published tag and immutable commit against platform `main`.
2. Create a focused branch from current `develop`.
3. Record current and target pins and compatibility impact.
4. Update the local pin, synchronized contract files, and reusable workflow reference.
5. Run complete consumer CI.
6. Preserve repository-specific gates and exceptions.
7. Merge to `develop` only after required CI is green.
8. Delete the temporary branch after merge.

Do not adopt unreleased Engineering Platform `develop` state.

## Rollback

If an Engineering Platform upgrade causes a consumer regression, revert the focused upgrade/adoption change to the last accepted immutable pin and rerun the complete consumer CI suite.

Rollback must not re-enable automatic infrastructure deployment. Deployment authorization is independent from Engineering Platform version rollback.
