"""
Unit tests for RAG worker functionality.
Tests the critical paths of worker health monitoring and message processing.
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from ai_inference.core.worker import WorkerHealth, RAGWorker, RAGTask


class TestWorkerHealth:
    """Test WorkerHealth monitoring."""
    
    def test_initial_health_state(self):
        """Test initial health state."""
        health = WorkerHealth()
        
        assert health.is_healthy is True
        assert health.messages_processed == 0
        assert health.errors_count == 0
        assert health.last_error is None
    
    def test_heartbeat_update(self):
        """Test heartbeat timestamp update."""
        health = WorkerHealth()
        initial_heartbeat = health.last_heartbeat
        
        # Small delay to ensure timestamp difference
        import time
        time.sleep(0.01)
        
        health.heartbeat()
        assert health.last_heartbeat > initial_heartbeat
    
    def test_success_recording(self):
        """Test recording successful operations."""
        health = WorkerHealth()
        
        health.record_success()
        
        assert health.messages_processed == 1
        assert health.is_healthy is True
    
    def test_error_recording(self):
        """Test recording errors."""
        health = WorkerHealth()
        
        health.record_error("Test error")
        
        assert health.errors_count == 1
        assert health.last_error == "Test error"
    
    def test_health_status_with_high_error_rate(self):
        """Test health status becomes unhealthy with high error rate."""
        health = WorkerHealth()
        
        # Record some successes first
        for _ in range(5):
            health.record_success()
        
        # Record many errors to trigger unhealthy state
        for i in range(15):
            health.record_error(f"Error {i}")
        
        assert health.is_healthy is False
    
    def test_get_status_format(self):
        """Test health status format."""
        health = WorkerHealth()
        health.record_success()
        health.record_error("Test error")
        
        status = health.get_status()
        
        required_keys = [
            "healthy", "uptime_seconds", "messages_processed", 
            "errors_count", "last_heartbeat", "last_error"
        ]
        
        for key in required_keys:
            assert key in status
        
        assert isinstance(status["uptime_seconds"], int)
        assert status["messages_processed"] == 1
        assert status["errors_count"] == 1


class TestRAGTask:
    """Test RAGTask model validation."""
    
    def test_valid_task_creation(self):
        """Test creating valid RAG task."""
        task_data = {
            "prompt": "Test prompt",
            "context": "Test context",
            "event_type": "test_event"
        }
        
        task = RAGTask(**task_data)
        
        assert task.prompt == "Test prompt"
        assert task.context == "Test context"
        assert task.event_type == "test_event"
    
    def test_task_with_defaults(self):
        """Test task creation with default values."""
        task_data = {
            "prompt": "Test prompt",
            "context": "Test context"
        }
        
        task = RAGTask(**task_data)
        
        assert task.event_type == "general_inference"  # Default value
        assert task.event_id is None
        assert task.timestamp is None


class TestRAGWorker:
    """Test RAGWorker functionality."""

    def _make_mock_config(self, **overrides):
        """Build a mock config with all attributes the worker expects."""
        defaults = {
            "aws_region": "us-east-1",
            "log_group_name": "/test/log",
            "log_stream_name": "test-stream",
            "vllm_url": "http://localhost:8000",
            "vllm_model": "test-model",
            "vllm_small_model": None,
            "vllm_large_model": None,
            "vllm_small_context_tokens": 4096,
            "vllm_large_context_tokens": 32768,
            "vllm_temperature": 0.1,
            "vllm_max_tokens": 2048,
            "worker_max_retries": 3,
            "worker_backoff_factor": 2.0,
            "worker_batch_size": 4,
            "worker_batch_token_budget": 12000,
            "queue_url": "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue",
            "ssm_kill_switch": "/test/kill-switch",
            "health_check_enabled": False,
            "gpu_scheduling_enabled": True,
            "gpu_memory_reserve_mb": 1024,
            "gpu_max_utilization_percent": 92.0,
            "gpu_small_model_memory_mb": 8192,
            "gpu_large_model_memory_mb": 24576,
            "gpu_small_model_max_batch_size": 8,
            "gpu_large_model_max_batch_size": 2,
            "gpu_device_id": "gpu-0",
            "gpu_device_name": "local-gpu",
            "gpu_device_memory_mb": 49152,
            "gpu_device_used_memory_mb": 0,
            "gpu_device_utilization_percent": 0.0,
            "result_store_table_name": "inference-results",
            "result_store_ttl_days": 7,
            "request_ttl_seconds": 300.0,
            "circuit_breaker_failure_threshold": 5,
            "circuit_breaker_recovery_timeout_seconds": 30.0,
            "latency_window_size": 100,
            "latency_p95_threshold_ms": 2000.0,
            "latency_min_samples": 10,
        }
        defaults.update(overrides)
        mock_config = Mock()
        for k, v in defaults.items():
            setattr(mock_config, k, v)
        return mock_config
    
    @patch('ai_inference.core.worker.get_config')
    @patch('boto3.Session')
    def test_worker_initialization(self, mock_session, mock_get_config, mock_openai_client):
        """Test worker initialization."""
        mock_get_config.return_value = self._make_mock_config()
        mock_session.return_value.client.return_value = Mock()

        worker = RAGWorker("test")

        assert worker.config == mock_get_config.return_value
        assert worker.health is not None
        assert worker.logger is not None
    
    @patch('ai_inference.core.worker.get_config')
    @patch('boto3.Session')
    def test_kill_switch_check_enabled(self, mock_session, mock_get_config, mock_openai_client):
        """Test kill switch check when enabled."""
        mock_get_config.return_value = self._make_mock_config()

        mock_ssm = Mock()
        mock_ssm.get_parameter.return_value = {
            'Parameter': {'Value': 'true'}
        }
        mock_session.return_value.client.return_value = mock_ssm

        worker = RAGWorker("test")
        worker.ssm = mock_ssm

        result = worker.check_kill_switch()

        assert result is True
        mock_ssm.get_parameter.assert_called_with(Name="/test/kill-switch")
    
    @patch('ai_inference.core.worker.get_config')
    @patch('boto3.Session')
    def test_kill_switch_check_disabled(self, mock_session, mock_get_config, mock_openai_client):
        """Test kill switch check when disabled."""
        mock_get_config.return_value = self._make_mock_config()

        mock_ssm = Mock()
        mock_ssm.get_parameter.return_value = {
            'Parameter': {'Value': 'false'}
        }
        mock_session.return_value.client.return_value = mock_ssm

        worker = RAGWorker("test")
        worker.ssm = mock_ssm

        result = worker.check_kill_switch()

        assert result is False
    
    @patch('ai_inference.core.worker.get_config')
    @patch('boto3.Session')
    def test_perform_inference_success(self, mock_session, mock_get_config, mock_openai_client):
        """Test successful inference."""
        mock_get_config.return_value = self._make_mock_config()
        mock_session.return_value.client.return_value = Mock()

        worker = RAGWorker("test")

        task = RAGTask(
            prompt="Test prompt",
            context="Test context",
            event_type="test"
        )

        result = worker.perform_inference(task)

        assert result == "Test AI response"
        assert worker.health.messages_processed == 1
    
    @patch('ai_inference.core.worker.get_config')
    @patch('boto3.Session')
    def test_process_message_success(self, mock_session, mock_get_config, mock_openai_client, sample_rag_task):
        """Test successful message processing."""
        mock_get_config.return_value = self._make_mock_config()

        mock_sqs = Mock()
        mock_session.return_value.client.return_value = mock_sqs

        worker = RAGWorker("test")
        worker.sqs = mock_sqs

        message = {
            "Body": json.dumps(sample_rag_task),
            "ReceiptHandle": "test-receipt-handle"
        }

        result = worker.process_message(message)

        assert result is True
        mock_sqs.delete_message.assert_called_once_with(
            QueueUrl=worker.config.queue_url,
            ReceiptHandle="test-receipt-handle"
        )
    
    @patch('ai_inference.core.worker.get_config')
    @patch('boto3.Session')
    def test_process_message_invalid_json(self, mock_session, mock_get_config, mock_openai_client):
        """Test message processing with invalid JSON."""
        mock_get_config.return_value = self._make_mock_config()
        mock_session.return_value.client.return_value = Mock()

        worker = RAGWorker("test")

        message = {
            "Body": "invalid json",
            "ReceiptHandle": "test-receipt-handle"
        }

        result = worker.process_message(message)

        assert result is False
        assert worker.health.errors_count > 0