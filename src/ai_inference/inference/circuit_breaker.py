"""
Circuit breaker for downstream inference calls.

Prevents the worker from hammering a failing vLLM server. Three states:

    CLOSED    → healthy, requests flow normally
    OPEN      → failing, reject immediately (fast-fail)
    HALF_OPEN → testing recovery, allow one probe request

Usage:
    from ai_inference.inference.circuit_breaker import CircuitBreaker, CircuitBreakerPolicy

    cb = CircuitBreaker(CircuitBreakerPolicy(failure_threshold=5, recovery_timeout_seconds=30))

    if cb.allow_request():
        try:
            result = call_vllm(...)
            cb.record_success()
        except Exception:
            cb.record_failure()
    else:
        # fast-fail, don't call downstream
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ai_inference.core.logging import get_logger
from ai_inference.core.metrics import MetricsCollector

logger = get_logger("circuit_breaker")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class CircuitBreakerPolicy:
    """Controls circuit breaker behavior."""

    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    half_open_max_probes: int = 1


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """State machine that protects against downstream failures."""

    def __init__(self, policy: Optional[CircuitBreakerPolicy] = None, metrics: Optional[MetricsCollector] = None) -> None:
        self.policy = policy or CircuitBreakerPolicy()
        self._metrics = metrics or MetricsCollector()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_probes = 0

    @property
    def state(self) -> CircuitState:
        # Check if open circuit should transition to half-open
        if self._state == CircuitState.OPEN:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.policy.recovery_timeout_seconds:
                self._transition(CircuitState.HALF_OPEN)
        return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        current = self.state

        if current == CircuitState.CLOSED:
            return True

        if current == CircuitState.HALF_OPEN:
            if self._half_open_probes < self.policy.half_open_max_probes:
                self._half_open_probes += 1
                return True
            return False

        # OPEN
        return False

    def record_success(self) -> None:
        """Record a successful downstream call."""
        if self._state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.CLOSED)
        self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed downstream call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.OPEN)
        elif self._state == CircuitState.CLOSED and self._failure_count >= self.policy.failure_threshold:
            self._transition(CircuitState.OPEN)

    def reset(self) -> None:
        """Manually reset the circuit to closed."""
        self._transition(CircuitState.CLOSED)

    def _transition(self, new_state: CircuitState) -> None:
        old_state = self._state
        self._state = new_state

        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._half_open_probes = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_probes = 0

        logger.info(
            "state transition",
            from_state=old_state.value,
            to_state=new_state.value,
            failure_count=self._failure_count,
        )
        self._metrics._emit("circuit_breaker_transition", "circuit_breaker",
                            from_state=old_state.value,
                            to_state=new_state.value,
                            failure_count=self._failure_count)
