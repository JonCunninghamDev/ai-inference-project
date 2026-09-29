#!/usr/bin/env python3
"""Credential-free CDK synthesis for deployment-readiness verification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import STAGES, build_app  # noqa: E402

DEFAULT_CONFIG = ROOT / "cdk.json"
DEFAULT_OUTDIR = ROOT / "cdk.out"


def load_context(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Load repository-owned CDK context without contacting AWS."""
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    context = payload.get("context")
    if not isinstance(context, dict):
        raise ValueError(f"{config_path} must contain an object-valued 'context'")
    return context


def synthesize(outdir: Path = DEFAULT_OUTDIR) -> list[str]:
    """Synthesize all configured stacks and return their artifact identifiers."""
    outdir.mkdir(parents=True, exist_ok=True)
    app = build_app(context=load_context(), outdir=str(outdir))
    app.synth()

    manifest_path = outdir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts", {})
    expected = [f"AirGappedRag-{stage}" for stage in STAGES]

    missing = [stack for stack in expected if stack not in artifacts]
    if missing:
        raise RuntimeError(f"CDK synthesis did not emit expected stack artifacts: {missing}")

    return expected


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synthesize AI inference CDK templates without AWS credentials."
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=DEFAULT_OUTDIR,
        help=f"Cloud assembly output directory (default: {DEFAULT_OUTDIR})",
    )
    args = parser.parse_args()

    stacks = synthesize(args.outdir)
    print(
        json.dumps(
            {
                "status": "synthesized",
                "outdir": str(args.outdir),
                "stacks": stacks,
                "aws_api_calls": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
