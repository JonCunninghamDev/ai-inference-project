from __future__ import annotations
import boto3
import json
import logging
try:
    import watchtower
except ImportError:  # pragma: no cover - optional in lightweight test environments
    watchtower = None
import time
import signal
import sys
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional in lightweight test environments
    OpenAI = None
from pydantic import BaseModel
from botocore.exceptions import ClientError, NoCredentialsError
from .config import get_config, WorkerConfig
from ai_inference.core.audit import AuditEvent, AuditLog, NullAuditLog
from ai_inference.core.logging import StructuredFormatter
from ai_inference.core.metrics import MetricsCollector
from ai_inference.core.ttl import RequestTTL
from ai_inference.inference.circuit_breaker import CircuitBreaker, CircuitBreakerPolicy
from ai_inference.inference.router import InferenceRequest, ModelProfile, ModelRouter
from ai_inference.inference.batching import BatchCandidate, BatchingPolicy, DynamicBatcher, InferenceBatch
from ai_inference.inference.gpu_scheduler import (
    GPUDeviceSnapshot,
    GPUScheduler,
    ModelResourceProfile,
    SchedulingPolicy,
)
from ai_inference.inference.latency import LatencyPolicy, LatencyTracker
from ai_inference.inference.vllm_adapter import InferenceAdapter, InferenceInput, MockVllmAdapter, VllmBatchAdapter
from ai_inference.core.result_store import DynamoResultStore, InferenceResult, InMemoryResultStore, RequestStatus, ResultStore
from ai_inference.gateway.tenant import TenantPolicyEngine

# Global shutdown flag
shutdown_event = threading.Event()

class WorkerHealth:
    """Tracks worker health metrics."""
    
    def __init__(self):
        self.last_heartbeat = datetime.now()
        self.messages_processed = 0
        self.errors_count = 0
        self.start_time = datetime.now()
        self.is_healthy = True
        self.last_error: Optional[str] = None
    
    def heartbeat(self):
        """Update heartbeat timestamp."""
        self.last_heartbeat = datetime.now()
    
    def record_success(self):
        """Record successful message processing."""
        self.messages_processed += 1
        self.is_healthy = True
    
    def record_error(self, error: str):
        """Record error."""
        self.errors_count += 1
        self.last_error = error
        # Mark unhealthy if error rate is too high
        if self.errors_count > 10 and self.messages_processed > 0:
            error_rate = self.errors_count / (self.messages_processed + self.errors_count)
            if error_rate > 0.5:  # 50% error rate
                self.is_healthy = False
    
    def get_status(self) -> Dict[str, Any]:
        """Get health status."""
        uptime = datetime.now() - self.start_time
        return {
            "healthy": self.is_healthy,
            "uptime_seconds": int(uptime.total_seconds()),
            "messages_processed": self.messages_processed,
            "errors_count": self.errors_count,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "last_error": self.last_error
        }

