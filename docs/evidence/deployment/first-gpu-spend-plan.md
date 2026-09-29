# First GPU Baseline Spend Plan

Status: plan verified in required consumer CI; GPU/cloud spend is **not approved**
Date captured: 2026-09-29
Issue: #23

## Purpose

This plan pins the first hardware-backed Production Evidence v1 runtime so the
cloud-spend gate can be decided against a concrete, reproducible configuration.

Merging this plan does not create AWS resources or authorize spend.

## Pinned baseline

| Dimension | Value |
| --- | --- |
| Cloud | AWS |
| Region | us-east-1 |
| EC2 instance | g6.2xlarge |
| Purchase model | On-Demand |
| GPU | 1 x NVIDIA L4 |
| GPU memory | 22 GiB usable as reported in the EC2 instance-type specification |
| Host memory | 32 GiB |
| Local NVMe | 1 x 450 GB |
| vLLM | 0.30.0 |
| Container | vllm/vllm-openai:v0.30.0 |
| Model | Qwen/Qwen3-4B-Instruct-2507 |
| Model revision | cdbee75f17c01a7cc42f958dc650907174af0554 |
| Model license | Apache-2.0 |
| Model repository size | about 8.06 GB |
| AMI family | Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 26.04) |
| AMI resolution | AWS public SSM parameter at launch time |

The benchmark profile in
`benchmarks/profiles/production-evidence-v1.json` is the machine-readable
source for these values.

## Why this instance/model pair

A single L4 gives us the hardware class the roadmap originally targeted while
remaining inexpensive enough for repeated controlled experiments. The 4B Qwen
model is small relative to the L4 memory budget, so the first run can focus on
serving behavior rather than immediately introducing quantization, tensor
parallelism, or multi-GPU complexity.

This first run is intentionally not a maximum-capacity benchmark. It is a
reproducible baseline from which later changes can be measured.

## Current cost basis

Captured 2026-09-29 and must be rechecked immediately before launch.

Current public EC2 price indexes show Linux On-Demand `g6.2xlarge` in
`us-east-1` at approximately **$0.9776/hour**.

Planned ceiling:

| Item | Estimate |
| --- | ---: |
| 3 hours EC2 compute | $2.9328 |
| 64 GiB gp3 root EBS for 3 hours at $0.08/GiB-month | about $0.021 |
| one public IPv4 for 3 hours at $0.005/hour | $0.015 |
| known subtotal | about $2.97 |
| first-session approval ceiling | **$5.00** |

The 35-minute load sequence itself, if run continuously at the current
On-Demand rate, is about **$0.57 of EC2 compute**.

The $5 ceiling provides buffer for setup time and small incidental AWS charges.
It does not authorize unrelated services or a longer-running instance.

Spot is not proposed for this first baseline. The current lowest indexed Spot
price for this instance in us-east-1 is only slightly below On-Demand, so the
small savings do not justify interruption risk for the first reproducible run.

## AMI/runtime contract

Resolve the latest x86_64 AWS Deep Learning Base OSS Nvidia Driver GPU AMI at
launch time through the AWS public SSM parameter:

    /aws/service/deeplearning/ami/x86_64/base-oss-nvidia-driver-gpu-ubuntu-26.04/latest/ami-id

AWS currently documents this AMI family as supporting G6 and including the
NVIDIA driver, CUDA stack, NVIDIA Container Toolkit, DCGM, containerd, and SSM
Agent.

The vLLM runtime is pinned independently of the AMI:

    vllm/vllm-openai:v0.30.0

The model must be served using both the model name and immutable revision:

    Qwen/Qwen3-4B-Instruct-2507
    cdbee75f17c01a7cc42f958dc650907174af0554

No benchmark result is valid if the model revision or runtime version silently
changes.

## First-session network/security shape

The first paid session is a smoke/performance baseline, not a public service.

Required shape:

- no inbound SSH;
- no public application ingress;
- security group inbound rules: none;
- administration through AWS Systems Manager Session Manager;
- one public IPv4 may be used for outbound internet access while the security
  group still allows no inbound connections;
