"""
Tenant-aware policies for the secure inference platform.

Enforces per-tenant rate limits and concurrency caps so one noisy tenant
cannot starve others. Tenant identity is extracted from request metadata.

Usage:
    from ai_inference.gateway.tenant import TenantPolicy, TenantPolicyEngine

    engine = TenantPolicyEngine(default_policy=TenantPolicy(max_requests_per_minute=60))
    engine.set_policy("tenant-a", TenantPolicy(max_requests_per_minute=120, priority_boost=2))

    result = engine.check("tenant-a")
    if result.allowed:
        # proceed
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Optional

from ai_inference.core.logging import get_logger
from ai_inference.core.metrics import MetricsCollector

logger = get_logger("tenant")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class TenantPolicy:
    """Per-tenant limits."""

    max_requests_per_minute: int = 60
    max_concurrent: int = 10
    priority_boost: int = 0  # added to request priority (higher = more important)


# ---------------------------------------------------------------------------
# Decision types
# ---------------------------------------------------------------------------


@dataclass
class TenantCheckResult:
    allowed: bool
    tenant_id: str
    reason: str
    retry_after_seconds: Optional[int] = None
    effective_priority: Optional[int] = None


# ---------------------------------------------------------------------------
# Rate tracking
# ---------------------------------------------------------------------------


@dataclass
class _TenantState:
    """Sliding window rate counter and concurrency tracker."""

    timestamps: list = field(default_factory=list)
    active_count: int = 0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class TenantPolicyEngine:
    """Evaluates per-tenant rate and concurrency limits."""

    DEFAULT_TENANT = "__default__"

    def __init__(
        self,
        default_policy: Optional[TenantPolicy] = None,
        metrics: Optional[MetricsCollector] = None,
    ) -> None:
        self._default_policy = default_policy or TenantPolicy()
        self._policies: Dict[str, TenantPolicy] = {}
        self._state: Dict[str, _TenantState] = defaultdict(_TenantState)
        self._metrics = metrics or MetricsCollector()

    def set_policy(self, tenant_id: str, policy: TenantPolicy) -> None:
        self._policies[tenant_id] = policy

    def get_policy(self, tenant_id: str) -> TenantPolicy:
        return self._policies.get(tenant_id, self._default_policy)

    def check(self, tenant_id: str, request_priority: int = 5) -> TenantCheckResult:
        """Check if a tenant can submit a new request."""
        policy = self.get_policy(tenant_id)
        state = self._state[tenant_id]
        now = time.time()

        # Prune timestamps older than 60s
        cutoff = now - 60.0
        state.timestamps = [t for t in state.timestamps if t > cutoff]

        # Rate limit check
        if len(state.timestamps) >= policy.max_requests_per_minute:
            oldest = state.timestamps[0]
            retry_after = int(60.0 - (now - oldest)) + 1
            logger.warning(
                "tenant rate limited",
                tenant_id=tenant_id,
                requests_in_window=len(state.timestamps),
                limit=policy.max_requests_per_minute,
            )
            self._metrics.record_request_rejected(reason=f"tenant_rate_limit:{tenant_id}")
            return TenantCheckResult(
                allowed=False,
                tenant_id=tenant_id,
                reason=f"Rate limit exceeded: {len(state.timestamps)}/{policy.max_requests_per_minute} requests/min",
                retry_after_seconds=max(1, retry_after),
            )

        # Concurrency check
        if state.active_count >= policy.max_concurrent:
            logger.warning(
                "tenant concurrency limited",
                tenant_id=tenant_id,
                active=state.active_count,
                limit=policy.max_concurrent,
            )
            self._metrics.record_request_rejected(reason=f"tenant_concurrency:{tenant_id}")
            return TenantCheckResult(
                allowed=False,
                tenant_id=tenant_id,
                reason=f"Concurrency limit exceeded: {state.active_count}/{policy.max_concurrent} active",
                retry_after_seconds=5,
            )

        # Admit — record timestamp and bump concurrency
        state.timestamps.append(now)
        state.active_count += 1

        effective_priority = min(10, request_priority + policy.priority_boost)

        return TenantCheckResult(
            allowed=True,
            tenant_id=tenant_id,
            reason="Within tenant limits",
            effective_priority=effective_priority,
        )

    def release(self, tenant_id: str) -> None:
        """Called when a request completes to decrement concurrency."""
        state = self._state[tenant_id]
        state.active_count = max(0, state.active_count - 1)

    @staticmethod
    def extract_tenant(metadata: Dict[str, str]) -> str:
        """Extract tenant ID from request metadata. Falls back to default."""
        return metadata.get("tenant", TenantPolicyEngine.DEFAULT_TENANT)
