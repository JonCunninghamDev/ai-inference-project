"""
Request TTL for the secure inference platform.

Auto-expires requests that have been queued beyond a configurable max age.
Prevents unbounded staleness and gives clients a deterministic failure
instead of infinite waiting.

Usage:
    from ai_inference.core.ttl import RequestTTL

    ttl = RequestTTL(max_age_seconds=300)
    if ttl.is_expired(accepted_at_iso):
        # reject or mark failed
"""
from __future__ import annotations

from datetime import datetime, timezone


class RequestTTL:
    """Checks if a request has exceeded its maximum allowed age."""

    def __init__(self, max_age_seconds: float = 300.0) -> None:
        self.max_age_seconds = max_age_seconds

    def is_expired(self, accepted_at: str) -> bool:
        """Check if the request accepted_at timestamp is beyond max age."""
        if not accepted_at:
            return False
        try:
            accepted = datetime.fromisoformat(accepted_at)
            age = (datetime.now(timezone.utc) - accepted).total_seconds()
            return age > self.max_age_seconds
        except (ValueError, TypeError):
            return False

    def remaining_seconds(self, accepted_at: str) -> float:
        """Seconds remaining before expiry. Negative means already expired."""
        if not accepted_at:
            return self.max_age_seconds
        try:
            accepted = datetime.fromisoformat(accepted_at)
            age = (datetime.now(timezone.utc) - accepted).total_seconds()
            return self.max_age_seconds - age
        except (ValueError, TypeError):
            return self.max_age_seconds
