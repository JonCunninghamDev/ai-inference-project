"""Unit tests for the audit trail module."""
import json
import tempfile
from pathlib import Path

import pytest

from ai_inference.core.audit import (
    AuditEvent,
    InMemoryAuditLog,
    JsonlAuditLog,
    NullAuditLog,
)


class TestAuditEvent:
    def test_to_dict(self):
        event = AuditEvent(request_id="r1", event="accepted", component="gateway", detail={"model": "small"})
        d = event.to_dict()
        assert d["request_id"] == "r1"
        assert d["event"] == "accepted"
        assert d["component"] == "gateway"
        assert d["detail"] == {"model": "small"}
        assert "timestamp" in d

    def test_default_timestamp(self):
        event = AuditEvent(request_id="r1", event="accepted", component="gateway")
        assert event.timestamp is not None


class TestInMemoryAuditLog:
    def test_record_and_retrieve(self):
        log = InMemoryAuditLog()
        log.record(AuditEvent(request_id="r1", event="accepted", component="gateway"))
        log.record(AuditEvent(request_id="r1", event="routed", component="gateway", detail={"model": "small"}))
        log.record(AuditEvent(request_id="r2", event="accepted", component="gateway"))

        trail = log.get_trail("r1")
        assert len(trail) == 2
        assert trail[0].event == "accepted"
        assert trail[1].event == "routed"

    def test_empty_trail(self):
        log = InMemoryAuditLog()
        assert log.get_trail("nonexistent") == []

    def test_all_events(self):
        log = InMemoryAuditLog()
        log.record(AuditEvent(request_id="r1", event="accepted", component="gateway"))
        log.record(AuditEvent(request_id="r2", event="accepted", component="gateway"))
        assert len(log.all_events) == 2

    def test_append_only(self):
        log = InMemoryAuditLog()
        log.record(AuditEvent(request_id="r1", event="accepted", component="gateway"))
        log.record(AuditEvent(request_id="r1", event="completed", component="worker"))
        # Both events preserved, nothing overwritten
        trail = log.get_trail("r1")
        assert len(trail) == 2


class TestJsonlAuditLog:
    def test_record_and_retrieve(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        log = JsonlAuditLog(path)
        log.record(AuditEvent(request_id="r1", event="accepted", component="gateway"))
        log.record(AuditEvent(request_id="r1", event="completed", component="worker"))
        log.record(AuditEvent(request_id="r2", event="accepted", component="gateway"))

        trail = log.get_trail("r1")
        assert len(trail) == 2
        assert trail[0].event == "accepted"
        assert trail[1].event == "completed"

    def test_file_is_valid_jsonl(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        log = JsonlAuditLog(path)
        log.record(AuditEvent(request_id="r1", event="accepted", component="gateway", detail={"k": "v"}))

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["request_id"] == "r1"
        assert data["detail"] == {"k": "v"}

    def test_empty_file(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        log = JsonlAuditLog(path)
        assert log.get_trail("r1") == []

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "nested" / "dir" / "audit.jsonl"
        log = JsonlAuditLog(path)
        log.record(AuditEvent(request_id="r1", event="accepted", component="gateway"))
        assert path.exists()


class TestNullAuditLog:
    def test_record_does_nothing(self):
        log = NullAuditLog()
        log.record(AuditEvent(request_id="r1", event="accepted", component="gateway"))
        assert log.get_trail("r1") == []
