"""
Unit tests for configuration management.
Tests the critical path of config loading and validation.
"""
import os
import pytest
from pathlib import Path
from unittest.mock import patch, Mock
from pydantic import ValidationError

from ai_inference.core.config import WorkerConfig, ConfigManager, get_config_manager


class TestWorkerConfig:
    """Test WorkerConfig validation."""
    
    def test_valid_config_creation(self):
        """Test creating valid configuration."""
        config_data = {
            "aws_region": "us-east-1",
            "aws_account_id": "123456789012",
            "queue_name": "test-queue",
            "dlq_name": "test-dlq",
            "ssm_kill_switch": "/test/kill-switch",
            "ssm_config_prefix": "/test/config",
            "log_group_name": "/aws/test",
            "log_stream_name": "test-stream",
            "vllm_url": "http://localhost:8000",
            "vllm_model": "test-model",
            "vpn_tunnel_cidr": "10.0.0.0/16",
            "home_ip": "1.2.3.4",
            "vpc_cidr": "10.0.0.0/16"
        }
        
        config = WorkerConfig(**config_data)
        assert config.aws_region == "us-east-1"
        assert config.queue_name == "test-queue"
        assert config.vllm_temperature == 0.1  # default value
    
    def test_invalid_vllm_url(self):
        """Test validation of vLLM URL."""
        config_data = {
            "aws_region": "us-east-1",
            "aws_account_id": "123456789012",
            "queue_name": "test-queue",
            "dlq_name": "test-dlq",
            "ssm_kill_switch": "/test/kill-switch",
            "ssm_config_prefix": "/test/config",
            "log_group_name": "/aws/test",
            "log_stream_name": "test-stream",
            "vllm_url": "invalid-url",  # Invalid URL
            "vllm_model": "test-model",
            "vpn_tunnel_cidr": "10.0.0.0/16",
            "home_ip": "1.2.3.4",
            "vpc_cidr": "10.0.0.0/16"
        }
        
        with pytest.raises(ValidationError):
            WorkerConfig(**config_data)
    
    def test_queue_url_generation(self):
        """Test SQS URL generation."""
        config_data = {
            "aws_region": "us-west-2",
            "aws_account_id": "987654321098",
            "queue_name": "my-queue",
            "dlq_name": "my-dlq",
            "ssm_kill_switch": "/test/kill-switch",
            "ssm_config_prefix": "/test/config",
            "log_group_name": "/aws/test",
            "log_stream_name": "test-stream",
            "vllm_url": "http://localhost:8000",
            "vllm_model": "test-model",
            "vpn_tunnel_cidr": "10.0.0.0/16",
            "home_ip": "1.2.3.4",
            "vpc_cidr": "10.0.0.0/16"
        }
        
        config = WorkerConfig(**config_data)
        expected_url = "https://sqs.us-west-2.amazonaws.com/987654321098/my-queue"
        assert config.queue_url == expected_url


class TestConfigManager:
    """Test ConfigManager functionality."""
    
    def test_config_loading_success(self, temp_config_dir):
        """Test successful configuration loading."""
        with patch('ai_inference.core.config.Path') as mock_path:
            mock_path.return_value.parent.parent = Path(temp_config_dir)
            
            manager = ConfigManager("test")
            config = manager.get_config()
            
            assert config.aws_region == "us-east-1"
            assert config.queue_name == "test-rag-queue"
            assert config.vllm_url == "http://localhost:8000"
    
    def test_config_file_not_found(self):
        """Test handling of missing config file."""
        with patch('ai_inference.core.config.Path') as mock_path:
            mock_path.return_value.parent.parent = Path("/nonexistent")
            
            with pytest.raises(FileNotFoundError):
                ConfigManager("nonexistent")
    
    def test_environment_override(self, temp_config_dir):
        """Test environment variable override."""
        with patch('ai_inference.core.config.Path') as mock_path:
            mock_path.return_value.parent.parent = Path(temp_config_dir)
            
            # Override with environment variable
            with patch.dict(os.environ, {"AWS_REGION": "eu-west-1"}):
                manager = ConfigManager("test")
                config = manager.get_config()
                
                assert config.aws_region == "eu-west-1"  # Overridden value
    
    @patch('boto3.Session')
    def test_aws_connectivity_validation_success(self, mock_session, temp_config_dir):
        """Test successful AWS connectivity validation."""
        with patch('ai_inference.core.config.Path') as mock_path:
            mock_path.return_value.parent.parent = Path(temp_config_dir)
            
            # Mock AWS clients
            mock_sqs = Mock()
            mock_ssm = Mock()
            mock_logs = Mock()
            
            mock_session.return_value.client.side_effect = lambda service: {
                'sqs': mock_sqs,
                'ssm': mock_ssm,
                'logs': mock_logs
            }[service]
            
            manager = ConfigManager("test")
            result = manager.validate_aws_connectivity()
            
            assert result is True
            mock_sqs.get_queue_attributes.assert_called_once()
            mock_ssm.get_parameter.assert_called_once()
            mock_logs.describe_log_groups.assert_called_once()
    
    @patch('boto3.Session')
    def test_aws_connectivity_validation_failure(self, mock_session, temp_config_dir):
        """Test AWS connectivity validation failure."""
        from botocore.exceptions import ClientError
        
        with patch('ai_inference.core.config.Path') as mock_path:
            mock_path.return_value.parent.parent = Path(temp_config_dir)
            
            # Mock AWS client that raises error
            mock_sqs = Mock()
            mock_sqs.get_queue_attributes.side_effect = ClientError(
                {'Error': {'Code': 'AccessDenied'}}, 'GetQueueAttributes'
            )
            
            mock_session.return_value.client.return_value = mock_sqs
            
            manager = ConfigManager("test")
            result = manager.validate_aws_connectivity()
            
            assert result is False


class TestGlobalConfigManager:
    """Test global configuration manager functions."""
    
    def test_get_config_manager_singleton(self, temp_config_dir):
        """Test singleton behavior of global config manager."""
        with patch('ai_inference.core.config.Path') as mock_path:
            mock_path.return_value.parent.parent = Path(temp_config_dir)
            
            manager1 = get_config_manager("test")
            manager2 = get_config_manager("test")
            
            assert manager1 is manager2  # Same instance
    
    def test_get_config_manager_different_environment(self, temp_config_dir):
        """Test creating new manager for different environment."""
        # Create a dev.env in the temp config dir so the manager can load it
        dev_config = Path(temp_config_dir) / "config" / "dev.env"
        dev_config.write_text("""
AWS_REGION=us-west-2
AWS_ACCOUNT_ID=123456789012
QUEUE_NAME=dev-rag-queue
DLQ_NAME=dev-rag-dlq
SSM_KILL_SWITCH=/rag/dev/kill-switch
SSM_CONFIG_PREFIX=/rag/dev/config
LOG_GROUP_NAME=/aws/rag/dev
LOG_STREAM_NAME=dev-worker
VLLM_URL=http://localhost:8000
VLLM_MODEL=dev-model
VPN_TUNNEL_CIDR=10.0.0.0/16
HOME_IP=1.2.3.4
VPC_CIDR=10.0.0.0/16
ALERT_EMAIL=dev@example.com
""")

        with patch('ai_inference.core.config.Path') as mock_path:
            mock_path.return_value.parent.parent = Path(temp_config_dir)

            manager1 = get_config_manager("test")
            manager2 = get_config_manager("dev")

            assert manager1 is not manager2
            assert manager1.environment == "test"
            assert manager2.environment == "dev"