"""
Configuration management for Air-Gapped RAG system.
Handles environment variables, validation, and secrets management.
"""
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class WorkerConfig(BaseModel):
    """Worker configuration with validation."""
    
    # AWS Configuration
    aws_region: str = Field(..., description="AWS region")
    aws_account_id: str = Field(..., description="AWS account ID")
    
    # Queue Configuration
    queue_name: str = Field(..., description="SQS queue name")
    dlq_name: str = Field(..., description="Dead letter queue name")
    queue_visibility_timeout: int = Field(300, ge=30, le=43200)
    max_receive_count: int = Field(3, ge=1, le=10)
    
    # SSM Configuration
    ssm_kill_switch: str = Field(..., description="SSM parameter for kill switch")
    ssm_config_prefix: str = Field(..., description="SSM parameter prefix")
    
    # CloudWatch Configuration
    log_group_name: str = Field(..., description="CloudWatch log group")
    log_stream_name: str = Field(..., description="CloudWatch log stream")
    log_retention_days: int = Field(7, ge=1, le=365)
    
    # vLLM Configuration
    vllm_url: str = Field(..., description="vLLM server URL")
    vllm_model: str = Field(..., description="Default vLLM model name")
    vllm_small_model: Optional[str] = Field(None, description="Small model for lower complexity inference")
    vllm_large_model: Optional[str] = Field(None, description="Large model for complex or long context inference")
    vllm_small_context_tokens: int = Field(4096, ge=512, le=262144)
    vllm_large_context_tokens: int = Field(32768, ge=512, le=262144)
    vllm_temperature: float = Field(0.1, ge=0.0, le=2.0)
    vllm_max_tokens: int = Field(2048, ge=1, le=8192)
    
    # Worker Configuration
    worker_poll_interval: int = Field(20, ge=1, le=300)
    worker_health_check_interval: int = Field(30, ge=5, le=300)
    worker_max_retries: int = Field(3, ge=1, le=10)
    worker_backoff_factor: float = Field(2.0, ge=1.0, le=10.0)
    worker_batch_size: int = Field(4, ge=1, le=10)
    worker_batch_token_budget: int = Field(12000, ge=1, le=262144)

    # GPU Scheduling Configuration
    gpu_scheduling_enabled: bool = Field(True, description="Enable GPU-aware scheduling checks")
    gpu_memory_reserve_mb: int = Field(1024, ge=0, le=131072)
    gpu_max_utilization_percent: float = Field(92.0, ge=1.0, le=100.0)
    gpu_small_model_memory_mb: int = Field(8192, ge=1, le=262144)
    gpu_large_model_memory_mb: int = Field(24576, ge=1, le=262144)
    gpu_small_model_max_batch_size: int = Field(8, ge=1, le=256)
    gpu_large_model_max_batch_size: int = Field(2, ge=1, le=256)
    gpu_device_id: str = Field("gpu-0", description="Logical GPU device identifier for local scheduling")
    gpu_device_name: str = Field("local-gpu", description="Human-readable GPU device name")
    gpu_device_memory_mb: int = Field(49152, ge=1, le=262144)
    gpu_device_used_memory_mb: int = Field(0, ge=0, le=262144)
    gpu_device_utilization_percent: float = Field(0.0, ge=0.0, le=100.0)

    # Result Store Configuration
    result_store_table_name: str = Field("inference-results", description="DynamoDB table for result store")
    result_store_ttl_days: int = Field(7, ge=1, le=90)

    # Request TTL Configuration
    request_ttl_seconds: float = Field(300.0, ge=10.0, le=3600.0)

    # Circuit Breaker Configuration
    circuit_breaker_failure_threshold: int = Field(5, ge=1, le=100)
    circuit_breaker_recovery_timeout_seconds: float = Field(30.0, ge=1.0, le=600.0)

    # Latency Tracker Configuration
    latency_window_size: int = Field(100, ge=10, le=10000)
    latency_p95_threshold_ms: float = Field(2000.0, ge=100.0, le=60000.0)
    latency_min_samples: int = Field(10, ge=1, le=100)

    
    # VPN Configuration
    vpn_tunnel_cidr: str = Field(..., description="VPN tunnel CIDR")
    vpn_bgp_asn: int = Field(65000, ge=1, le=4294967295)
    home_ip: str = Field(..., description="Home gateway IP")
    vpc_cidr: str = Field(..., description="VPC CIDR block")
    
    # Security Configuration
    encryption_at_rest: bool = Field(True, description="Enable encryption at rest")
    vpn_key_rotation_days: int = Field(90, ge=1, le=365)
    session_timeout_minutes: int = Field(30, ge=5, le=1440)
    
    # Monitoring Configuration
    health_check_enabled: bool = Field(True, description="Enable health checks")
    metrics_enabled: bool = Field(True, description="Enable metrics collection")
    alert_email: Optional[str] = Field(None, description="Alert email address")
    
    @field_validator('vllm_url')
    @classmethod
    def validate_vllm_url(cls, v: str) -> str:
        if not v.startswith(('http://', 'https://')):
            raise ValueError('vLLM URL must start with http:// or https://')
        return v

    @field_validator('alert_email')
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v and '@' not in v:
            raise ValueError('Invalid email address')
        return v
    
    @property
    def queue_url(self) -> str:
        """Generate SQS queue URL."""
        return f"https://sqs.{self.aws_region}.amazonaws.com/{self.aws_account_id}/{self.queue_name}"
    
    @property
    def dlq_url(self) -> str:
        """Generate DLQ URL."""
        return f"https://sqs.{self.aws_region}.amazonaws.com/{self.aws_account_id}/{self.dlq_name}"

