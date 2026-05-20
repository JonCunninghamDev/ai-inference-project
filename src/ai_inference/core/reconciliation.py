"""
Reconciliation engine for the secure inference platform.

Scans the result store for requests stuck in non-terminal states and
applies configurable recovery strategies:

    - Dry Run:  log what would happen, change nothing
    - Heal:     resubmit stale requests or mark them failed
    - Bedrock:  analyze failure patterns with Claude for operator context
    - SNS:      notify operators only after all automated recovery is exhausted

All modes default to disabled. Enable them explicitly via ReconciliationConfig.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Protocol

from pydantic import BaseModel

from ai_inference.core.logging import get_logger
from ai_inference.core.result_store import InferenceResult, RequestStatus, ResultStore

logger = get_logger("reconciliation")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class ReconciliationConfig:
    """Controls reconciliation behavior. All recovery modes default to off."""

    # Timing
    stale_pending_timeout_seconds: int = 120
    stale_processing_timeout_seconds: int = 300
    max_heal_retries: int = 3

    # Modes
    dry_run_enabled: bool = False
    heal_enabled: bool = False
    bedrock_analysis_enabled: bool = False
    sns_notification_enabled: bool = False

    # Bedrock settings (only used when bedrock_analysis_enabled=True)
    bedrock_model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"
    bedrock_region: str = "us-east-1"

    # SNS settings (only used when sns_notification_enabled=True)
    sns_topic_arn: str = ""
    sns_region: str = "us-east-1"


# ---------------------------------------------------------------------------
# Action types produced by reconciliation
# ---------------------------------------------------------------------------


class ReconciliationAction(str, Enum):
    RESUBMIT = "resubmit"
    MARK_FAILED = "mark_failed"
    NOTIFY = "notify"
    SKIP = "skip"


@dataclass
class ReconciliationEvent:
    """A single reconciliation decision."""

    request_id: str
    previous_status: RequestStatus
    action: ReconciliationAction
    reason: str
    dry_run: bool = False
    bedrock_analysis: Optional[str] = None
    notified: bool = False


# ---------------------------------------------------------------------------
# Publisher protocol (reuse pattern from gateway)
# ---------------------------------------------------------------------------


class QueuePublisher(Protocol):
    def publish(self, payload: Mapping[str, Any]) -> None: ...


class SnsPublisher(Protocol):
    def publish_failure(self, event: ReconciliationEvent, result: InferenceResult) -> None: ...


# ---------------------------------------------------------------------------
# Default SNS publisher
# ---------------------------------------------------------------------------


class AwsSnsPublisher:
    """Publishes unrecoverable failure notifications to SNS."""

    def __init__(self, topic_arn: str, region: str = "us-east-1") -> None:
        import boto3
        self._client = boto3.client("sns", region_name=region)
        self._topic_arn = topic_arn

    def publish_failure(self, event: ReconciliationEvent, result: InferenceResult) -> None:
        message = {
            "request_id": result.request_id,
            "status": result.status.value,
            "accepted_at": result.accepted_at,
            "error": result.error,
            "reconciliation_action": event.action.value,
            "reconciliation_reason": event.reason,
            "bedrock_analysis": event.bedrock_analysis,
        }
        self._client.publish(
            TopicArn=self._topic_arn,
            Subject=f"Inference failure: {result.request_id[:8]}",
            Message=json.dumps(message, indent=2),
            MessageAttributes={
                "event_type": {"DataType": "String", "StringValue": "reconciliation_failure"},
            },
        )


# ---------------------------------------------------------------------------
# Bedrock failure analyzer
# ---------------------------------------------------------------------------


class BedrockFailureAnalyzer:
    """Uses Bedrock Claude to produce a structured explanation of why a request failed."""

    def __init__(self, model_id: str, region: str = "us-east-1") -> None:
        import boto3
        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._model_id = model_id

    def analyze(self, result: InferenceResult) -> str:
        prompt = (
            "You are an inference platform reliability engineer. "
            "A request failed to complete. Analyze the following record and provide "
            "a brief structured explanation of likely root cause and recommended operator action.\n\n"
            f"Request ID: {result.request_id}\n"
            f"Status: {result.status.value}\n"
            f"Accepted at: {result.accepted_at}\n"
            f"Completed at: {result.completed_at or 'never'}\n"
            f"Model: {result.model_name or 'unknown'}\n"
            f"Error: {result.error or 'none recorded'}\n"
        )
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 256,
            "messages": [{"role": "user", "content": prompt}],
        })
        response = self._client.invoke_model(modelId=self._model_id, body=body)
        response_body = json.loads(response["body"].read())
        return response_body["content"][0]["text"]


# ---------------------------------------------------------------------------
# Reconciliation engine
# ---------------------------------------------------------------------------


class ReconciliationEngine:
    """Scans for stale requests and applies recovery strategies."""

    def __init__(
        self,
        config: ReconciliationConfig,
        result_store: ResultStore,
        queue_publisher: Optional[QueuePublisher] = None,
        sns_publisher: Optional[SnsPublisher] = None,
        bedrock_analyzer: Optional[BedrockFailureAnalyzer] = None,
    ) -> None:
        self.config = config
        self.result_store = result_store
        self.queue_publisher = queue_publisher
        self.sns_publisher = sns_publisher
        self.bedrock_analyzer = bedrock_analyzer

        # Initialize optional components based on config
        if config.sns_notification_enabled and not sns_publisher and config.sns_topic_arn:
            self.sns_publisher = AwsSnsPublisher(config.sns_topic_arn, config.sns_region)
        if config.bedrock_analysis_enabled and not bedrock_analyzer:
            self.bedrock_analyzer = BedrockFailureAnalyzer(config.bedrock_model_id, config.bedrock_region)

    def _is_stale(self, result: InferenceResult) -> bool:
        """Determine if a record has exceeded its timeout."""
        try:
            accepted = datetime.fromisoformat(result.accepted_at)
        except (ValueError, TypeError):
            return True

        age_seconds = (datetime.now(timezone.utc) - accepted).total_seconds()

        if result.status == RequestStatus.PENDING:
            return age_seconds > self.config.stale_pending_timeout_seconds
        if result.status == RequestStatus.PROCESSING:
            return age_seconds > self.config.stale_processing_timeout_seconds
        return False

    def _decide_action(self, result: InferenceResult) -> ReconciliationEvent:
        """Decide what to do with a stale record."""
        if result.status == RequestStatus.PENDING:
            return ReconciliationEvent(
                request_id=result.request_id,
                previous_status=result.status,
                action=ReconciliationAction.RESUBMIT,
                reason=f"Stuck in pending beyond {self.config.stale_pending_timeout_seconds}s",
                dry_run=self.config.dry_run_enabled,
            )
        if result.status == RequestStatus.PROCESSING:
            return ReconciliationEvent(
                request_id=result.request_id,
                previous_status=result.status,
                action=ReconciliationAction.MARK_FAILED,
                reason=f"Stuck in processing beyond {self.config.stale_processing_timeout_seconds}s",
                dry_run=self.config.dry_run_enabled,
            )
        return ReconciliationEvent(
            request_id=result.request_id,
            previous_status=result.status,
            action=ReconciliationAction.SKIP,
            reason="No action needed",
        )

    def _execute_heal(self, event: ReconciliationEvent, result: InferenceResult) -> None:
        """Execute the healing action."""
        if event.action == ReconciliationAction.RESUBMIT:
            if self.queue_publisher:
                payload = {
                    "event_id": result.request_id,
                    "timestamp": result.accepted_at,
                    "prompt": "(reconciliation resubmit)",
                    "context": "",
                    "event_type": "reconciliation_retry",
                    "priority": 1,
                    "requested_model": result.model_name,
                    "metadata": {"reconciled": "true"},
                }
                self.queue_publisher.publish(payload)
                logger.info("resubmitted to queue", request_id=result.request_id)
            else:
                logger.warning("resubmit failed: no queue publisher", request_id=result.request_id)
                self._mark_failed(result, "Resubmit failed: no queue publisher")

        elif event.action == ReconciliationAction.MARK_FAILED:
            self._mark_failed(result, event.reason)

    def _mark_failed(self, result: InferenceResult, reason: str) -> None:
        """Mark a request as permanently failed."""
        self.result_store.put(InferenceResult(
            request_id=result.request_id,
            status=RequestStatus.FAILED,
            accepted_at=result.accepted_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            model_name=result.model_name,
            error=f"Reconciliation: {reason}",
        ))
        logger.info("marked failed", request_id=result.request_id, reason=reason)

    def _run_bedrock_analysis(self, event: ReconciliationEvent, result: InferenceResult) -> None:
        """Attach Bedrock failure analysis to the event."""
        if not self.bedrock_analyzer:
            return
        try:
            event.bedrock_analysis = self.bedrock_analyzer.analyze(result)
            logger.info("bedrock analysis attached", request_id=result.request_id)
        except Exception as e:
            logger.warning("bedrock analysis failed", request_id=result.request_id, error=str(e))
            event.bedrock_analysis = f"Analysis unavailable: {e}"

    def _notify(self, event: ReconciliationEvent, result: InferenceResult) -> None:
        """Send SNS notification for unrecoverable failure."""
        if not self.sns_publisher:
            logger.warning("notify failed: no SNS publisher", request_id=result.request_id)
            return
        try:
            self.sns_publisher.publish_failure(event, result)
            event.notified = True
            logger.info("sns notification sent", request_id=result.request_id)
        except Exception as e:
            logger.error("sns notification failed", request_id=result.request_id, error=str(e))

    def run_once(self) -> List[ReconciliationEvent]:
        """Execute one reconciliation pass. Returns all events for observability."""
        events: List[ReconciliationEvent] = []

        # Scan for stale pending and processing records
        stale_records: List[InferenceResult] = []
        for status in (RequestStatus.PENDING, RequestStatus.PROCESSING):
            for record in self.result_store.scan_by_status(status):
                if self._is_stale(record):
                    stale_records.append(record)

        if not stale_records:
            logger.debug("reconciliation pass complete", stale_count=0)
            return events

        logger.info("reconciliation pass started", stale_count=len(stale_records))

        for record in stale_records:
            event = self._decide_action(record)
            events.append(event)

            if event.action == ReconciliationAction.SKIP:
                continue

            # Dry run: log only
            if self.config.dry_run_enabled:
                logger.info(
                    "[DRY RUN] would execute",
                    request_id=event.request_id,
                    action=event.action.value,
                    previous_status=event.previous_status.value,
                    reason=event.reason,
                )
                continue

            # Heal mode: execute recovery
            if self.config.heal_enabled:
                self._execute_heal(event, record)

                # After healing, if the action was mark_failed, run optional analysis + notification
                if event.action == ReconciliationAction.MARK_FAILED:
                    if self.config.bedrock_analysis_enabled:
                        self._run_bedrock_analysis(event, record)

                    if self.config.sns_notification_enabled:
                        self._notify(event, record)
            else:
                # Neither dry run nor heal — just log the finding
                logger.info(
                    "stale request found, heal disabled",
                    request_id=event.request_id,
                    previous_status=event.previous_status.value,
                    action=event.action.value,
                )

        return events