class RAGWorker:
    """Enhanced RAG worker with health monitoring and graceful shutdown."""
    
    def __init__(
        self,
        environment: str = "dev",
        result_store: Optional[ResultStore] = None,
        inference_adapter: Optional[InferenceAdapter] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        metrics: Optional[MetricsCollector] = None,
        tenant_engine: Optional[TenantPolicyEngine] = None,
        audit_log: Optional[AuditLog] = None,
    ):
        self.config = get_config(environment)
        self.health = WorkerHealth()
        self.logger = self._setup_logging()
        self.session = boto3.Session(region_name=self.config.aws_region)
        self.sqs = self.session.client("sqs")
        self.ssm = self.session.client("ssm")
        self.ai_client: Optional[OpenAI] = None
        self.result_store: ResultStore = result_store or self._initialize_result_store()
        self.metrics = metrics or MetricsCollector()
        self.tenant_engine = tenant_engine
        self.audit: AuditLog = audit_log or NullAuditLog()
        self.request_ttl = RequestTTL(max_age_seconds=self.config.request_ttl_seconds)
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            CircuitBreakerPolicy(
                failure_threshold=self.config.circuit_breaker_failure_threshold,
                recovery_timeout_seconds=self.config.circuit_breaker_recovery_timeout_seconds,
            ),
            metrics=self.metrics,
        )
        self.inference_adapter: Optional[InferenceAdapter] = inference_adapter
        self.latency_tracker = LatencyTracker(LatencyPolicy(
            window_size=self.config.latency_window_size,
            p95_threshold_ms=self.config.latency_p95_threshold_ms,
            min_samples=self.config.latency_min_samples,
        ))
        self.router = self._initialize_model_router()
        self.batcher = self._initialize_dynamic_batcher()
        self.gpu_scheduler = self._initialize_gpu_scheduler()
        self._setup_signal_handlers()
        self._initialize_ai_client()
        if self.inference_adapter is None:
            self._initialize_inference_adapter()
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging with structured JSON output."""
        logger = logging.getLogger("RAG-Worker")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()

        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.propagate = False

        # CloudWatch handler (optional, uses same structured format)
        try:
            if watchtower is None:
                raise ImportError("watchtower is not installed")
            cw_handler = watchtower.CloudWatchLogHandler(
                log_group_name=self.config.log_group_name,
                log_stream_name=self.config.log_stream_name,
                boto3_client=self.session.client("logs")
            )
            cw_handler.setFormatter(StructuredFormatter())
            logger.addHandler(cw_handler)
        except Exception:
            pass

        return logger
    
    def _setup_signal_handlers(self):
        """Setup graceful shutdown signal handlers."""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            shutdown_event.set()
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    def _initialize_result_store(self) -> ResultStore:
        """Initialize result store from config. Uses DynamoDB in deployed mode."""
        table_name = getattr(self.config, "result_store_table_name", "")
        if table_name and table_name != "inference-results":
            # Deployed mode: use DynamoDB
            return DynamoResultStore(
                table_name=table_name,
                region=self.config.aws_region,
                ttl_days=self.config.result_store_ttl_days,
            )
        return InMemoryResultStore()
    
    def _initialize_model_router(self) -> ModelRouter:
        """Initialize deterministic model routing policy from config."""
        def config_str(name: str, default: str) -> str:
            value = getattr(self.config, name, None)
            return value if isinstance(value, str) and value else default

        def config_int(name: str, default: int) -> int:
            value = getattr(self.config, name, default)
            return value if isinstance(value, int) else default

        default_model = config_str("vllm_model", "local-default-model")
        small_model = config_str("vllm_small_model", default_model)
        large_model = config_str("vllm_large_model", default_model)
        profiles = [
            ModelProfile(
                name=small_model,
                max_context_tokens=config_int("vllm_small_context_tokens", 4096),
                priority=10,
                description="Lower latency model for simple requests",
            )
        ]
        if large_model != small_model:
            profiles.append(
                ModelProfile(
                    name=large_model,
                    max_context_tokens=config_int("vllm_large_context_tokens", 32768),
                    priority=20,
                    description="Higher capacity model for complex or long context requests",
                )
            )
        return ModelRouter(profiles=profiles, default_model=small_model, latency_tracker=self.latency_tracker)

    def _initialize_dynamic_batcher(self) -> DynamicBatcher:
        """Initialize dynamic batching policy from worker config."""
        def config_int(name: str, default: int) -> int:
            value = getattr(self.config, name, default)
            return value if isinstance(value, int) else default

        return DynamicBatcher(
            BatchingPolicy(
                max_batch_size=config_int("worker_batch_size", 4),
                max_batch_tokens=config_int("worker_batch_token_budget", 12000),
            )
        )


    def _initialize_gpu_scheduler(self) -> GPUScheduler:
        """Initialize GPU-aware scheduling policy from worker config."""
        def config_str(name: str, default: str) -> str:
            value = getattr(self.config, name, None)
            return value if isinstance(value, str) and value else default

        default_model = config_str("vllm_model", "local-default-model")
        small_model = config_str("vllm_small_model", default_model)
        large_model = config_str("vllm_large_model", default_model)
        profiles = {
            small_model: ModelResourceProfile(
                model_name=small_model,
                required_memory_mb=self.config.gpu_small_model_memory_mb,
                expected_utilization_percent=25.0,
                max_batch_size=self.config.gpu_small_model_max_batch_size,
            )
        }
        if large_model != small_model:
            profiles[large_model] = ModelResourceProfile(
                model_name=large_model,
                required_memory_mb=self.config.gpu_large_model_memory_mb,
                expected_utilization_percent=55.0,
                max_batch_size=self.config.gpu_large_model_max_batch_size,
            )
        return GPUScheduler(
            model_profiles=profiles,
            policy=SchedulingPolicy(
                memory_reserve_mb=self.config.gpu_memory_reserve_mb,
                max_gpu_utilization_percent=self.config.gpu_max_utilization_percent,
            ),
        )

    def get_gpu_snapshots(self) -> list[GPUDeviceSnapshot]:
        """Return current GPU capacity observations.

        This module intentionally starts with a deterministic local snapshot that
        can be fed by environment/config. A later production module can replace
        this with NVML, Kubernetes device plugin data, or a fleet inventory API
        without changing scheduling policy.
        """
        return [
            GPUDeviceSnapshot(
                device_id=self.config.gpu_device_id,
                name=self.config.gpu_device_name,
                total_memory_mb=self.config.gpu_device_memory_mb,
                used_memory_mb=self.config.gpu_device_used_memory_mb,
                utilization_percent=self.config.gpu_device_utilization_percent,
            )
        ]

    def _initialize_inference_adapter(self) -> None:
        """Initialize the vLLM batch adapter from config."""
        try:
            self.inference_adapter = VllmBatchAdapter(base_url=self.config.vllm_url)
            self.logger.info("vLLM batch adapter initialized")
        except ImportError:
            self.logger.warning("openai not installed, inference adapter unavailable")

    def _initialize_ai_client(self):
        """Initialize AI client with retry logic."""
        max_retries = self.config.worker_max_retries
        backoff = 1
        
        for attempt in range(max_retries):
            try:
                if OpenAI is None:
                    raise ImportError("openai is not installed")
                self.ai_client = OpenAI(
                    base_url=self.config.vllm_url,
                    api_key="local-airgap",
                    timeout=30.0
                )
                # Test connection
                self.ai_client.models.list()
                self.logger.info("AI client initialized successfully")
                return
            except Exception as e:
                self.logger.warning(f"AI client initialization attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(backoff)
                    backoff *= self.config.worker_backoff_factor
                else:
                    self.logger.error("Failed to initialize AI client after all retries")
                    raise

    def check_kill_switch(self) -> bool:
        """Check if processing is enabled via SSM parameter."""
        try:
            response = self.ssm.get_parameter(Name=self.config.ssm_kill_switch)
            return response['Parameter']['Value'].lower() == 'true'
        except ClientError as e:
            self.logger.error(f"Failed to read kill switch: {e}")
            self.health.record_error(f"SSM error: {e}")
            return False
    
    def perform_inference(self, task: RAGTask) -> Optional[str]:
        """Perform inference with error handling and retries."""
        if not self.ai_client:
            self.logger.error("AI client not initialized")
            return None
        
        max_retries = self.config.worker_max_retries
        backoff = 1
        
        for attempt in range(max_retries):
            try:
                routing_decision = self.router.route(
                    InferenceRequest(
                        prompt=task.prompt,
                        context=task.context,
                        event_type=task.event_type,
                        priority=task.priority,
                        requested_model=task.requested_model,
                    )
                )
                self.logger.info(
                    "Processing %s with model=%s reason=%s estimated_tokens=%s (attempt %s)",
                    task.event_type,
                    routing_decision.model_name,
                    routing_decision.reason.value,
                    routing_decision.estimated_tokens,
                    attempt + 1,
                )
                
                response = self.ai_client.chat.completions.create(
                    model=routing_decision.model_name,
                    messages=[
                        {"role": "system", "content": f"Use ONLY the following context: {task.context}"},
                        {"role": "user", "content": task.prompt}
                    ],
                    temperature=self.config.vllm_temperature,
                    max_tokens=self.config.vllm_max_tokens
                )
                
                result = response.choices[0].message.content
                self.health.record_success()
                return result
                
            except Exception as e:
                self.logger.warning(f"Inference attempt {attempt + 1} failed: {e}")
                self.health.record_error(f"Inference error: {e}")
                
                if attempt < max_retries - 1:
                    time.sleep(backoff)
                    backoff *= self.config.worker_backoff_factor
        
        self.logger.error(f"Inference failed after {max_retries} attempts")
        return None
    
    def task_to_batch_candidate(self, task: RAGTask) -> BatchCandidate:
        """Convert a task into a batch candidate using the current routing policy."""
        routing_decision = self.router.route(
            InferenceRequest(
                prompt=task.prompt,
                context=task.context,
                event_type=task.event_type,
                priority=task.priority,
                requested_model=task.requested_model,
            )
        )
        return BatchCandidate(
            request_id=task.event_id or f"task-{int(time.time() * 1000)}",
            prompt=task.prompt,
            context=task.context,
            model_name=routing_decision.model_name,
            event_type=task.event_type,
            priority=task.priority,
            estimated_tokens=routing_decision.estimated_tokens,
            batchable=routing_decision.batchable,
            raw_payload=task.model_dump(),
        )

    def perform_inference_with_model(self, task: RAGTask, model_name: str) -> Optional[str]:
        """Perform inference with an already selected model.

        Batch processing makes the routing decision once before execution. This
        method preserves the retry behavior while avoiding route drift inside a
        batch.
        """
        if not self.ai_client:
            self.logger.error("AI client not initialized")
            return None

        max_retries = self.config.worker_max_retries
        backoff = 1

        for attempt in range(max_retries):
            try:
                self.logger.info(
                    "Processing %s with preselected model=%s (attempt %s)",
                    task.event_type,
                    model_name,
                    attempt + 1,
                )
                response = self.ai_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": f"Use ONLY the following context: {task.context}"},
                        {"role": "user", "content": task.prompt}
                    ],
                    temperature=self.config.vllm_temperature,
                    max_tokens=self.config.vllm_max_tokens
                )
                result = response.choices[0].message.content
                self.health.record_success()
                return result
            except Exception as e:
                self.logger.warning(f"Inference attempt {attempt + 1} failed: {e}")
                self.health.record_error(f"Inference error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(backoff)
                    backoff *= self.config.worker_backoff_factor

        self.logger.error(f"Inference failed after {max_retries} attempts")
        return None

    def _release_tenant(self, metadata: Dict[str, Any]) -> None:
        """Release tenant concurrency slot on request completion."""
        if self.tenant_engine is None:
            return
        tenant_id = TenantPolicyEngine.extract_tenant(metadata)
        self.tenant_engine.release(tenant_id)

    def process_batch(self, batch: InferenceBatch, messages_by_request_id: Dict[str, Dict[str, Any]]) -> bool:
        """Process a batch using the circuit breaker and inference adapter."""
        self.logger.info(
            "Processing batch_id=%s model=%s size=%s reason=%s estimated_tokens=%s",
            batch.batch_id,
            batch.model_name,
            batch.size,
            batch.reason,
            batch.total_estimated_tokens,
        )
        if self.config.gpu_scheduling_enabled:
            scheduling_decision = self.gpu_scheduler.schedule(
                model_name=batch.model_name,
                devices=self.get_gpu_snapshots(),
                batch_size=batch.size,
            )
            self.metrics.record_scheduling_decision(
                batch_id=batch.batch_id, model=batch.model_name,
                scheduled=scheduling_decision.scheduled,
                device_id=scheduling_decision.device_id,
                reason=scheduling_decision.reason,
            )
            if not scheduling_decision.scheduled:
                self.logger.warning(
                    "Deferring batch_id=%s model=%s reason=%s available_memory_mb=%s required_memory_mb=%s",
                    batch.batch_id,
                    batch.model_name,
                    scheduling_decision.reason,
                    scheduling_decision.available_memory_mb,
                    scheduling_decision.required_memory_mb,
                )
                self.health.record_error(f"GPU scheduling deferred: {scheduling_decision.reason}")
                return False
            self.logger.info(
                "Scheduled batch_id=%s model=%s on device=%s reason=%s",
                batch.batch_id,
                batch.model_name,
                scheduling_decision.device_id,
                scheduling_decision.reason,
            )

        # Circuit breaker gate
        if not self.circuit_breaker.allow_request():
            self.logger.warning(
                "Circuit breaker OPEN — fast-failing batch_id=%s model=%s",
                batch.batch_id, batch.model_name,
            )
            now = datetime.now(timezone.utc).isoformat()
            for candidate in batch.candidates:
                raw = candidate.raw_payload
                self.result_store.put(InferenceResult(
                    request_id=candidate.request_id,
                    status=RequestStatus.FAILED,
                    accepted_at=raw.get("timestamp", now),
                    completed_at=now,
                    model_name=batch.model_name,
                    error="Circuit breaker open — downstream unavailable",
                ))
                self.metrics.record_inference_failed(
                    request_id=candidate.request_id, model=batch.model_name,
                    error="circuit_breaker_open",
                )
                self._release_tenant(raw.get("metadata", {}))
            return False

        # TTL check: expire requests that have been queued too long
        now = datetime.now(timezone.utc).isoformat()
        live_candidates = []
        for candidate in batch.candidates:
            raw = candidate.raw_payload
            accepted_at = raw.get("timestamp", "")
            if self.request_ttl.is_expired(accepted_at):
                self.result_store.put(InferenceResult(
                    request_id=candidate.request_id,
                    status=RequestStatus.FAILED,
                    accepted_at=accepted_at,
                    completed_at=now,
                    model_name=batch.model_name,
                    error=f"Request expired (TTL {self.request_ttl.max_age_seconds}s)",
                ))
                self.metrics.record_inference_failed(
                    request_id=candidate.request_id, model=batch.model_name, error="ttl_expired",
                )
                self.audit.record(AuditEvent(
                    request_id=candidate.request_id, event="expired", component="worker",
                    detail={"max_age_seconds": self.request_ttl.max_age_seconds},
                ))
                self._release_tenant(raw.get("metadata", {}))
                # Delete from queue so it doesn't reappear
                message = messages_by_request_id[candidate.request_id]
                self.sqs.delete_message(
                    QueueUrl=self.config.queue_url, ReceiptHandle=message["ReceiptHandle"],
                )
                self.logger.info("Request expired request_id=%s", candidate.request_id)
            else:
                live_candidates.append(candidate)

        if not live_candidates:
            return True  # All expired, nothing to infer

        # Build adapter inputs
        inputs = [
            InferenceInput(
                request_id=c.request_id,
                prompt=c.prompt,
                context=c.context,
            )
            for c in live_candidates
        ]

        # Mark all as processing
        now = datetime.now(timezone.utc).isoformat()
        for candidate in live_candidates:
            raw = candidate.raw_payload
            self.result_store.put(InferenceResult(
                request_id=candidate.request_id,
                status=RequestStatus.PROCESSING,
                accepted_at=raw.get("timestamp", now),
                model_name=batch.model_name,
            ))
            self.metrics.record_inference_started(
                request_id=candidate.request_id, model=batch.model_name, batch_id=batch.batch_id,
            )

        # Execute batch inference via adapter
        outputs = self.inference_adapter.infer_batch(model=batch.model_name, inputs=inputs)

        all_succeeded = True
        for output in outputs:
            candidate = next(c for c in live_candidates if c.request_id == output.request_id)
            raw = candidate.raw_payload
            metadata = raw.get("metadata", {})

            if output.success:
                self.circuit_breaker.record_success()
                self.result_store.put(InferenceResult(
                    request_id=output.request_id,
                    status=RequestStatus.COMPLETED,
                    accepted_at=raw.get("timestamp", now),
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    model_name=batch.model_name,
                    result=output.text,
                ))
                self.metrics.record_inference_completed(
                    request_id=output.request_id, model=batch.model_name, duration_ms=output.duration_ms,
                )
                self.latency_tracker.record(batch.model_name, output.duration_ms)
                message = messages_by_request_id[output.request_id]
                self.sqs.delete_message(
                    QueueUrl=self.config.queue_url,
                    ReceiptHandle=message["ReceiptHandle"],
                )
                self.health.record_success()
                self.logger.info("Completed request_id=%s in batch %s", output.request_id, batch.batch_id)
                self.audit.record(AuditEvent(
                    request_id=output.request_id, event="completed", component="worker",
                    detail={"model": batch.model_name, "batch_id": batch.batch_id, "duration_ms": output.duration_ms},
                ))
            else:
                self.circuit_breaker.record_failure()
                self.result_store.put(InferenceResult(
                    request_id=output.request_id,
                    status=RequestStatus.FAILED,
                    accepted_at=raw.get("timestamp", now),
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    model_name=batch.model_name,
                    error=output.error or "Inference failed",
                ))
                self.metrics.record_inference_failed(
                    request_id=output.request_id, model=batch.model_name, error=output.error or "unknown",
                )
                all_succeeded = False
                self.health.record_error(f"Inference failed: {output.error}")
                self.logger.error("Failed request_id=%s in batch %s: %s", output.request_id, batch.batch_id, output.error)
                self.audit.record(AuditEvent(
                    request_id=output.request_id, event="failed", component="worker",
                    detail={"model": batch.model_name, "batch_id": batch.batch_id, "error": output.error},
                ))

            self._release_tenant(metadata)

        return all_succeeded

    def process_messages(self, messages: List[Dict[str, Any]]) -> bool:
        """Process multiple SQS messages through the dynamic batcher."""
        candidates: List[BatchCandidate] = []
        messages_by_request_id: Dict[str, Dict[str, Any]] = {}

        for message in messages:
            try:
                body = json.loads(message["Body"])
                task = RAGTask(**body)
                candidate = self.task_to_batch_candidate(task)
                candidates.append(candidate)
                messages_by_request_id[candidate.request_id] = message
            except Exception as e:
                self.logger.error(f"Message normalization failed before batching: {e}")
                self.health.record_error(f"Batch normalization error: {e}")

        if not candidates:
            return False

        batches = self.batcher.build_batches(candidates)
        results = [self.process_batch(batch, messages_by_request_id) for batch in batches]
        return all(results)

    def process_message(self, message: Dict[str, Any]) -> bool:
        """Process a single SQS message."""
        try:
            body = json.loads(message["Body"])
            task = RAGTask(**body)
            
            answer = self.perform_inference(task)
            
            if answer:
                # Delete message from queue
                self.sqs.delete_message(
                    QueueUrl=self.config.queue_url,
                    ReceiptHandle=message["ReceiptHandle"]
                )
                
                self.logger.info("Message processed successfully")
                print(f"\n--- LLM RESPONSE ---\n{answer}\n--------------------\n")
                return True
            else:
                self.logger.error("Inference failed, message remains in queue")
                return False
                
        except Exception as e:
            self.logger.error(f"Message processing failed: {e}")
            self.health.record_error(f"Processing error: {e}")
            return False
    
    def health_check_loop(self):
        """Background health check loop."""
        while not shutdown_event.is_set():
            try:
                self.health.heartbeat()
                
                # Log health status periodically
                if self.config.health_check_enabled:
                    status = self.health.get_status()
                    self.logger.debug(f"Health status: {status}")
                
                # Check if we can reach AWS services
                try:
                    self.sqs.get_queue_attributes(
                        QueueUrl=self.config.queue_url,
                        AttributeNames=['ApproximateNumberOfMessages']
                    )
                except Exception as e:
                    self.logger.warning(f"AWS connectivity check failed: {e}")
                    self.health.record_error(f"AWS connectivity: {e}")
                
                shutdown_event.wait(self.config.worker_health_check_interval)
                
            except Exception as e:
                self.logger.error(f"Health check error: {e}")
                shutdown_event.wait(self.config.worker_health_check_interval)
    
    def run(self):
        """Main worker loop with graceful shutdown."""
        self.logger.info(f"RAG Worker starting (environment: {self.config.aws_region})")
        self.logger.info(f"Queue URL: {self.config.queue_url}")
        self.logger.info(f"Kill switch: {self.config.ssm_kill_switch}")
        
        # Start health check thread
        if self.config.health_check_enabled:
            health_thread = threading.Thread(target=self.health_check_loop, daemon=True)
            health_thread.start()
        
        try:
            while not shutdown_event.is_set():
                try:
                    # Check kill switch
                    if not self.check_kill_switch():
                        self.logger.warning("Processing disabled by kill switch")
                        shutdown_event.wait(10)
                        continue
                    
                    # Poll SQS for messages
                    response = self.sqs.receive_message(
                        QueueUrl=self.config.queue_url,
                        MaxNumberOfMessages=self.batcher.policy.max_batch_size,
                        WaitTimeSeconds=min(self.config.worker_poll_interval, 20)
                    )
                    
                    messages = response.get("Messages", [])
                    
                    if not messages:
                        # No messages, continue polling
                        continue
                    
                    # Process messages through the dynamic batching layer.
                    if not shutdown_event.is_set():
                        self.process_messages(messages)
                    
                except KeyboardInterrupt:
                    self.logger.info("Keyboard interrupt received")
                    break
                except Exception as e:
                    self.logger.error(f"Unexpected error in main loop: {e}")
                    self.health.record_error(f"Main loop error: {e}")
                    # Brief pause before retrying
                    shutdown_event.wait(5)
        
        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            raise
        finally:
            self.logger.info("Worker shutting down gracefully")
            self._cleanup()
    
    def _cleanup(self):
        """Cleanup resources on shutdown."""
        try:
            # Log final health status
            final_status = self.health.get_status()
            self.logger.info(f"Final health status: {final_status}")
            
            # Close AI client if needed
            if hasattr(self.ai_client, 'close'):
                self.ai_client.close()
            
            self.logger.info("Cleanup completed")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

class RAGTask(BaseModel):
    """RAG task model with validation."""
    prompt: str
    context: str
    event_type: str = "general_inference"
    event_id: Optional[str] = None
    timestamp: Optional[str] = None
    priority: int = 5
    requested_model: Optional[str] = None

def main():
    """Main entry point."""
    import os
    
    # Get environment from command line or environment variable
    environment = os.getenv("ENVIRONMENT", "dev")
    if len(sys.argv) > 1:
        environment = sys.argv[1]
    
    try:
        worker = RAGWorker(environment)
        worker.run()
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()