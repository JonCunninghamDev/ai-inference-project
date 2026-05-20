"""
Latency tracker for observed model inference performance.

Maintains a sliding window of inference durations per model. The router
consults this to avoid sending latency-sensitive requests to a model that
is currently slow.

Usage:
    from ai_inference.inference.latency import LatencyTracker, LatencyPolicy

    tracker = LatencyTracker(LatencyPolicy(window_size=100, p95_threshold_ms=2000))
    tracker.record("demo-small", duration_ms=150)
    tracker.is_degraded("demo-small")  # False
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class LatencyPolicy:
    """Controls when a model is considered degraded."""

    window_size: int = 100
    p95_threshold_ms: float = 2000.0
    min_samples: int = 10  # Don't judge until we have enough data


@dataclass
class ModelLatencyStats:
    """Current latency statistics for a model."""

    model: str
    sample_count: int
    p50_ms: float
    p95_ms: float
    degraded: bool


class LatencyTracker:
    """Sliding window latency observer per model."""

    def __init__(self, policy: Optional[LatencyPolicy] = None) -> None:
        self.policy = policy or LatencyPolicy()
        self._windows: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.policy.window_size))

    def record(self, model: str, duration_ms: float) -> None:
        """Record an observed inference duration."""
        self._windows[model].append(duration_ms)

    def is_degraded(self, model: str) -> bool:
        """Check if a model's P95 exceeds the threshold."""
        window = self._windows.get(model)
        if not window or len(window) < self.policy.min_samples:
            return False
        p95 = self._percentile(window, 95)
        return p95 > self.policy.p95_threshold_ms

    def get_stats(self, model: str) -> Optional[ModelLatencyStats]:
        """Get current latency stats for a model."""
        window = self._windows.get(model)
        if not window:
            return None
        return ModelLatencyStats(
            model=model,
            sample_count=len(window),
            p50_ms=self._percentile(window, 50),
            p95_ms=self._percentile(window, 95),
            degraded=self.is_degraded(model),
        )

    @staticmethod
    def _percentile(data: deque, pct: int) -> float:
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * pct / 100)
        idx = min(idx, len(sorted_data) - 1)
        return sorted_data[idx]
