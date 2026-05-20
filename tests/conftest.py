"""Pytest configuration and shared fixtures for Air-Gapped RAG tests."""
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch


@pytest.fixture
def temp_config_dir():
    """Create temporary config directory with test environment files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / "config"
        config_dir.mkdir()
        
        # Create test config file
        test_config = config_dir / "test.env"
        test_config.write_text("""
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012
QUEUE_NAME=test-rag-queue
DLQ_NAME=test-rag-dlq
SSM_KILL_SWITCH=/rag/test/kill-switch
SSM_CONFIG_PREFIX=/rag/test/config
LOG_GROUP_NAME=/aws/rag/test
LOG_STREAM_NAME=test-worker
VLLM_URL=http://localhost:8000
VLLM_MODEL=test-model
VPN_TUNNEL_CIDR=10.0.0.0/16
HOME_IP=1.2.3.4
VPC_CIDR=10.0.0.0/16
ALERT_EMAIL=test@example.com
""")
        
        # Patch the config path
        with patch('ai_inference.core.config.Path') as mock_path:
            mock_path.return_value.parent.parent = Path(temp_dir)
            yield temp_dir


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for testing."""
    mock_client = Mock()
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = "Test AI response"
    mock_client.chat.completions.create.return_value = mock_response
    mock_client.models.list.return_value = []
    
    with patch('ai_inference.core.worker.OpenAI', return_value=mock_client):
        yield mock_client


@pytest.fixture
def sample_rag_task():
    """Sample RAG task for testing."""
    return {
        "prompt": "What is the capital of France?",
        "context": "France is a country in Europe. Paris is its capital city.",
        "event_type": "test_inference",
        "event_id": "test-123",
        "timestamp": "2024-01-01T00:00:00Z"
    }