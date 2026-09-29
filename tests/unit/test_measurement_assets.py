from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_prometheus_baseline_has_three_measurement_targets() -> None:
    config = (ROOT / "config" / "observability" / "prometheus.yml").read_text(
        encoding="utf-8"
    )

    assert "127.0.0.1:8080" in config
    assert "127.0.0.1:8000" in config
    assert "127.0.0.1:9400" in config
    assert config.count("metrics_path: /metrics") == 3


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


def test_vllm_example_requires_model_selection_before_real_run() -> None:
    config = (
        ROOT
        / "config"
        / "vllm"
        / "production-evidence-v1.env.example"
    ).read_text(encoding="utf-8")

    assert "VLLM_URL=http://127.0.0.1:8000" in config
    assert "VLLM_MODEL=SET_MODEL_BEFORE_RUN" in config
