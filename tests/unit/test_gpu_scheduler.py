import pytest

from ai_inference.inference.gpu_scheduler import (
    GPUDeviceSnapshot,
    GPUScheduler,
    ModelResourceProfile,
    SchedulingPolicy,
    SchedulingStatus,
)


def scheduler():
    return GPUScheduler(
        model_profiles={
            "small-local": ModelResourceProfile(
                model_name="small-local",
                required_memory_mb=8_000,
                expected_utilization_percent=20,
                max_batch_size=8,
            ),
            "large-local": ModelResourceProfile(
                model_name="large-local",
                required_memory_mb=24_000,
                expected_utilization_percent=50,
                max_batch_size=2,
            ),
        },
        policy=SchedulingPolicy(memory_reserve_mb=1_000, max_gpu_utilization_percent=90),
    )


def gpu(device_id, total=48_000, used=0, util=0, unhealthy=False):
    return GPUDeviceSnapshot(
        device_id=device_id,
        name="test-gpu",
        total_memory_mb=total,
        used_memory_mb=used,
        utilization_percent=util,
        unhealthy=unhealthy,
    )


def test_schedules_model_when_capacity_is_available():
    decision = scheduler().schedule("small-local", [gpu("gpu-0")], batch_size=4)

    assert decision.status == SchedulingStatus.SCHEDULED
    assert decision.scheduled
    assert decision.device_id == "gpu-0"
    assert decision.reason == "gpu_capacity_available"


def test_selects_tightest_memory_fit_to_avoid_fragmenting_larger_gpu():
    decision = scheduler().schedule(
        "small-local",
        [gpu("large", total=80_000, used=0), gpu("tight", total=16_000, used=2_000)],
    )

    assert decision.device_id == "tight"


def test_defers_when_memory_capacity_is_insufficient():
    decision = scheduler().schedule("large-local", [gpu("gpu-0", total=24_000, used=1_000)], batch_size=1)

    assert decision.status == SchedulingStatus.DEFERRED
    assert decision.reason == "insufficient_gpu_capacity"
    assert decision.required_memory_mb == 25_000


def test_defers_when_projected_utilization_is_too_high():
    decision = scheduler().schedule("large-local", [gpu("gpu-0", util=50)], batch_size=1)

    assert decision.status == SchedulingStatus.DEFERRED
    assert decision.reason == "insufficient_gpu_capacity"


def test_rejects_unknown_model_profiles():
    decision = scheduler().schedule("unknown-model", [gpu("gpu-0")])

    assert decision.status == SchedulingStatus.REJECTED
    assert decision.reason == "unknown_model_resource_profile"


def test_defers_batch_that_exceeds_model_profile():
    decision = scheduler().schedule("large-local", [gpu("gpu-0")], batch_size=4)

    assert decision.status == SchedulingStatus.DEFERRED
    assert decision.reason == "batch_size_exceeds_model_profile"


def test_ignores_unhealthy_devices():
    decision = scheduler().schedule("small-local", [gpu("bad", unhealthy=True)])

    assert decision.status == SchedulingStatus.DEFERRED
    assert decision.reason == "insufficient_gpu_capacity"


def test_device_snapshot_validates_memory_values():
    with pytest.raises(ValueError):
        gpu("invalid", total=4_000, used=5_000)
