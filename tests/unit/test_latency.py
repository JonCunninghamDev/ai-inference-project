"""Unit tests for latency tracking and latency-aware routing."""
import pytest

from ai_inference.inference.latency import LatencyPolicy, LatencyTracker, ModelLatencyStats
from ai_inference.inference.router import (
    InferenceRequest,
    ModelProfile,
    ModelRouter,
    RoutingReason,
)


class TestLatencyTracker:
    def test_not_degraded_with_no_data(self):
        tracker = LatencyTracker()
        assert tracker.is_degraded("model-a") is False

    def test_not_degraded_below_min_samples(self):
        tracker = LatencyTracker(LatencyPolicy(min_samples=10))
        for _ in range(9):
            tracker.record("model-a", 9999.0)  # High but not enough samples
        assert tracker.is_degraded("model-a") is False

    def test_degraded_when_p95_exceeds_threshold(self):
        tracker = LatencyTracker(LatencyPolicy(window_size=20, p95_threshold_ms=500.0, min_samples=10))
        for _ in range(20):
            tracker.record("model-a", 600.0)
        assert tracker.is_degraded("model-a") is True

    def test_not_degraded_when_p95_below_threshold(self):
        tracker = LatencyTracker(LatencyPolicy(window_size=20, p95_threshold_ms=500.0, min_samples=10))
        for _ in range(20):
            tracker.record("model-a", 100.0)
        assert tracker.is_degraded("model-a") is False

    def test_sliding_window_evicts_old_data(self):
        tracker = LatencyTracker(LatencyPolicy(window_size=10, p95_threshold_ms=500.0, min_samples=10))
        # Fill with slow data
        for _ in range(10):
            tracker.record("model-a", 600.0)
        assert tracker.is_degraded("model-a") is True
        # Overwrite with fast data
        for _ in range(10):
            tracker.record("model-a", 100.0)
        assert tracker.is_degraded("model-a") is False

    def test_get_stats(self):
        tracker = LatencyTracker(LatencyPolicy(window_size=20, p95_threshold_ms=500.0, min_samples=5))
        for i in range(20):
            tracker.record("model-a", float(i * 10))
        stats = tracker.get_stats("model-a")
        assert stats is not None
        assert stats.model == "model-a"
        assert stats.sample_count == 20
        assert stats.p50_ms > 0
        assert stats.p95_ms > stats.p50_ms

    def test_get_stats_unknown_model(self):
        tracker = LatencyTracker()
        assert tracker.get_stats("unknown") is None

    def test_independent_models(self):
        tracker = LatencyTracker(LatencyPolicy(window_size=10, p95_threshold_ms=500.0, min_samples=10))
        for _ in range(10):
            tracker.record("model-a", 600.0)
            tracker.record("model-b", 100.0)
        assert tracker.is_degraded("model-a") is True
        assert tracker.is_degraded("model-b") is False


class TestLatencyAwareRouting:
    def _make_router(self, tracker=None):
        return ModelRouter(
            profiles=[
                ModelProfile(name="small", max_context_tokens=4096, priority=10, description="fast"),
                ModelProfile(name="large", max_context_tokens=32768, priority=20, description="capable"),
            ],
            default_model="small",
            latency_tracker=tracker,
        )

    def test_no_tracker_routes_normally(self):
        router = self._make_router(tracker=None)
        decision = router.route(InferenceRequest(prompt="hello", context="world"))
        assert decision.model_name == "small"
        assert decision.reason == RoutingReason.DEFAULT_SMALL_MODEL

    def test_healthy_model_routes_normally(self):
        tracker = LatencyTracker(LatencyPolicy(window_size=10, p95_threshold_ms=500.0, min_samples=10))
        for _ in range(10):
            tracker.record("small", 100.0)
        router = self._make_router(tracker=tracker)
        decision = router.route(InferenceRequest(prompt="hello", context="world"))
        assert decision.model_name == "small"
        assert decision.reason == RoutingReason.DEFAULT_SMALL_MODEL

    def test_degraded_model_triggers_latency_avoidance(self):
        tracker = LatencyTracker(LatencyPolicy(window_size=10, p95_threshold_ms=500.0, min_samples=10))
        for _ in range(10):
            tracker.record("small", 800.0)  # Degraded
            tracker.record("large", 200.0)  # Healthy
        router = self._make_router(tracker=tracker)
        decision = router.route(InferenceRequest(prompt="hello", context="world"))
        assert decision.model_name == "large"
        assert decision.reason == RoutingReason.LATENCY_AVOIDANCE
        assert "small" in decision.notes

    def test_all_models_degraded_falls_through(self):
        tracker = LatencyTracker(LatencyPolicy(window_size=10, p95_threshold_ms=500.0, min_samples=10))
        for _ in range(10):
            tracker.record("small", 800.0)
            tracker.record("large", 800.0)
        router = self._make_router(tracker=tracker)
        decision = router.route(InferenceRequest(prompt="hello", context="world"))
        # No alternative available, falls through to default
        assert decision.model_name == "small"
        assert decision.reason == RoutingReason.DEFAULT_SMALL_MODEL

    def test_explicit_model_not_overridden_by_latency(self):
        tracker = LatencyTracker(LatencyPolicy(window_size=10, p95_threshold_ms=500.0, min_samples=10))
        for _ in range(10):
            tracker.record("small", 800.0)
        router = self._make_router(tracker=tracker)
        decision = router.route(InferenceRequest(prompt="hello", context="world", requested_model="small"))
        # Explicit request is honored regardless of latency
        assert decision.model_name == "small"
        assert decision.reason == RoutingReason.EXPLICIT_MODEL_REQUESTED

    def test_high_priority_not_overridden_by_latency(self):
        tracker = LatencyTracker(LatencyPolicy(window_size=10, p95_threshold_ms=500.0, min_samples=10))
        for _ in range(10):
            tracker.record("large", 800.0)
        router = self._make_router(tracker=tracker)
        decision = router.route(InferenceRequest(prompt="hello", context="world", priority=1))
        # High priority always goes to largest model
        assert decision.model_name == "large"
        assert decision.reason == RoutingReason.HIGH_PRIORITY_REQUEST
