"""Tests for circuit breaker."""
import time
from unittest.mock import patch

from ai_inference.core.metrics import InMemoryMetricsSink, MetricsCollector
from ai_inference.inference.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerPolicy,
    CircuitState,
)


def _breaker(**kwargs) -> CircuitBreaker:
    return CircuitBreaker(CircuitBreakerPolicy(**kwargs))


# --- Closed state ---


def test_closed_allows_requests():
    cb = _breaker()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_closed_after_failures_below_threshold():
    cb = _breaker(failure_threshold=5)
    for _ in range(4):
        cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


# --- Transition to open ---


def test_opens_after_failure_threshold():
    cb = _breaker(failure_threshold=3)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_open_rejects_requests():
    cb = _breaker(failure_threshold=1, recovery_timeout_seconds=999)
    cb.record_failure()
    assert cb.allow_request() is False


# --- Transition to half-open ---


def test_transitions_to_half_open_after_timeout():
    cb = _breaker(failure_threshold=1, recovery_timeout_seconds=0.01)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    time.sleep(0.02)
    assert cb.state == CircuitState.HALF_OPEN


def test_half_open_allows_one_probe():
    cb = _breaker(failure_threshold=1, recovery_timeout_seconds=0.01, half_open_max_probes=1)
    cb.record_failure()
    time.sleep(0.02)

    assert cb.allow_request() is True  # probe
    assert cb.allow_request() is False  # no more probes


# --- Recovery (half-open → closed) ---


def test_success_in_half_open_closes_circuit():
    cb = _breaker(failure_threshold=1, recovery_timeout_seconds=0.01)
    cb.record_failure()
    time.sleep(0.02)

    cb.allow_request()  # probe
    cb.record_success()

    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


# --- Failure in half-open → back to open ---


def test_failure_in_half_open_reopens():
    cb = _breaker(failure_threshold=1, recovery_timeout_seconds=0.01)
    cb.record_failure()
    time.sleep(0.02)

    cb.allow_request()  # probe
    cb.record_failure()

    assert cb.state == CircuitState.OPEN


# --- Reset ---


def test_manual_reset():
    cb = _breaker(failure_threshold=1, recovery_timeout_seconds=999)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


# --- Success resets failure count ---


def test_success_resets_failure_count():
    cb = _breaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    # Count reset, so 2 more failures shouldn't trip
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED


# --- Metrics ---


def test_transition_emits_metric():
    sink = InMemoryMetricsSink()
    metrics = MetricsCollector(sink)
    cb = CircuitBreaker(CircuitBreakerPolicy(failure_threshold=1), metrics=metrics)

    cb.record_failure()

    assert len(sink.events) == 1
    assert sink.events[0].event_type == "circuit_breaker_transition"
    assert sink.events[0].fields["from_state"] == "closed"
    assert sink.events[0].fields["to_state"] == "open"
