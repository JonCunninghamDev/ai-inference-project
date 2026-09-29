from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "engineering-policy.json"
PLATFORM_CI = ROOT / ".github" / "workflows" / "platform-consumer-ci.yml"
LEGACY_CI = ROOT / ".github" / "workflows" / "ci-cd.yml"

EXPECTED_PLATFORM_VERSION = "v1.0.0"
EXPECTED_PLATFORM_COMMIT = "b107c9306161b395cbcaffebb55e47850b999560"


def _policy() -> dict:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def test_engineering_platform_pin_is_immutable_v1_release() -> None:
    policy = _policy()
    assert policy["platform"]["repository"] == "JonCunninghamDev/engineering-platform"
    assert policy["platform"]["version"] == EXPECTED_PLATFORM_VERSION
    assert policy["platform"]["commit"] == EXPECTED_PLATFORM_COMMIT
    assert policy["compatibility"]["minimum_platform_version"] == "1.0.0"


def test_two_long_lived_branch_roles_are_explicit() -> None:
    branches = _policy()["branches"]
    assert branches["release"] == "main"
    assert branches["integration"] == "develop"


def test_platform_consumer_ci_is_required_and_pinned() -> None:
    policy = _policy()
    assert "Platform Consumer CI" in policy["review"]["required_checks"]

    workflow = PLATFORM_CI.read_text(encoding="utf-8")
    assert EXPECTED_PLATFORM_COMMIT in workflow
    assert "tests/unit -q" in workflow
    assert "cdk deploy" not in workflow
    assert "configure-aws-credentials" not in workflow


def test_consequential_infrastructure_actions_require_human_approval() -> None:
    policy = _policy()
    required = set()
    for override in policy.get("overrides", []):
        required.update(
            override.get("restrictions", {}).get("require_human_approval_for", [])
        )

    assert {
        "cloud_resource_creation",
        "gpu_resource_creation",
        "recurring_cost_increase",
        "iam_change",
        "network_exposure_change",
        "production_deployment",
    } <= required


def test_legacy_automatic_deployment_workflow_is_retired() -> None:
    assert PLATFORM_CI.exists()
    assert not LEGACY_CI.exists()
