"""
Inference Gateway API for the secure inference platform.

The gateway is intentionally thin. It does not run model inference itself.
Its job is to normalize external requests, make the routing decision visible,
and enqueue work for the isolated worker fleet. This keeps the public control
plane separate from the private execution plane, which is a core pattern for
secure and air gapped AI systems.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional
from uuid import uuid4

import boto3
from fastapi import FastAPI, HTTPException, Request as FastAPIRequest, status
from pydantic import BaseModel, Field

from ai_inference.core.audit import AuditEvent, AuditLog, InMemoryAuditLog, NullAuditLog
from ai_inference.core.logging import get_logger
from ai_inference.core.metrics import MetricsCollector
from ai_inference.core.result_store import InMemoryResultStore, InferenceResult, RequestStatus, ResultStore
from ai_inference.gateway.admission import AdmissionController, AdmissionDecision, AdmissionPolicy, SystemLoad
from ai_inference.gateway.auth import AuthProvider, AuthResult, NoAuthProvider
from ai_inference.gateway.tenant import TenantPolicyEngine
from ai_inference.inference.router import InferenceRequest, ModelProfile, ModelRouter


class GatewaySettings(BaseModel):
    """Runtime settings for the gateway."""

    queue_url: str = Field(default="", description="SQS queue URL used to hand work to inference workers")
    aws_region: str = Field(default="us-east-1")
    default_model: str = Field(default="llama-3.1-8b")
    small_model: Optional[str] = Field(default=None)
    large_model: Optional[str] = Field(default=None)
    small_context_tokens: int = Field(default=4096, ge=512)
    large_context_tokens: int = Field(default=32768, ge=512)

    @classmethod
    def from_env(cls) -> "GatewaySettings":
        return cls(
            queue_url=os.getenv("INFERENCE_QUEUE_URL") or os.getenv("QUEUE_URL") or "",
            aws_region=os.getenv("AWS_REGION", "us-east-1"),
            default_model=os.getenv("VLLM_MODEL", "llama-3.1-8b"),
            small_model=os.getenv("VLLM_SMALL_MODEL") or None,
            large_model=os.getenv("VLLM_LARGE_MODEL") or None,
            small_context_tokens=int(os.getenv("VLLM_SMALL_CONTEXT_TOKENS", "4096")),
            large_context_tokens=int(os.getenv("VLLM_LARGE_CONTEXT_TOKENS", "32768")),
        )


class InferenceGatewayRequest(BaseModel):
    """Client facing inference request."""

    prompt: str = Field(..., min_length=1)
    context: str = ""
    event_type: str = "general_inference"
    priority: int = Field(default=5, ge=1, le=10)
    requested_model: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None


class RoutingDecisionResponse(BaseModel):
    model_name: str
    reason: str
    estimated_tokens: int
    batchable: bool
    notes: str


class InferenceGatewayResponse(BaseModel):
    request_id: str
    status: str
    accepted_at: str
    routing: RoutingDecisionResponse
    idempotency_key: str


class InferenceResultResponse(BaseModel):
    request_id: str
    status: str
    accepted_at: str
    completed_at: Optional[str] = None
    model_name: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None


class QueuePublisher:
    """Small adapter around SQS to keep the API testable."""

    def __init__(self, queue_url: str, aws_region: str):
        self.queue_url = queue_url
        self.client = boto3.client("sqs", region_name=aws_region)

    def publish(self, payload: Mapping[str, Any]) -> None:
        if not self.queue_url:
            raise RuntimeError("Queue URL is not configured")
        self.client.send_message(QueueUrl=self.queue_url, MessageBody=json.dumps(payload))


def build_router(settings: GatewaySettings) -> ModelRouter:
    small_model = settings.small_model or settings.default_model
    large_model = settings.large_model or settings.default_model
    profiles = [
        ModelProfile(
            name=small_model,
            max_context_tokens=settings.small_context_tokens,
            priority=10,
            description="Lower latency model for simple requests",
        )
    ]
    if large_model != small_model:
        profiles.append(
            ModelProfile(
                name=large_model,
                max_context_tokens=settings.large_context_tokens,
                priority=20,
                description="Higher capacity model for complex or long context requests",
            )
        )
    return ModelRouter(profiles=profiles, default_model=small_model)


def derive_idempotency_key(request: InferenceGatewayRequest) -> str:
    if request.idempotency_key:
        return request.idempotency_key
    stable_payload = {
        "prompt": request.prompt,
        "context": request.context,
        "event_type": request.event_type,
        "priority": request.priority,
        "requested_model": request.requested_model,
        "metadata": request.metadata,
    }
    encoded = json.dumps(stable_payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_app(
    settings: Optional[GatewaySettings] = None,
    publisher: Optional[Any] = None,
    router: Optional[ModelRouter] = None,
    result_store: Optional[ResultStore] = None,
    metrics: Optional[MetricsCollector] = None,
    admission: Optional[AdmissionController] = None,
    tenant_engine: Optional[TenantPolicyEngine] = None,
    audit_log: Optional[AuditLog] = None,
    auth_provider: Optional[AuthProvider] = None,
) -> FastAPI:
    settings = settings or GatewaySettings.from_env()
    router = router or build_router(settings)
    publisher = publisher or QueuePublisher(settings.queue_url, settings.aws_region)
    result_store = result_store or InMemoryResultStore()
    metrics = metrics or MetricsCollector()
    admission = admission or AdmissionController(metrics=metrics)
    tenant_engine = tenant_engine or TenantPolicyEngine(metrics=metrics)
    audit = audit_log or NullAuditLog()
    auth = auth_provider or NoAuthProvider()
    log = get_logger("gateway")

    app = FastAPI(
        title="Secure Inference Gateway",
        version="0.2.0",
        description="Control-plane API for submitting secure inference work to isolated workers.",
    )

    @app.get("/health")
    def health() -> Dict[str, Any]:
        pending = result_store.scan_by_status(RequestStatus.PENDING)
        processing = result_store.scan_by_status(RequestStatus.PROCESSING)
        return {
            "status": "ok",
            "component": "inference_gateway",
            "queue_configured": bool(settings.queue_url),
            "models": list(router.profiles.keys()),
            "requests": {
                "pending": len(pending),
                "processing": len(processing),
            },
            "admission": {
                "enabled": admission.policy.enabled,
                "max_queue_depth": admission.policy.max_queue_depth,
            },
        }

    @app.get("/v1/audit/{request_id}")
    def get_audit_trail(request_id: str) -> Dict[str, Any]:
        trail = audit.get_trail(request_id)
        if not trail:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No audit trail found")
        return {
            "request_id": request_id,
            "events": [e.to_dict() for e in trail],
        }

    @app.post(
        "/v1/inference",
        response_model=InferenceGatewayResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def submit_inference(request: InferenceGatewayRequest, raw_request: FastAPIRequest) -> InferenceGatewayResponse:
        # Authentication check
        auth_result = auth.authenticate(raw_request.headers.get("authorization"))
        if not auth_result.authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=auth_result.reason,
            )

        # Admission control check
        load = SystemLoad(
            pending_count=len(result_store.scan_by_status(RequestStatus.PENDING)),
            processing_count=len(result_store.scan_by_status(RequestStatus.PROCESSING)),
        )
        admission_result = admission.check(load)
        if admission_result.decision not in (AdmissionDecision.ADMIT, AdmissionDecision.DISABLED):
            headers = {}
            if admission_result.retry_after_seconds:
                headers["Retry-After"] = str(admission_result.retry_after_seconds)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=admission_result.reason,
                headers=headers,
            )

        # Tenant identity: prefer auth-derived tenant, fall back to metadata
        tenant_id = auth_result.tenant_id or TenantPolicyEngine.extract_tenant(request.metadata)
        tenant_result = tenant_engine.check(tenant_id, request.priority)
        if not tenant_result.allowed:
            headers = {}
            if tenant_result.retry_after_seconds:
                headers["Retry-After"] = str(tenant_result.retry_after_seconds)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=tenant_result.reason,
                headers=headers,
            )

        routing_decision = router.route(
            InferenceRequest(
                prompt=request.prompt,
                context=request.context,
                event_type=request.event_type,
                priority=request.priority,
                requested_model=request.requested_model,
                metadata=request.metadata,
            )
        )
        request_id = str(uuid4())
        accepted_at = datetime.now(timezone.utc).isoformat()
        idempotency_key = derive_idempotency_key(request)

        queue_payload = {
            "event_id": request_id,
            "timestamp": accepted_at,
            "prompt": request.prompt,
            "context": request.context,
            "event_type": request.event_type,
            "priority": request.priority,
            "requested_model": routing_decision.model_name,
            "metadata": request.metadata,
            "routing": {
                "model_name": routing_decision.model_name,
                "reason": routing_decision.reason.value,
                "estimated_tokens": routing_decision.estimated_tokens,
                "batchable": routing_decision.batchable,
                "notes": routing_decision.notes,
            },
            "idempotency_key": idempotency_key,
        }

        try:
            publisher.publish(queue_payload)
        except Exception as exc:
            log.error("queue publish failed", request_id=request_id, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Unable to enqueue inference request: {exc}",
            ) from exc

        result_store.put(InferenceResult(
            request_id=request_id,
            status=RequestStatus.PENDING,
            accepted_at=accepted_at,
            model_name=routing_decision.model_name,
        ))

        log.info(
            "request accepted",
            request_id=request_id,
            model=routing_decision.model_name,
            reason=routing_decision.reason.value,
            estimated_tokens=routing_decision.estimated_tokens,
            event_type=request.event_type,
        )

        metrics.record_request_accepted(
            request_id=request_id,
            model=routing_decision.model_name,
            event_type=request.event_type,
            estimated_tokens=routing_decision.estimated_tokens,
        )

        audit.record(AuditEvent(
            request_id=request_id,
            event="accepted",
            component="gateway",
            detail={
                "model": routing_decision.model_name,
                "reason": routing_decision.reason.value,
                "estimated_tokens": routing_decision.estimated_tokens,
                "event_type": request.event_type,
                "tenant": tenant_id,
            },
        ))

        return InferenceGatewayResponse(
            request_id=request_id,
            status="accepted",
            accepted_at=accepted_at,
            routing=RoutingDecisionResponse(**queue_payload["routing"]),
            idempotency_key=idempotency_key,
        )

    @app.get(
        "/v1/inference/{request_id}",
        response_model=InferenceResultResponse,
    )
    def get_inference_result(request_id: str) -> InferenceResultResponse:
        record = result_store.get(request_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
        return InferenceResultResponse(**record.model_dump())

    # Expose store for worker integration
    app.state.result_store = result_store
    app.state.audit_log = audit

    return app


app = create_app()
