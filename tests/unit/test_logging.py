"""Tests for structured JSON logging."""
import json
import logging

from ai_inference.core.logging import get_logger, StructuredFormatter


def test_logger_emits_json(capsys):
    logger = get_logger("test_component")
    logger.info("hello world", request_id="r1", model="demo")

    output = capsys.readouterr().out.strip()
    entry = json.loads(output)

    assert entry["level"] == "INFO"
    assert entry["component"] == "test_component"
    assert entry["message"] == "hello world"
    assert entry["request_id"] == "r1"
    assert entry["model"] == "demo"
    assert "timestamp" in entry


def test_logger_includes_error_level(capsys):
    logger = get_logger("worker")
    logger.error("something broke", request_id="r2")

    output = capsys.readouterr().out.strip()
    entry = json.loads(output)

    assert entry["level"] == "ERROR"
    assert entry["component"] == "worker"


def test_logger_no_extra_fields(capsys):
    logger = get_logger("gateway_no_extras")
    logger.info("simple message")

    output = capsys.readouterr().out.strip()
    entry = json.loads(output)

    assert entry["message"] == "simple message"
    assert "request_id" not in entry


def test_logger_handles_numeric_fields(capsys):
    logger = get_logger("scheduler")
    logger.info("batch scheduled", batch_size=4, duration_ms=152)

    output = capsys.readouterr().out.strip()
    entry = json.loads(output)

    assert entry["batch_size"] == 4
    assert entry["duration_ms"] == 152


def test_separate_components_independent(capsys):
    gw = get_logger("gateway_iso_test")
    wk = get_logger("worker_iso_test")

    gw.info("from gateway")
    wk.info("from worker")

    lines = capsys.readouterr().out.strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["component"] == "gateway_iso_test"
    assert json.loads(lines[1])["component"] == "worker_iso_test"