class ConfigManager:
    """Manages configuration loading and validation."""
    
    def __init__(self, environment: str = "dev"):
        self.environment = environment.lower()
        self.config: Optional[WorkerConfig] = None
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from environment file."""
        config_file = Path(__file__).parent.parent / "config" / f"{self.environment}.env"
        
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        # Load environment file
        load_dotenv(config_file)
        
        # Override with actual environment variables
        load_dotenv(override=True)
        
        try:
            # Convert environment variables to config
            config_dict = self._env_to_dict()
            self.config = WorkerConfig(**config_dict)
            logger.info(f"Configuration loaded for environment: {self.environment}")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise
    
    def _env_to_dict(self) -> Dict[str, Any]:
        """Convert environment variables to configuration dictionary."""
        return {
            # AWS Configuration
            "aws_region": os.getenv("AWS_REGION"),
            "aws_account_id": os.getenv("AWS_ACCOUNT_ID"),
            
            # Queue Configuration
            "queue_name": os.getenv("QUEUE_NAME"),
            "dlq_name": os.getenv("DLQ_NAME"),
            "queue_visibility_timeout": int(os.getenv("QUEUE_VISIBILITY_TIMEOUT", "300")),
            "max_receive_count": int(os.getenv("MAX_RECEIVE_COUNT", "3")),
            
            # SSM Configuration
            "ssm_kill_switch": os.getenv("SSM_KILL_SWITCH"),
            "ssm_config_prefix": os.getenv("SSM_CONFIG_PREFIX"),
            
            # CloudWatch Configuration
            "log_group_name": os.getenv("LOG_GROUP_NAME"),
            "log_stream_name": os.getenv("LOG_STREAM_NAME"),
            "log_retention_days": int(os.getenv("LOG_RETENTION_DAYS", "7")),
            
            # vLLM Configuration
            "vllm_url": os.getenv("VLLM_URL"),
            "vllm_model": os.getenv("VLLM_MODEL"),
            "vllm_small_model": os.getenv("VLLM_SMALL_MODEL"),
            "vllm_large_model": os.getenv("VLLM_LARGE_MODEL"),
            "vllm_small_context_tokens": int(os.getenv("VLLM_SMALL_CONTEXT_TOKENS", "4096")),
            "vllm_large_context_tokens": int(os.getenv("VLLM_LARGE_CONTEXT_TOKENS", "32768")),
            "vllm_temperature": float(os.getenv("VLLM_TEMPERATURE", "0.1")),
            "vllm_max_tokens": int(os.getenv("VLLM_MAX_TOKENS", "2048")),
            
            # Worker Configuration
            "worker_poll_interval": int(os.getenv("WORKER_POLL_INTERVAL", "20")),
            "worker_health_check_interval": int(os.getenv("WORKER_HEALTH_CHECK_INTERVAL", "30")),
            "worker_max_retries": int(os.getenv("WORKER_MAX_RETRIES", "3")),
            "worker_backoff_factor": float(os.getenv("WORKER_BACKOFF_FACTOR", "2.0")),
            "worker_batch_size": int(os.getenv("WORKER_BATCH_SIZE", "4")),
            "worker_batch_token_budget": int(os.getenv("WORKER_BATCH_TOKEN_BUDGET", "12000")),

            # GPU Scheduling Configuration
            "gpu_scheduling_enabled": os.getenv("GPU_SCHEDULING_ENABLED", "true").lower() == "true",
            "gpu_memory_reserve_mb": int(os.getenv("GPU_MEMORY_RESERVE_MB", "1024")),
            "gpu_max_utilization_percent": float(os.getenv("GPU_MAX_UTILIZATION_PERCENT", "92.0")),
            "gpu_small_model_memory_mb": int(os.getenv("GPU_SMALL_MODEL_MEMORY_MB", "8192")),
            "gpu_large_model_memory_mb": int(os.getenv("GPU_LARGE_MODEL_MEMORY_MB", "24576")),
            "gpu_small_model_max_batch_size": int(os.getenv("GPU_SMALL_MODEL_MAX_BATCH_SIZE", "8")),
            "gpu_large_model_max_batch_size": int(os.getenv("GPU_LARGE_MODEL_MAX_BATCH_SIZE", "2")),
            "gpu_device_id": os.getenv("GPU_DEVICE_ID", "gpu-0"),
            "gpu_device_name": os.getenv("GPU_DEVICE_NAME", "local-gpu"),
            "gpu_device_memory_mb": int(os.getenv("GPU_DEVICE_MEMORY_MB", "49152")),
            "gpu_device_used_memory_mb": int(os.getenv("GPU_DEVICE_USED_MEMORY_MB", "0")),
            "gpu_device_utilization_percent": float(os.getenv("GPU_DEVICE_UTILIZATION_PERCENT", "0.0")),

            # Result Store Configuration
            "result_store_table_name": os.getenv("RESULT_STORE_TABLE_NAME", "inference-results"),
            "result_store_ttl_days": int(os.getenv("RESULT_STORE_TTL_DAYS", "7")),

            # Request TTL Configuration
            "request_ttl_seconds": float(os.getenv("REQUEST_TTL_SECONDS", "300.0")),

            # Circuit Breaker Configuration
            "circuit_breaker_failure_threshold": int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")),
            "circuit_breaker_recovery_timeout_seconds": float(os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SECONDS", "30.0")),

            # Latency Tracker Configuration
            "latency_window_size": int(os.getenv("LATENCY_WINDOW_SIZE", "100")),
            "latency_p95_threshold_ms": float(os.getenv("LATENCY_P95_THRESHOLD_MS", "2000.0")),
            "latency_min_samples": int(os.getenv("LATENCY_MIN_SAMPLES", "10")),
            
            # VPN Configuration
            "vpn_tunnel_cidr": os.getenv("VPN_TUNNEL_CIDR"),
            "vpn_bgp_asn": int(os.getenv("VPN_BGP_ASN", "65000")),
            "home_ip": os.getenv("HOME_IP"),
            "vpc_cidr": os.getenv("VPC_CIDR"),
            
            # Security Configuration
            "encryption_at_rest": os.getenv("ENCRYPTION_AT_REST", "true").lower() == "true",
            "vpn_key_rotation_days": int(os.getenv("VPN_KEY_ROTATION_DAYS", "90")),
            "session_timeout_minutes": int(os.getenv("SESSION_TIMEOUT_MINUTES", "30")),
            
            # Monitoring Configuration
            "health_check_enabled": os.getenv("HEALTH_CHECK_ENABLED", "true").lower() == "true",
            "metrics_enabled": os.getenv("METRICS_ENABLED", "true").lower() == "true",
            "alert_email": os.getenv("ALERT_EMAIL"),
        }
    
    def get_config(self) -> WorkerConfig:
        """Get the loaded configuration."""
        if not self.config:
            raise RuntimeError("Configuration not loaded")
        return self.config
    
    def validate_aws_connectivity(self) -> bool:
        """Validate AWS connectivity and permissions."""
        try:
            import boto3
            from botocore.exceptions import ClientError
            
            session = boto3.Session(region_name=self.config.aws_region)
            
            # Test SQS access
            sqs = session.client("sqs")
            sqs.get_queue_attributes(QueueUrl=self.config.queue_url, AttributeNames=['All'])
            
            # Test SSM access
            ssm = session.client("ssm")
            ssm.get_parameter(Name=self.config.ssm_kill_switch)
            
            # Test CloudWatch Logs access
            logs = session.client("logs")
            logs.describe_log_groups(logGroupNamePrefix=self.config.log_group_name)
            
            logger.info("AWS connectivity validation successful")
            return True
            
        except ClientError as e:
            logger.error(f"AWS connectivity validation failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during AWS validation: {e}")
            return False

# Global configuration instance
_config_manager: Optional[ConfigManager] = None

def get_config_manager(environment: str = None) -> ConfigManager:
    """Get or create the global configuration manager."""
    global _config_manager
    
    if _config_manager is None or (environment and _config_manager.environment != environment):
        env = environment or os.getenv("ENVIRONMENT", "dev")
        _config_manager = ConfigManager(env)
    
    return _config_manager

def get_config(environment: str = None) -> WorkerConfig:
    """Get the current configuration."""
    return get_config_manager(environment).get_config()