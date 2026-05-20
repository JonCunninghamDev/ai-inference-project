#!/usr/bin/env python3
import aws_cdk as cdk
from src.air_gapped_rag.infrastructure import AirGappedRagStack

app = cdk.App()

# Define our targets
environments = ["Dev", "Staging", "Prod"]

for stage in environments:
    AirGappedRagStack(
        app,
        f"AirGappedRag-{stage}",
        stage=stage,
        # Standardize naming: AirGappedRag-Dev, etc.
    )

app.synth()