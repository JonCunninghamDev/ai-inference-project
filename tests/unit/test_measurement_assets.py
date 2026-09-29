from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_prometheus_baseline_has_four_measurement_targets() -> None:
    config = (ROOT / "config" / "observability" / "prometheus.yml").read_text(
        encoding="utf-8"
    )

    assert "127.0.0.1:8080" in config
    assert "127.0.0.1:9101" in config
    assert "127.0.0.1:8000" in config
    assert "127.0.0.1:9400" in config
    assert config.count("metrics_path: /metrics") == 4


def test_benchmark_profile_separates_terminal_latency_from_ttft() -> None:
    profile = json.loads(
        (
            ROOT
            / "benchmarks"
            / "profiles"
            / "production-evidence-v1.json"
        ).read_text(encoding="utf-8")
    )

    assert profile["api_mode"] == "asynchronous_polling"
    assert "not TTFT" in profile["slo_baseline"]["note"]
    assert "vllm:time_to_first_token_seconds" in profile["metric_sources"]["vllm"]
    assert "inference_terminal_latency_ms" in profile["metric_sources"]["load_generator"]
    assert profile["workload"]["arrival_rates_rps"] == [1, 5, 10, 25, 50, 100, 200]


def test_k6_workload_polls_to_terminal_state_without_claiming_ttft() -> None:
    script = (
        ROOT / "benchmarks" / "k6" / "async_inference.js"
    ).read_text(encoding="utf-8")

    assert "POST" not in script
    assert "'/v1/inference'" in script
    assert "'/v1/inference/' + requestId" in script
    assert "inference_terminal_latency_ms" in script
    assert "inference_terminal_success" in script
    assert "inference_rejected_total" in script
    assert "ttft" not in script.lower()


def test_vllm_example_pins_model_revision_and_runtime() -> None:
    config = (
        ROOT
        / "config"
        / "vllm"
        / "production-evidence-v1.env.example"
    ).read_text(encoding="utf-8")

    assert "VLLM_URL=http://127.0.0.1:8000" in config
    assert "VLLM_MODEL=Qwen/Qwen3-4B-Instruct-2507" in config
    assert (
        "VLLM_MODEL_REVISION="
        "cdbee75f17c01a7cc42f958dc650907174af0554"
    ) in config
    assert "VLLM_RUNTIME_VERSION=0.30.0" in config
    assert "VLLM_CONTAINER=vllm/vllm-openai:v0.30.0" in config


def test_production_evidence_profile_keeps_gpu_spend_gate_closed() -> None:
    profile = json.loads(
        (
            ROOT
            / "benchmarks"
            / "profiles"
            / "production-evidence-v1.json"
        ).read_text(encoding="utf-8")
    )

    assert profile["authorization"]["gpu_cloud_spend_approved"] is False
    assert profile["authorization"]["approval_ceiling_usd"] == 5.0
    assert profile["hardware"]["region"] == "us-east-1"
    assert profile["hardware"]["instance_type"] == "g6.2xlarge"
    assert profile["hardware"]["purchase_model"] == "on-demand"
    assert profile["hardware"]["gpu"] == "NVIDIA L4"
    assert profile["runtime"]["vllm_version"] == "0.30.0"
    assert profile["runtime"]["container"] == "vllm/vllm-openai:v0.30.0"
    assert profile["model"]["name"] == "Qwen/Qwen3-4B-Instruct-2507"
    assert (
        profile["model"]["revision"]
        == "cdbee75f17c01a7cc42f958dc650907174af0554"
    )
    assert profile["cost_gate"]["max_session_hours"] == 3
    assert profile["cost_gate"]["approval_ceiling_usd"] == 5.0


def test_first_gpu_spend_plan_has_termination_and_source_evidence() -> None:
    plan = (
        ROOT
        / "docs"
        / "evidence"
        / "deployment"
        / "first-gpu-spend-plan.md"
    ).read_text(encoding="utf-8")

    assert "GPU/cloud spend is **not approved**" in plan
    assert "Terminate the EC2 instance" in plan
    assert "three-hour maximum session budget" in plan
    assert "security group inbound rules: none" in plan
    assert "Recheck price and capacity immediately before launch" in plan
    assert "https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html" in plan
    assert "https://github.com/vllm-project/vllm/releases" in plan
