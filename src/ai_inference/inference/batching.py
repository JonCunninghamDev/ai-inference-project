"""
Dynamic batching primitives for the secure inference platform.

The batcher groups compatible inference tasks before they reach vLLM. It is
intentionally policy-driven rather than framework magic: in secure or resource
constrained environments, operators need predictable boundaries around queue
wait time, maximum batch size, model compatibility, and priority handling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4


@dataclass(frozen=True)
class BatchCandidate:
    """Normalized unit of work that can be considered for batching."""

    request_id: str
    prompt: str
    context: str = ""
    model_name: str = ""
    event_type: str = "general_inference"
    priority: int = 5
    estimated_tokens: int = 0
    batchable: bool = True
    metadata: Mapping[str, str] = field(default_factory=dict)
    raw_payload: Mapping[str, Any] = field(default_factory=dict)

    @property
    def compatibility_key(self) -> tuple[str, str]:
        """
        Return the fields that must match before requests share a batch.

        This early platform version keeps compatibility strict: same selected
        model and same event type. That avoids mixing prompt patterns that may
        later require different system instructions, safety policies, or output
        schemas.
        """
        return (self.model_name, self.event_type)


@dataclass(frozen=True)
class InferenceBatch:
    """A concrete batch that a worker can submit to the inference backend."""

    batch_id: str
    model_name: str
    event_type: str
    candidates: Sequence[BatchCandidate]
    reason: str
    created_at: str

    @property
    def size(self) -> int:
        return len(self.candidates)

    @property
    def total_estimated_tokens(self) -> int:
        return sum(candidate.estimated_tokens for candidate in self.candidates)


@dataclass(frozen=True)
class BatchingPolicy:
    """Operational limits for dynamic batching."""

    max_batch_size: int = 4
    max_batch_tokens: int = 12000
    high_priority_threshold: int = 2
    allow_single_item_batches: bool = True

    def __post_init__(self) -> None:
        if self.max_batch_size < 1:
            raise ValueError("max_batch_size must be at least 1")
        if self.max_batch_tokens < 1:
            raise ValueError("max_batch_tokens must be at least 1")
        if self.high_priority_threshold < 1:
            raise ValueError("high_priority_threshold must be at least 1")


class DynamicBatcher:
    """Build deterministic batches from queued inference work."""

    def __init__(self, policy: BatchingPolicy | None = None):
        self.policy = policy or BatchingPolicy()

    def build_batches(self, candidates: Iterable[BatchCandidate]) -> list[InferenceBatch]:
        """Group candidates into compatible batches."""
        candidates_list = list(candidates)
        if not candidates_list:
            return []

        immediate: list[InferenceBatch] = []
        grouped: dict[tuple[str, str], list[BatchCandidate]] = {}

        for candidate in sorted(candidates_list, key=lambda item: (item.priority, item.request_id)):
            if not candidate.batchable:
                immediate.append(self._make_batch([candidate], "not_batchable"))
                continue
            if candidate.priority <= self.policy.high_priority_threshold:
                immediate.append(self._make_batch([candidate], "high_priority_singleton"))
                continue
            if candidate.estimated_tokens > self.policy.max_batch_tokens:
                immediate.append(self._make_batch([candidate], "token_budget_exceeded_singleton"))
                continue
            grouped.setdefault(candidate.compatibility_key, []).append(candidate)

        batches = list(immediate)
        for group in grouped.values():
            batches.extend(self._split_group(group))

        return batches

    def _split_group(self, group: Sequence[BatchCandidate]) -> list[InferenceBatch]:
        batches: list[InferenceBatch] = []
        current: list[BatchCandidate] = []
        current_tokens = 0

        for candidate in group:
            would_exceed_size = len(current) >= self.policy.max_batch_size
            would_exceed_tokens = current and current_tokens + candidate.estimated_tokens > self.policy.max_batch_tokens
            if would_exceed_size or would_exceed_tokens:
                batches.append(self._make_batch(current, "compatible_dynamic_batch"))
                current = []
                current_tokens = 0

            current.append(candidate)
            current_tokens += candidate.estimated_tokens

        if current and (self.policy.allow_single_item_batches or len(current) > 1):
            reason = "compatible_dynamic_batch" if len(current) > 1 else "single_batchable_request"
            batches.append(self._make_batch(current, reason))

        return batches

    def _make_batch(self, candidates: Sequence[BatchCandidate], reason: str) -> InferenceBatch:
        if not candidates:
            raise ValueError("Cannot create an empty inference batch")
        first = candidates[0]
        return InferenceBatch(
            batch_id=str(uuid4()),
            model_name=first.model_name,
            event_type=first.event_type,
            candidates=list(candidates),
            reason=reason,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
