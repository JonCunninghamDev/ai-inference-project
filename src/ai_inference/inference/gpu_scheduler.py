"""
GPU-aware scheduling primitives for the secure inference platform.

This module keeps scheduling policy explicit and deterministic. It does not try
launch containers or own cluster orchestration yet. Its job is to answer the
platform question that appears before every inference batch: is there enough GPU
capacity to run this model now, and if multiple devices are available, which one
is the safest placement?
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence


class SchedulingStatus(str, Enum):
    """Result categories for placement decisions."""

    SCHEDULED = "scheduled"
    DEFERRED = "deferred"
    REJECTED = "rejected"


@dataclass(frozen=True)
class GPUDeviceSnapshot:
    """Point-in-time view of one GPU device."""

    device_id: str
    name: str = "unknown"
    total_memory_mb: int = 0
    used_memory_mb: int = 0
    utilization_percent: float = 0.0
    unhealthy: bool = False
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.total_memory_mb < 0:
            raise ValueError("total_memory_mb cannot be negative")
        if self.used_memory_mb < 0:
            raise ValueError("used_memory_mb cannot be negative")
        if self.used_memory_mb > self.total_memory_mb and self.total_memory_mb > 0:
            raise ValueError("used_memory_mb cannot exceed total_memory_mb")
        if not 0 <= self.utilization_percent <= 100:
            raise ValueError("utilization_percent must be between 0 and 100")

    @property
    def free_memory_mb(self) -> int:
        return max(self.total_memory_mb - self.used_memory_mb, 0)


@dataclass(frozen=True)
class ModelResourceProfile:
    """Resource requirement for running a model or batch."""

    model_name: str
    required_memory_mb: int
    expected_utilization_percent: float = 0.0
    max_batch_size: int = 1

    def __post_init__(self) -> None:
        if self.required_memory_mb < 1:
            raise ValueError("required_memory_mb must be at least 1")
        if not 0 <= self.expected_utilization_percent <= 100:
            raise ValueError("expected_utilization_percent must be between 0 and 100")
        if self.max_batch_size < 1:
            raise ValueError("max_batch_size must be at least 1")


@dataclass(frozen=True)
class SchedulingPolicy:
    """Operational limits used by the scheduler."""

    memory_reserve_mb: int = 1024
    max_gpu_utilization_percent: float = 92.0
    allow_cpu_fallback: bool = False

    def __post_init__(self) -> None:
        if self.memory_reserve_mb < 0:
            raise ValueError("memory_reserve_mb cannot be negative")
        if not 1 <= self.max_gpu_utilization_percent <= 100:
            raise ValueError("max_gpu_utilization_percent must be between 1 and 100")


@dataclass(frozen=True)
class SchedulingDecision:
    """Placement decision for an inference batch."""

    status: SchedulingStatus
    model_name: str
    device_id: str | None
    reason: str
    available_memory_mb: int = 0
    required_memory_mb: int = 0

    @property
    def scheduled(self) -> bool:
        return self.status == SchedulingStatus.SCHEDULED


class StaticGPUInventory:
    """Simple inventory provider used for tests and local deployments."""

    def __init__(self, devices: Sequence[GPUDeviceSnapshot]):
        self._devices = list(devices)

    def snapshot(self) -> list[GPUDeviceSnapshot]:
        return list(self._devices)


class GPUScheduler:
    """Select an eligible GPU for a model based on memory and utilization."""

    def __init__(
        self,
        model_profiles: Mapping[str, ModelResourceProfile],
        policy: SchedulingPolicy | None = None,
    ):
        if not model_profiles:
            raise ValueError("At least one model resource profile is required")
        self.model_profiles = dict(model_profiles)
        self.policy = policy or SchedulingPolicy()

    def schedule(
        self,
        model_name: str,
        devices: Sequence[GPUDeviceSnapshot],
        batch_size: int = 1,
    ) -> SchedulingDecision:
        profile = self.model_profiles.get(model_name)
        if profile is None:
            return SchedulingDecision(
                status=SchedulingStatus.REJECTED,
                model_name=model_name,
                device_id=None,
                reason="unknown_model_resource_profile",
            )

        if batch_size > profile.max_batch_size:
            return SchedulingDecision(
                status=SchedulingStatus.DEFERRED,
                model_name=model_name,
                device_id=None,
                reason="batch_size_exceeds_model_profile",
                required_memory_mb=profile.required_memory_mb,
            )

        if not devices:
            return SchedulingDecision(
                status=SchedulingStatus.DEFERRED,
                model_name=model_name,
                device_id="cpu" if self.policy.allow_cpu_fallback else None,
                reason="no_gpu_available" if not self.policy.allow_cpu_fallback else "cpu_fallback_selected",
                required_memory_mb=profile.required_memory_mb,
            )

        eligible: list[tuple[int, float, GPUDeviceSnapshot]] = []
        required_with_reserve = profile.required_memory_mb + self.policy.memory_reserve_mb

        for device in devices:
            if device.unhealthy:
                continue
            projected_utilization = device.utilization_percent + profile.expected_utilization_percent
            if device.free_memory_mb < required_with_reserve:
                continue
            if projected_utilization > self.policy.max_gpu_utilization_percent:
                continue
            eligible.append((device.free_memory_mb, device.utilization_percent, device))

        if not eligible:
            best_free = max((device.free_memory_mb for device in devices if not device.unhealthy), default=0)
            return SchedulingDecision(
                status=SchedulingStatus.DEFERRED,
                model_name=model_name,
                device_id=None,
                reason="insufficient_gpu_capacity",
                available_memory_mb=best_free,
                required_memory_mb=required_with_reserve,
            )

        # Prefer the tightest memory fit, then lower current utilization. This
        # avoids fragmenting large GPUs while still avoiding hot devices.
        _, _, selected = sorted(eligible, key=lambda item: (item[0], item[1], item[2].device_id))[0]
        return SchedulingDecision(
            status=SchedulingStatus.SCHEDULED,
            model_name=model_name,
            device_id=selected.device_id,
            reason="gpu_capacity_available",
            available_memory_mb=selected.free_memory_mb,
            required_memory_mb=required_with_reserve,
        )
