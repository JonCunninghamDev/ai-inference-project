#!/usr/bin/env python3
"""AWS CDK application for the AI inference platform.

The CloudFormation stack identifiers intentionally retain the historical
`AirGappedRag-<Stage>` names for this baseline. Renaming those identifiers is
an infrastructure migration and is outside the scope of credential-free
synthesis validation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aws_cdk as cdk

from ai_inference.infrastructure import AirGappedRagStack

STAGES = ("Dev", "Staging", "Prod")
LEGACY_STACK_PREFIX = "AirGappedRag"


def build_app(
    *,
    context: Mapping[str, Any] | None = None,
    outdir: str | None = None,
) -> cdk.App:
    """Build the CDK app without performing any AWS API calls."""
    kwargs: dict[str, Any] = {}
    if context is not None:
        kwargs["context"] = dict(context)
    if outdir is not None:
        kwargs["outdir"] = outdir

    app = cdk.App(**kwargs)
    for stage in STAGES:
        AirGappedRagStack(
            app,
            f"{LEGACY_STACK_PREFIX}-{stage}",
            stage=stage,
        )
    return app


def main() -> None:
    """Synthesize the application when invoked by the CDK CLI."""
    build_app().synth()


if __name__ == "__main__":
    main()
