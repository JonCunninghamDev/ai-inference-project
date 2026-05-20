"""
Structured JSON logging for the secure inference platform.

Usage:
    from ai_inference.core.logging import get_logger

    logger = get_logger("gateway")
    logger.info("request accepted", request_id="abc-123", model="demo-small")

All log entries are JSON with consistent fields for CloudWatch Insights queries.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class StructuredFormatter(logging.Formatter):
    """Formats log records as single-line JSON for CloudWatch ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "message": record.getMessage(),
        }

        # Merge any extra fields passed via logger.info("msg", extra={...})
        # or via the StructuredLogger helper
        extras = getattr(record, "_structured_extras", {})
        entry.update(extras)

        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, default=str)


class StructuredLogger:
    """Wraps stdlib logger to allow keyword arguments as structured fields."""

    def __init__(self, logger: logging.Logger, component: str) -> None:
        self._logger = logger
        self._component = component

    def _log(self, level: int, msg: str, **kwargs: Any) -> None:
        extra = {"_structured_extras": kwargs, "component": self._component}
        self._logger.log(level, msg, extra=extra)

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, **kwargs)

    def critical(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, msg, **kwargs)


def get_logger(component: str, level: int = logging.INFO) -> StructuredLogger:
    """Get a structured logger for a platform component.

    Args:
        component: Component name (gateway, worker, reconciliation, scheduler).
        level: Minimum log level.

    Returns:
        StructuredLogger that emits JSON to stdout.
    """
    name = f"ai_inference.{component}"
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False

    return StructuredLogger(logger, component)
