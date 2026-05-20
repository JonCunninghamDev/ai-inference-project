"""
Append-only audit trail for the secure inference platform.

Records every lifecycle transition for a request. Designed for compliance,
debugging, and post-incident analysis in environments where explainability
is non-negotiable.

Usage:
    from ai_inference.core.audit import AuditLog, InMemoryAuditLog, AuditEvent

    audit = InMemoryAuditLog()
    audit.record(AuditEvent(request_id="abc", event="accepted", component="gateway", detail={"model": "demo-small"}))
    trail = audit.get_trail("abc")
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol


# ---------------------------------------------------------------------------
# Event type
# ---------------------------------------------------------------------------


@dataclass
class AuditEvent:
    """A single lifecycle transition."""

    request_id: str
    event: str
    component: str
    detail: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class AuditLog(Protocol):
    def record(self, event: AuditEvent) -> None: ...
    def get_trail(self, request_id: str) -> List[AuditEvent]: ...


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------


class InMemoryAuditLog:
    """Append-only in-memory audit log for dev/demo."""

    def __init__(self) -> None:
        self._events: List[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self._events.append(event)

    def get_trail(self, request_id: str) -> List[AuditEvent]:
        return [e for e in self._events if e.request_id == request_id]

    @property
    def all_events(self) -> List[AuditEvent]:
        return list(self._events)


# ---------------------------------------------------------------------------
# JSONL file implementation (air-gapped compatible)
# ---------------------------------------------------------------------------


class JsonlAuditLog:
    """Appends audit events to a local JSONL file.

    Suitable for air-gapped environments. The file is append-only —
    no event is ever modified or deleted.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: AuditEvent) -> None:
        with open(self._path, "a") as f:
            f.write(json.dumps(event.to_dict(), default=str) + "\n")

    def get_trail(self, request_id: str) -> List[AuditEvent]:
        if not self._path.exists():
            return []
        events: List[AuditEvent] = []
        with open(self._path) as f:
            for line in f:
                data = json.loads(line)
                if data["request_id"] == request_id:
                    events.append(AuditEvent(**data))
        return events


# ---------------------------------------------------------------------------
# Null implementation (disabled)
# ---------------------------------------------------------------------------


class NullAuditLog:
    """Discards all events. Use when auditing is disabled."""

    def record(self, event: AuditEvent) -> None:
        pass

    def get_trail(self, request_id: str) -> List[AuditEvent]:
        return []
