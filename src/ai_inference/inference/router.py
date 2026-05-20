"""
Model routing primitives for the air gapped inference platform.

This module keeps routing deterministic and explainable. That is intentional:
in secure or mission sensitive systems, operators need to understand why a
request was routed to a specific model instead of treating routing as a black
box policy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Iterable, Mapping, Optional

if TYPE_CHECKING:
    from ai_inference.inference.latency import LatencyTracker


class RoutingReason(str, Enum):
    """Human readable reason codes for a routing decision."""

    EXPLICIT_MODEL_REQUESTED = "explicit_model_requested"
    CONTEXT_TOO_LARGE_FOR_SMALL_MODEL = "context_too_large_for_small_model"
    COMPLEX_TASK_TYPE = "complex_task_type"
    HIGH_PRIORITY_REQUEST = "high_priority_request"
    DEFAULT_SMALL_MODEL = "default_small_model"
    FALLBACK_DEFAULT_MODEL = "fallback_default_model"
    LATENCY_AVOIDANCE = "latency_avoidance"


@dataclass(frozen=True)
class ModelProfile:
    """Operational profile for a model served by the platform."""

    name: str
    max_context_tokens: int
    priority: int = 100
    supports_batching: bool = True
    enabled: bool = True
    description: str = ""


@dataclass(frozen=True)
class InferenceRequest:
    """Normalized request metadata used by the router."""

    prompt: str
    context: str = ""
    event_type: str = "general_inference"
    priority: int = 5
    requested_model: Optional[str] = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    @property
    def estimated_tokens(self) -> int:
        """
        Cheap token estimate used for routing.

        This is not meant to replace tokenizer exact counts. It is good enough
        for an early platform routing layer and keeps the router dependency
        light for offline deployments.
        """
        text = f"{self.prompt}\n{self.context}"
        return max(1, len(text) // 4)


@dataclass(frozen=True)
class RoutingDecision:
    """Result of model routing."""

    model_name: str
    reason: RoutingReason
    estimated_tokens: int
    batchable: bool
    notes: str = ""


class ModelRouter:
    """Deterministic router for choosing an inference model."""

    COMPLEX_EVENT_TYPES = {
        "long_context_rag",
        "multi_document_rag",
        "code_generation",
        "analysis",
        "mission_summary",
        "legal_review",
        "medical_review",
    }

    def __init__(self, profiles: Iterable[ModelProfile], default_model: str, latency_tracker: Optional["LatencyTracker"] = None):
        self._profiles = {profile.name: profile for profile in profiles if profile.enabled}
        self.default_model = default_model
        self._latency_tracker = latency_tracker

        if not self._profiles:
            raise ValueError("At least one enabled model profile is required")

        if self.default_model not in self._profiles:
            raise ValueError(f"Default model '{self.default_model}' is not enabled or configured")

    @property
    def profiles(self) -> Mapping[str, ModelProfile]:
        return self._profiles

    def route(self, request: InferenceRequest) -> RoutingDecision:
        """Route a request to the most appropriate model profile."""
        estimated_tokens = request.estimated_tokens

        if request.requested_model:
            profile = self._profiles.get(request.requested_model)
            if profile:
                return RoutingDecision(
                    model_name=profile.name,
                    reason=RoutingReason.EXPLICIT_MODEL_REQUESTED,
                    estimated_tokens=estimated_tokens,
                    batchable=profile.supports_batching,
                    notes="Caller requested a configured model explicitly.",
                )

        sorted_profiles = sorted(
            self._profiles.values(),
            key=lambda profile: (profile.max_context_tokens, profile.priority),
        )
        smallest_model = sorted_profiles[0]
        largest_model = sorted_profiles[-1]

        if estimated_tokens > smallest_model.max_context_tokens:
            selected = self._smallest_model_that_fits(estimated_tokens) or largest_model
            return RoutingDecision(
                model_name=selected.name,
                reason=RoutingReason.CONTEXT_TOO_LARGE_FOR_SMALL_MODEL,
                estimated_tokens=estimated_tokens,
                batchable=selected.supports_batching,
                notes="Request exceeded the smallest model context budget.",
            )

        if request.event_type in self.COMPLEX_EVENT_TYPES:
            return RoutingDecision(
                model_name=largest_model.name,
                reason=RoutingReason.COMPLEX_TASK_TYPE,
                estimated_tokens=estimated_tokens,
                batchable=largest_model.supports_batching,
                notes=f"Event type '{request.event_type}' is configured as complex.",
            )

        if request.priority <= 2:
            return RoutingDecision(
                model_name=largest_model.name,
                reason=RoutingReason.HIGH_PRIORITY_REQUEST,
                estimated_tokens=estimated_tokens,
                batchable=largest_model.supports_batching,
                notes="High priority request routed to highest capacity model.",
            )

        # Latency avoidance: if the default model is degraded, try an alternative
        latency_override = self._check_latency_avoidance(smallest_model, estimated_tokens)
        if latency_override:
            return latency_override

        return RoutingDecision(
            model_name=smallest_model.name,
            reason=RoutingReason.DEFAULT_SMALL_MODEL,
            estimated_tokens=estimated_tokens,
            batchable=smallest_model.supports_batching,
            notes="Defaulted to the smallest enabled model that can serve the request.",
        )

    def _check_latency_avoidance(self, preferred: ModelProfile, estimated_tokens: int) -> Optional[RoutingDecision]:
        """If the preferred model is degraded, try to find a non-degraded alternative."""
        if self._latency_tracker is None:
            return None
        if not self._latency_tracker.is_degraded(preferred.name):
            return None
        # Find an alternative that fits and is not degraded
        candidates = sorted(
            self._profiles.values(),
            key=lambda p: (p.max_context_tokens, p.priority),
        )
        for alt in candidates:
            if alt.name == preferred.name:
                continue
            if estimated_tokens <= alt.max_context_tokens and not self._latency_tracker.is_degraded(alt.name):
                return RoutingDecision(
                    model_name=alt.name,
                    reason=RoutingReason.LATENCY_AVOIDANCE,
                    estimated_tokens=estimated_tokens,
                    batchable=alt.supports_batching,
                    notes=f"Avoided '{preferred.name}' due to elevated P95 latency.",
                )
        return None

    def _smallest_model_that_fits(self, estimated_tokens: int) -> Optional[ModelProfile]:
        candidates = sorted(
            self._profiles.values(),
            key=lambda profile: (profile.max_context_tokens, profile.priority),
        )
        for profile in candidates:
            if estimated_tokens <= profile.max_context_tokens:
                return profile
        return None
