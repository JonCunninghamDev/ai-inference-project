"""Inference platform modules."""

from .router import InferenceRequest, ModelProfile, ModelRouter, RoutingDecision

__all__ = [
    "InferenceRequest",
    "ModelProfile",
    "ModelRouter",
    "RoutingDecision",
]

from ai_inference.inference.gpu_scheduler import (
    GPUDeviceSnapshot,
    GPUScheduler,
    ModelResourceProfile,
    SchedulingDecision,
    SchedulingPolicy,
    SchedulingStatus,
    StaticGPUInventory,
)
