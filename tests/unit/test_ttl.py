"""Unit tests for request TTL."""
from datetime import datetime, timedelta, timezone

import pytest

from ai_inference.core.ttl import RequestTTL


class TestRequestTTL:
    def test_not_expired_recent(self):
        ttl = RequestTTL(max_age_seconds=300)
        now = datetime.now(timezone.utc).isoformat()
        assert ttl.is_expired(now) is False

    def test_expired_old(self):
        ttl = RequestTTL(max_age_seconds=60)
        old = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        assert ttl.is_expired(old) is True

    def test_empty_string_not_expired(self):
        ttl = RequestTTL(max_age_seconds=60)
        assert ttl.is_expired("") is False

    def test_invalid_timestamp_not_expired(self):
        ttl = RequestTTL(max_age_seconds=60)
        assert ttl.is_expired("not-a-date") is False

    def test_remaining_seconds_positive(self):
        ttl = RequestTTL(max_age_seconds=300)
        now = datetime.now(timezone.utc).isoformat()
        remaining = ttl.remaining_seconds(now)
        assert 299 <= remaining <= 300

    def test_remaining_seconds_negative_when_expired(self):
        ttl = RequestTTL(max_age_seconds=60)
        old = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        remaining = ttl.remaining_seconds(old)
        assert remaining < 0

    def test_boundary_not_expired_just_under(self):
        ttl = RequestTTL(max_age_seconds=60)
        # 59 seconds ago — should not be expired
        recent = (datetime.now(timezone.utc) - timedelta(seconds=59)).isoformat()
        assert ttl.is_expired(recent) is False