- outbound HTTPS is used for container/model retrieval and AWS control-plane
  access;
- vLLM binds to loopback;
- worker metrics bind to loopback;
- Prometheus and DCGM metrics are host-local;
- no load balancer, public API, production DNS, or production deployment.

If the actual launch path would require a new VPC, NAT gateway, VPC endpoint,
VPN, public listener, or security-group ingress rule, stop and request a
separate infrastructure/network gate before creation.

## Session controls

The paid session must use all of these controls:

1. Record the AWS account/region, resolved AMI ID, instance ID, launch timestamp,
   git commit, vLLM image digest if available, model revision, and benchmark
   parameters.
2. Set a three-hour maximum session budget.
3. Verify the instance reaches SSM before any model setup.
4. Verify `nvidia-smi`, Docker/NVIDIA runtime, DCGM, and available disk before
   downloading the model.
5. Start vLLM on loopback and capture its `/metrics` inventory before load.
6. Run smoke requests before the full arrival-rate sequence.
7. Stop escalation when the service clearly saturates rather than forcing every
   configured rate.
8. Export/save benchmark and metric evidence before shutdown.
9. Terminate the EC2 instance at the end of the session.
10. Verify the instance state is terminated and no experiment-only billable
    resource remains.

## Automatic/early stop conditions

Terminate the run early if any of these occur:

- accumulated or projected session cost would exceed the approved ceiling;
- model revision cannot be verified;
- vLLM cannot start cleanly on the pinned runtime;
- GPU is not the expected L4 device;
- metrics required for the baseline cannot be captured;
- unexpected public ingress becomes reachable;
- benchmark behavior indicates data loss/corruption rather than ordinary
  saturation;
- the experiment cannot be completed within the three-hour window.

## Rollback

Before provisioning:
- revert this focused plan if the baseline changes.

After a future approved provisioning:
- terminate the GPU instance;
- delete experiment-only IAM instance profile/role only if it was created for
  this run and is not shared;
- delete experiment-only security group only if it was created for this run;
- release any experiment-only public IPv4 allocation;
- delete experiment-only EBS volume if it is not configured for delete-on-
  termination;
- verify the AWS console/billing inventory has no running GPU resource.

## Sources captured 2026-09-29

Authoritative or primary sources:

- AWS G6 instance specifications:
  https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html
- AWS accelerated-computing G6 overview:
  https://aws.amazon.com/ec2/instance-types/accelerated-computing/
- AWS Deep Learning Base GPU AMI Ubuntu 26.04 and public SSM parameter:
  https://docs.aws.amazon.com/dlami/latest/devguide/aws-deep-learning-x86-base-gpu-ami-ubuntu-26-04.html
- AWS 20260925 DLAMI release details:
  https://docs.aws.amazon.com/dlami/latest/devguide/aws-deep-learning-ami-gpubaseoss-ul2604-2026-09-28.html
- AWS gp3 pricing:
  https://aws.amazon.com/ebs/pricing/
- AWS public IPv4 pricing:
  https://aws.amazon.com/vpc/pricing/
- vLLM releases:
  https://github.com/vllm-project/vllm/releases
- Qwen model repository:
  https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507
- exact Qwen revision:
  https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/commit/cdbee75f17c01a7cc42f958dc650907174af0554

Current-price indexes used for the point-in-time EC2/Spot rate:

- https://www.doit.com/compute/compute/aws/us-east-1/g6.2xlarge
- https://www.economize.cloud/resources/aws/pricing/ec2/g6.2xlarge/

These pricing indexes are point-in-time evidence, not an immutable AWS quote.
Recheck price and capacity immediately before launch.


## CI verification

Planning head verified before the spend gate:

- implementation commit: `940922c421d9e904c61a12d0a4abe70d7ed4ef16`
- GitHub Actions run: `36630520190`
- Python: 3.12
- unit suite: **283 passed in 35.50s**
- conclusion: `success`
- AWS/GPU resources created: none
- cloud spend incurred by this issue: $0

The GPU/cloud spend authorization flag remains false after this verification.
