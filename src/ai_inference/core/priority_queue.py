"""
Priority queue for the secure inference platform.

Provides priority lanes so high-priority requests are processed before
normal traffic. Three lanes: high, normal, low. Drain order is strict:
all high-priority items are consumed before any normal items, and all
normal items before any low items.

Priority mapping (from request priority field 1-10):
    1-2  → high lane
    3-7  → normal lane
    8-10 → low lane

Usage:
    from ai_inference.core.priority_queue import PriorityInferenceQueue, PriorityLane

    q = PriorityInferenceQueue()
    q.put(payload, priority=1)   # high lane
    q.put(payload, priority=5)   # normal lane
    item = q.get(timeout=1.0)    # returns highest priority item first
"""
from __future__ import annotations

import json
from enum import IntEnum
from queue import Empty, Queue
from typing import Any, Optional


class PriorityLane(IntEnum):
    HIGH = 0
    NORMAL = 1
    LOW = 2


def priority_to_lane(priority: int) -> PriorityLane:
    """Map request priority (1-10) to a lane."""
    if priority <= 2:
        return PriorityLane.HIGH
    if priority <= 7:
        return PriorityLane.NORMAL
    return PriorityLane.LOW


class PriorityInferenceQueue:
    """In-process priority queue with strict lane ordering.

    Suitable for demo and single-process deployments. In production,
    this would be replaced by SQS FIFO with message group IDs or
    separate queues per priority tier.
    """

    def __init__(self) -> None:
        self._lanes = {
            PriorityLane.HIGH: Queue(),
            PriorityLane.NORMAL: Queue(),
            PriorityLane.LOW: Queue(),
        }

    def put(self, payload: str, priority: int = 5) -> None:
        """Enqueue a serialized payload into the appropriate lane."""
        lane = priority_to_lane(priority)
        self._lanes[lane].put(payload)

    def get(self, timeout: float = 0.5) -> Optional[str]:
        """Get the next item, draining high before normal before low.

        Returns None if all lanes are empty after timeout.
        """
        # Try each lane in priority order without blocking
        for lane in PriorityLane:
            try:
                return self._lanes[lane].get_nowait()
            except Empty:
                continue

        # All lanes empty — block on normal lane briefly to avoid busy-wait
        try:
            return self._lanes[PriorityLane.NORMAL].get(timeout=timeout)
        except Empty:
            # Check high/low one more time (may have arrived during wait)
            for lane in (PriorityLane.HIGH, PriorityLane.LOW):
                try:
                    return self._lanes[lane].get_nowait()
                except Empty:
                    continue
            return None

    def get_batch(self, max_size: int, timeout: float = 0.5) -> list[str]:
        """Get up to max_size items, respecting priority order."""
        items: list[str] = []
        first = self.get(timeout=timeout)
        if first is None:
            return items
        items.append(first)
        while len(items) < max_size:
            item = self.get(timeout=0.0)
            if item is None:
                break
            items.append(item)
        return items

    def qsize(self) -> int:
        """Total items across all lanes."""
        return sum(q.qsize() for q in self._lanes.values())

    def lane_sizes(self) -> dict[str, int]:
        """Item count per lane."""
        return {lane.name.lower(): self._lanes[lane].qsize() for lane in PriorityLane}
