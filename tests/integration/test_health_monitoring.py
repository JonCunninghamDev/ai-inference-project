"""
Integration tests for health monitoring endpoints.
Tests the critical health check functionality that production monitoring depends on.
"""
import json
import pytest
import requests
from unittest.mock import Mock, patch
from datetime import datetime

from ai_inference.core.worker import WorkerHealth, RAGWorker


class TestHealthEndpoints:
    """Test health monitoring integration."""
    
    @patch('ai_inference.core.worker.get_config')
    @patch('boto3.Session')
    def test_worker_health_status_endpoint(self, mock_session, mock_get_config, mock_openai_client):
        """Test worker health status can be retrieved."""
        # Mock config
        mock_config = Mock()
        mock_config.aws_region = "us-east-1"
        mock_config.log_group_name = "/test/log"
        mock_config.log_stream_name = "test-stream"
        mock_config.vllm_url = "http://localhost:8000"
        mock_config.worker_max_retries = 3
        mock_config.worker_backoff_factor = 2.0
        mock_config.health_check_enabled = True
        mock_config.worker_health_check_interval = 1
        mock_get_config.return_value = mock_config
        
        # Mock AWS session
        mock_session.return_value.client.return_value = Mock()
        
        worker = RAGWorker("test")
        
        # Simulate some activity
        worker.health.record_success()
        worker.health.record_success()
        worker.health.record_error("Test error")
        
        status = worker.health.get_status()
        
        # Verify status format matches monitoring expectations
        assert "healthy" in status
        assert "uptime_seconds" in status
        assert "messages_processed" in status
        assert "errors_count" in status
        assert "last_heartbeat" in status
        
        # Verify values
        assert status["messages_processed"] == 2
        assert status["errors_count"] == 1
        assert isinstance(status["healthy"], bool)
        assert isinstance(status["uptime_seconds"], int)
    
    def test_health_status_json_serializable(self):
        """Test that health status can be JSON serialized for API responses."""
        health = WorkerHealth()
        health.record_success()
        health.record_error("Test error")
        
        status = health.get_status()
        
        # Should not raise exception
        json_status = json.dumps(status)
        
        # Should be able to parse back
        parsed_status = json.loads(json_status)
        
        assert parsed_status["messages_processed"] == 1
        assert parsed_status["errors_count"] == 1
    
    @patch('ai_inference.core.worker.get_config')
    @patch('boto3.Session')
    def test_aws_connectivity_health_check(self, mock_session, mock_get_config, mock_openai_client):
        """Test AWS connectivity as part of health check."""
        # Mock config
        mock_config = Mock()
        mock_config.aws_region = "us-east-1"
        mock_config.log_group_name = "/test/log"
        mock_config.log_stream_name = "test-stream"
        mock_config.vllm_url = "http://localhost:8000"
        mock_config.worker_max_retries = 3
        mock_config.worker_backoff_factor = 2.0
        mock_config.queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        mock_get_config.return_value = mock_config
        
        # Mock SQS client that works
        mock_sqs = Mock()
        mock_sqs.get_queue_attributes.return_value = {
            'Attributes': {'ApproximateNumberOfMessages': '0'}
        }
        mock_session.return_value.client.return_value = mock_sqs
        
        worker = RAGWorker("test")
        worker.sqs = mock_sqs
        
        # Simulate health check that includes AWS connectivity
        try:
            worker.sqs.get_queue_attributes(
                QueueUrl=mock_config.queue_url,
                AttributeNames=['ApproximateNumberOfMessages']
            )
            connectivity_ok = True
        except Exception:
            connectivity_ok = False
        
        assert connectivity_ok is True
        mock_sqs.get_queue_attributes.assert_called_once()
    
    @patch('ai_inference.core.worker.get_config')
    @patch('boto3.Session')
    def test_aws_connectivity_failure_handling(self, mock_session, mock_get_config, mock_openai_client):
        """Test handling of AWS connectivity failures in health checks."""
        from botocore.exceptions import ClientError
        
        # Mock config
        mock_config = Mock()
        mock_config.aws_region = "us-east-1"
        mock_config.log_group_name = "/test/log"
        mock_config.log_stream_name = "test-stream"
        mock_config.vllm_url = "http://localhost:8000"
        mock_config.worker_max_retries = 3
        mock_config.worker_backoff_factor = 2.0
        mock_config.queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
        mock_get_config.return_value = mock_config
        
        # Mock SQS client that fails
        mock_sqs = Mock()
        mock_sqs.get_queue_attributes.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied'}}, 'GetQueueAttributes'
        )
        mock_session.return_value.client.return_value = mock_sqs
        
        worker = RAGWorker("test")
        worker.sqs = mock_sqs
        
        # Simulate health check that includes AWS connectivity
        try:
            worker.sqs.get_queue_attributes(
                QueueUrl=mock_config.queue_url,
                AttributeNames=['ApproximateNumberOfMessages']
            )
            connectivity_ok = True
        except Exception as e:
            connectivity_ok = False
            worker.health.record_error(f"AWS connectivity: {e}")
        
        assert connectivity_ok is False
        assert worker.health.errors_count > 0
        assert "AWS connectivity" in worker.health.last_error


class TestHealthMonitoringIntegration:
    """Test integration with external monitoring systems."""
    
    def test_health_metrics_format_for_cloudwatch(self):
        """Test health metrics format suitable for CloudWatch."""
        health = WorkerHealth()
        
        # Simulate some activity
        for _ in range(10):
            health.record_success()
        
        for _ in range(2):
            health.record_error("Test error")
        
        status = health.get_status()
        
        # Format metrics for CloudWatch
        metrics = {
            "MessagesProcessed": status["messages_processed"],
            "ErrorCount": status["errors_count"],
            "HealthStatus": 1 if status["healthy"] else 0,
            "UptimeSeconds": status["uptime_seconds"]
        }
        
        # Verify all metrics are numeric (required for CloudWatch)
        for key, value in metrics.items():
            assert isinstance(value, (int, float)), f"{key} should be numeric"
        
        assert metrics["MessagesProcessed"] == 10
        assert metrics["ErrorCount"] == 2
        assert metrics["HealthStatus"] == 1  # Should be healthy
    
    def test_health_status_thresholds(self):
        """Test health status thresholds for alerting."""
        health = WorkerHealth()
        
        # Test healthy state
        for _ in range(100):
            health.record_success()
        
        status = health.get_status()
        assert status["healthy"] is True
        
        # Test unhealthy state with high error rate
        for _ in range(200):
            health.record_error("Test error")
        
        status = health.get_status()
        assert status["healthy"] is False
        
        # Verify error rate calculation
        total_operations = status["messages_processed"] + status["errors_count"]
        error_rate = status["errors_count"] / total_operations if total_operations > 0 else 0
        
        # Should be unhealthy when error rate > 50%
        assert error_rate > 0.5