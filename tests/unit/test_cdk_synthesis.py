from __future__ import annotations

import json
from pathlib import Path

from app import LEGACY_STACK_PREFIX, STAGES, build_app

ROOT = Path(__file__).resolve().parents[2]


def _context() -> dict:
    payload = json.loads((ROOT / "cdk.json").read_text(encoding="utf-8"))
    return payload["context"]


def test_cdk_app_uses_current_package_import() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "air_gapped_rag" not in source
    assert "from ai_inference.infrastructure import AirGappedRagStack" in source


def test_cdk_synth_emits_all_existing_stage_templates(tmp_path: Path) -> None:
    outdir = tmp_path / "cdk.out"
    app = build_app(context=_context(), outdir=str(outdir))
    app.synth()

    manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
    artifacts = manifest["artifacts"]
    expected = {f"{LEGACY_STACK_PREFIX}-{stage}" for stage in STAGES}

    assert expected <= set(artifacts)

    for stack_name in sorted(expected):
        artifact = artifacts[stack_name]
        assert artifact["type"] == "aws:cloudformation:stack"

        template_file = artifact["properties"]["templateFile"]
        template = json.loads((outdir / template_file).read_text(encoding="utf-8"))
        assert template["Resources"]
        assert {"QueueUrl", "ResultTableName", "LogGroupName"} <= set(
            template["Outputs"]
        )


def test_cdk_synth_preserves_existing_stack_identifiers() -> None:
    assert tuple(f"{LEGACY_STACK_PREFIX}-{stage}" for stage in STAGES) == (
        "AirGappedRag-Dev",
        "AirGappedRag-Staging",
        "AirGappedRag-Prod",
    )
