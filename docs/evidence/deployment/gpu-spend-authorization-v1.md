# GPU Spend Authorization: Production Evidence v1

Date: 2026-09-29  
Issue: #32

## Decision

Approved.

The user explicitly approved the bounded Production Evidence v1 GPU/cloud gate
on 2026-09-29 with: "Let's do it".

## Authorized boundary

- AWS region: `us-east-1`
- instance: one `g6.2xlarge` On-Demand
- GPU: one NVIDIA L4
- maximum session: 3 hours
- maximum total cloud spend: $5.00
- vLLM: `0.30.0`
- container: `vllm/vllm-openai:v0.30.0`
- model: `Qwen/Qwen3-4B-Instruct-2507`
- model revision: `cdbee75f17c01a7cc42f958dc650907174af0554`
- public inbound: none
- gateway, vLLM, and worker metrics: loopback/private baseline
- documented early-stop conditions remain mandatory

## Point-in-time cost recheck

Immediately before approval, current public pricing sources continued to show
Linux On-Demand `g6.2xlarge` in `us-east-1` at approximately $0.9776/hour.

At that rate:

- 3 hours EC2 compute: $2.9328
- existing plan estimate including root EBS and public IPv4: about $2.97
- approved total ceiling: $5.00

Account-specific quota and availability-zone capacity are not assumed. If AWS
cannot place the pinned instance within this boundary, provisioning must stop
rather than substitute another hardware shape.

## Not authorized

This approval does not extend to:

- another region, instance type, GPU, or purchase model;
- more than one GPU instance;
- runtime beyond 3 hours;
- total spend beyond $5;
- public ingress;
- NAT gateways, load balancers, VPNs, or unrelated cloud services;
- weakening the pinned model/runtime/network contracts.

## Governance

The machine-readable authorization is changed through a temporary branch and PR
to `develop`. Provisioning must not begin until required CI passes, the PR is
merged, and the merged authorization state is verified.
