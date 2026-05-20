"""
Autoscaler executor for the secure inference platform.

Executes scaling decisions produced by the Autoscaler. Protocol boundary
allows swapping between ECS, ASG, or a no-op executor.

Usage:
    from ai_inference.core.scaling_executor import EcsScalingExecutor, LogOnlyExecutor

    executor = EcsScalingExecutor(cluster="inference", service="workers", region="us-east-1")
    executor.execute(decision)
"""
from __future__ import annotations

from typing import Protocol

from ai_inference.core.autoscaler import ScalingAction, ScalingDecision
from ai_inference.core.logging import get_logger

logger = get_logger("scaling_executor")


class ScalingExecutor(Protocol):
    def execute(self, decision: ScalingDecision) -> bool: ...


class LogOnlyExecutor:
    """Logs scaling decisions without acting. Default for dry-run mode."""

    def execute(self, decision: ScalingDecision) -> bool:
        if decision.action == ScalingAction.HOLD:
            return True
        logger.info(
            "would scale",
            action=decision.action.value,
            current=decision.current_workers,
            desired=decision.desired_workers,
            reason=decision.reason,
        )
        return True


class EcsScalingExecutor:
    """Scales an ECS service by updating desired count."""

    def __init__(self, cluster: str, service: str, region: str = "us-east-1") -> None:
        import boto3
        self._client = boto3.client("ecs", region_name=region)
        self._cluster = cluster
        self._service = service

    def execute(self, decision: ScalingDecision) -> bool:
        if decision.action == ScalingAction.HOLD:
            return True
        try:
            self._client.update_service(
                cluster=self._cluster,
                service=self._service,
                desiredCount=decision.desired_workers,
            )
            logger.info(
                "ECS service scaled",
                cluster=self._cluster,
                service=self._service,
                desired=decision.desired_workers,
                reason=decision.reason,
            )
            return True
        except Exception as e:
            logger.error(
                "ECS scaling failed",
                cluster=self._cluster,
                service=self._service,
                error=str(e),
            )
            return False


class AsgScalingExecutor:
    """Scales an Auto Scaling Group by updating desired capacity."""

    def __init__(self, asg_name: str, region: str = "us-east-1") -> None:
        import boto3
        self._client = boto3.client("autoscaling", region_name=region)
        self._asg_name = asg_name

    def execute(self, decision: ScalingDecision) -> bool:
        if decision.action == ScalingAction.HOLD:
            return True
        try:
            self._client.set_desired_capacity(
                AutoScalingGroupName=self._asg_name,
                DesiredCapacity=decision.desired_workers,
            )
            logger.info(
                "ASG scaled",
                asg=self._asg_name,
                desired=decision.desired_workers,
                reason=decision.reason,
            )
            return True
        except Exception as e:
            logger.error(
                "ASG scaling failed",
                asg=self._asg_name,
                error=str(e),
            )
            return False
