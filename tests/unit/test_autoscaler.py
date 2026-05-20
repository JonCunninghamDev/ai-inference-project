"""Tests for worker pool autoscaling."""
import time
from unittest.mock import patch

from ai_inference.core.autoscaler import (
    Autoscaler,
    AutoscalingPolicy,
    ClusterState,
    ScalingAction,
)
from ai_inference.core.metrics import InMemoryMetricsSink, MetricsCollector


def _scaler(dry_run=True, **kwargs) -> Autoscaler:
    defaults = {"cooldown_seconds": 0}
    defaults.update(kwargs)
    policy = AutoscalingPolicy(dry_run=dry_run, **defaults)
    return Autoscaler(policy)


# --- Hold (within targets) ---


def test_hold_when_within_targets():
    scaler = _scaler()
    decision = scaler.evaluate(ClusterState(current_workers=2, avg_queue_wait_ms=500))
    assert decision.action == ScalingAction.HOLD
    assert decision.desired_workers == 2


# --- Scale up triggers ---


def test_scale_up_on_high_queue_wait():
    scaler = _scaler(target_queue_wait_ms=1000)
    decision = scaler.evaluate(ClusterState(current_workers=2, avg_queue_wait_ms=3000))
    assert decision.action == ScalingAction.SCALE_UP
    assert decision.desired_workers == 3
    assert "Queue wait" in decision.reason


def test_scale_up_on_scheduling_deferrals():
    scaler = _scaler(scale_up_threshold_deferrals=2)
    decision = scaler.evaluate(ClusterState(current_workers=1, scheduling_deferrals=3))
    assert decision.action == ScalingAction.SCALE_UP
    assert "deferrals" in decision.reason


def test_scale_up_on_high_utilization():
    scaler = _scaler(target_utilization_percent=70)
    decision = scaler.evaluate(ClusterState(current_workers=3, utilization_percent=85))
    assert decision.action == ScalingAction.SCALE_UP
    assert "Utilization" in decision.reason


def test_scale_up_capped_at_max():
    scaler = _scaler(max_workers=5)
    decision = scaler.evaluate(ClusterState(current_workers=5, avg_queue_wait_ms=99999))
    assert decision.action == ScalingAction.HOLD
    assert "max workers" in decision.reason


# --- Scale down triggers ---


def test_scale_down_on_idle():
    scaler = _scaler(scale_down_idle_seconds=60)
    decision = scaler.evaluate(ClusterState(current_workers=3, idle_seconds=120))
    assert decision.action == ScalingAction.SCALE_DOWN
    assert decision.desired_workers == 2
    assert "Idle" in decision.reason


def test_scale_down_capped_at_min():
    scaler = _scaler(min_workers=2, scale_down_idle_seconds=60)
    decision = scaler.evaluate(ClusterState(current_workers=2, idle_seconds=999))
    assert decision.action == ScalingAction.HOLD


# --- Cooldown ---


def test_cooldown_prevents_rapid_scaling():
    scaler = _scaler(cooldown_seconds=300, target_queue_wait_ms=1000)
    # First evaluation triggers scale up
    d1 = scaler.evaluate(ClusterState(current_workers=2, avg_queue_wait_ms=5000))
    assert d1.action == ScalingAction.SCALE_UP

    # Second evaluation within cooldown should hold
    d2 = scaler.evaluate(ClusterState(current_workers=3, avg_queue_wait_ms=5000))
    assert d2.action == ScalingAction.HOLD
    assert "cooldown" in d2.reason.lower()


# --- Dry run ---


def test_dry_run_flag_propagated():
    scaler = _scaler(dry_run=True, target_queue_wait_ms=1000)
    decision = scaler.evaluate(ClusterState(current_workers=1, avg_queue_wait_ms=5000))
    assert decision.dry_run is True


def test_non_dry_run():
    scaler = _scaler(dry_run=False, target_queue_wait_ms=1000)
    decision = scaler.evaluate(ClusterState(current_workers=1, avg_queue_wait_ms=5000))
    assert decision.dry_run is False


# --- Metrics emission ---


def test_scaling_decision_emits_metric():
    sink = InMemoryMetricsSink()
    metrics = MetricsCollector(sink)
    policy = AutoscalingPolicy(dry_run=True, cooldown_seconds=0, target_queue_wait_ms=1000)
    scaler = Autoscaler(policy, metrics=metrics)

    scaler.evaluate(ClusterState(current_workers=2, avg_queue_wait_ms=5000))

    assert len(sink.events) == 1
    assert sink.events[0].event_type == "scaling_decision"
    assert sink.events[0].fields["action"] == "scale_up"


# --- Priority of triggers ---


def test_queue_wait_checked_before_deferrals():
    """Queue wait is the first trigger evaluated."""
    scaler = _scaler(target_queue_wait_ms=1000, scale_up_threshold_deferrals=1)
    decision = scaler.evaluate(ClusterState(
        current_workers=1, avg_queue_wait_ms=5000, scheduling_deferrals=5,
    ))
    assert "Queue wait" in decision.reason
