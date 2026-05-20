"""Unit tests for the priority queue module."""
import pytest

from ai_inference.core.priority_queue import (
    PriorityInferenceQueue,
    PriorityLane,
    priority_to_lane,
)


class TestPriorityToLane:
    def test_high_priority(self):
        assert priority_to_lane(1) == PriorityLane.HIGH
        assert priority_to_lane(2) == PriorityLane.HIGH

    def test_normal_priority(self):
        assert priority_to_lane(3) == PriorityLane.NORMAL
        assert priority_to_lane(5) == PriorityLane.NORMAL
        assert priority_to_lane(7) == PriorityLane.NORMAL

    def test_low_priority(self):
        assert priority_to_lane(8) == PriorityLane.LOW
        assert priority_to_lane(10) == PriorityLane.LOW


class TestPriorityInferenceQueue:
    def test_high_before_normal(self):
        q = PriorityInferenceQueue()
        q.put("normal", priority=5)
        q.put("high", priority=1)
        assert q.get(timeout=0.0) == "high"
        assert q.get(timeout=0.0) == "normal"

    def test_normal_before_low(self):
        q = PriorityInferenceQueue()
        q.put("low", priority=9)
        q.put("normal", priority=5)
        assert q.get(timeout=0.0) == "normal"
        assert q.get(timeout=0.0) == "low"

    def test_strict_ordering_all_lanes(self):
        q = PriorityInferenceQueue()
        q.put("low", priority=10)
        q.put("normal", priority=5)
        q.put("high", priority=1)
        assert q.get(timeout=0.0) == "high"
        assert q.get(timeout=0.0) == "normal"
        assert q.get(timeout=0.0) == "low"

    def test_fifo_within_same_lane(self):
        q = PriorityInferenceQueue()
        q.put("first", priority=5)
        q.put("second", priority=5)
        q.put("third", priority=5)
        assert q.get(timeout=0.0) == "first"
        assert q.get(timeout=0.0) == "second"
        assert q.get(timeout=0.0) == "third"

    def test_empty_returns_none(self):
        q = PriorityInferenceQueue()
        assert q.get(timeout=0.01) is None

    def test_qsize(self):
        q = PriorityInferenceQueue()
        q.put("a", priority=1)
        q.put("b", priority=5)
        q.put("c", priority=9)
        assert q.qsize() == 3

    def test_lane_sizes(self):
        q = PriorityInferenceQueue()
        q.put("a", priority=1)
        q.put("b", priority=2)
        q.put("c", priority=5)
        q.put("d", priority=9)
        sizes = q.lane_sizes()
        assert sizes["high"] == 2
        assert sizes["normal"] == 1
        assert sizes["low"] == 1

    def test_get_batch_respects_priority(self):
        q = PriorityInferenceQueue()
        q.put("low", priority=9)
        q.put("normal", priority=5)
        q.put("high", priority=1)
        batch = q.get_batch(max_size=3, timeout=0.0)
        assert batch == ["high", "normal", "low"]

    def test_get_batch_respects_max_size(self):
        q = PriorityInferenceQueue()
        for i in range(10):
            q.put(f"item-{i}", priority=5)
        batch = q.get_batch(max_size=4, timeout=0.0)
        assert len(batch) == 4

    def test_get_batch_empty(self):
        q = PriorityInferenceQueue()
        batch = q.get_batch(max_size=4, timeout=0.01)
        assert batch == []
