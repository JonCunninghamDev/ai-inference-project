"""Unit tests for the scaling executor module."""
from unittest.mock import Mock, patch

import pytest

from ai_inference.core.autoscaler import ScalingAction, ScalingDecision
from ai_inference.core.scaling_executor import AsgScalingExecutor, EcsScalingExecutor, LogOnlyExecutor


class TestLogOnlyExecutor:
    def test_hold_returns_true(self):
        executor = LogOnlyExecutor()
        decision = ScalingDecision(
            action=ScalingAction.HOLD, reason="ok",
            current_workers=2, desired_workers=2, dry_run=True,
        )
        assert executor.execute(decision) is True

    def test_scale_up_returns_true(self):
        executor = LogOnlyExecutor()
        decision = ScalingDecision(
            action=ScalingAction.SCALE_UP, reason="queue wait",
            current_workers=2, desired_workers=3, dry_run=True,
        )
        assert executor.execute(decision) is True

    def test_scale_down_returns_true(self):
        executor = LogOnlyExecutor()
        decision = ScalingDecision(
            action=ScalingAction.SCALE_DOWN, reason="idle",
            current_workers=3, desired_workers=2, dry_run=True,
        )
        assert executor.execute(decision) is True


class TestEcsScalingExecutor:
    @patch("boto3.client")
    def test_scale_up_calls_update_service(self, mock_boto):
        mock_ecs = Mock()
        mock_boto.return_value = mock_ecs

        executor = EcsScalingExecutor(cluster="test-cluster", service="test-service")
        decision = ScalingDecision(
            action=ScalingAction.SCALE_UP, reason="queue wait",
            current_workers=2, desired_workers=3, dry_run=False,
        )
        result = executor.execute(decision)

        assert result is True
        mock_ecs.update_service.assert_called_once_with(
            cluster="test-cluster", service="test-service", desiredCount=3,
        )

    @patch("boto3.client")
    def test_hold_does_not_call_api(self, mock_boto):
        mock_ecs = Mock()
        mock_boto.return_value = mock_ecs

        executor = EcsScalingExecutor(cluster="test-cluster", service="test-service")
        decision = ScalingDecision(
            action=ScalingAction.HOLD, reason="ok",
            current_workers=2, desired_workers=2, dry_run=False,
        )
        executor.execute(decision)
        mock_ecs.update_service.assert_not_called()

    @patch("boto3.client")
    def test_api_failure_returns_false(self, mock_boto):
        mock_ecs = Mock()
        mock_ecs.update_service.side_effect = Exception("throttled")
        mock_boto.return_value = mock_ecs

        executor = EcsScalingExecutor(cluster="test-cluster", service="test-service")
        decision = ScalingDecision(
            action=ScalingAction.SCALE_UP, reason="queue wait",
            current_workers=2, desired_workers=3, dry_run=False,
        )
        result = executor.execute(decision)
        assert result is False


class TestAsgScalingExecutor:
    @patch("boto3.client")
    def test_scale_up_calls_set_desired_capacity(self, mock_boto):
        mock_asg = Mock()
        mock_boto.return_value = mock_asg

        executor = AsgScalingExecutor(asg_name="test-asg")
        decision = ScalingDecision(
            action=ScalingAction.SCALE_UP, reason="deferrals",
            current_workers=1, desired_workers=2, dry_run=False,
        )
        result = executor.execute(decision)

        assert result is True
        mock_asg.set_desired_capacity.assert_called_once_with(
            AutoScalingGroupName="test-asg", DesiredCapacity=2,
        )

    @patch("boto3.client")
    def test_api_failure_returns_false(self, mock_boto):
        mock_asg = Mock()
        mock_asg.set_desired_capacity.side_effect = Exception("access denied")
        mock_boto.return_value = mock_asg

        executor = AsgScalingExecutor(asg_name="test-asg")
        decision = ScalingDecision(
            action=ScalingAction.SCALE_DOWN, reason="idle",
            current_workers=3, desired_workers=2, dry_run=False,
        )
        result = executor.execute(decision)
        assert result is False
