# CDK Synthesis Baseline

Issue: #17  
Status: verified in required consumer CI  
Baseline date: 2026-09-29

## Purpose

This evidence establishes a credential-free infrastructure synthesis baseline before any AWS deployment or GPU provisioning work begins.

## Configuration

- repository branch: `feature/issue-17-cdk-synthesis-baseline`
- production base: `develop`
- stages: `Dev`, `Staging`, `Prod`
- repository command: `mise run synth`
- direct command: `uv run python scripts/synth_infrastructure.py`
- AWS credentials required: no
- AWS API calls intended: no
- deployment/bootstrap intended: no

## Compatibility boundary

The generated CloudFormation stack identifiers remain:

- `AirGappedRag-Dev`
- `AirGappedRag-Staging`
- `AirGappedRag-Prod`

Those names are legacy compatibility identifiers. They are intentionally preserved in this baseline so validation does not silently become an infrastructure migration. Renaming deployed stack identities, monitoring namespaces, service names, or other historical infrastructure identifiers requires a separate migration decision and evidence.

## Verification

The unit suite includes a synthesis regression that:

1. builds the CDK app with repository-owned stage context;
2. synthesizes a cloud assembly to a temporary directory;
3. verifies all three existing stack artifacts;
4. opens each emitted CloudFormation template;
5. verifies resources and key outputs are present.

CI result: passed.

- implementation commit: `d595cf1b31f8953e50b67186511563792e73d06b`
- GitHub Actions run: `36624243406`
- reusable platform workflow: `engineering-platform@b107c9306161b395cbcaffebb55e47850b999560`
- Python: 3.12.14
- unit/synthesis suite: **253 passed in 30.19s**
- CI conclusion: `success`
- AWS credentials used by the synthesis test: none
- AWS resource creation/update/destruction: none

## Known limitations

- Synthesis proves template generation, not deployability or runtime correctness.
- No AWS credentials, account bootstrap, CloudFormation deployment, networking validation, or service health check is performed.
- Existing infrastructure definitions still include legacy naming and security/deployment assumptions documented elsewhere in the repository.
- This baseline does not authorize resource creation or spending.
