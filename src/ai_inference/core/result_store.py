"""
Result store for tracking inference request lifecycle.

Starts as an in-memory implementation. The protocol boundary allows a
DynamoDB or Redis backend to replace this without changing gateway or
worker code.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Protocol

import boto3
from pydantic import BaseModel, Field


class RequestStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class InferenceResult(BaseModel):
    request_id: str
    status: RequestStatus
    accepted_at: str
    completed_at: Optional[str] = None
    model_name: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None


class ResultStore(Protocol):
    def put(self, result: InferenceResult) -> None: ...
    def get(self, request_id: str) -> Optional[InferenceResult]: ...
    def scan_by_status(self, status: RequestStatus) -> list[InferenceResult]: ...


class InMemoryResultStore:
    """Thread-safe in-memory store. Suitable for single-process dev/demo."""

    def __init__(self) -> None:
        self._store: Dict[str, InferenceResult] = {}

    def put(self, result: InferenceResult) -> None:
        self._store[result.request_id] = result

    def get(self, request_id: str) -> Optional[InferenceResult]:
        return self._store.get(request_id)

    def scan_by_status(self, status: RequestStatus) -> list[InferenceResult]:
        return [r for r in self._store.values() if r.status == status]


class DynamoResultStore:
    """DynamoDB-backed result store for deployed environments.

    Table schema:
        PK: request_id (S)
        ttl: epoch seconds for automatic expiry
    """

    def __init__(self, table_name: str, region: str = "us-east-1", ttl_days: int = 7) -> None:
        self._table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        self._ttl_seconds = ttl_days * 86400

    def put(self, result: InferenceResult) -> None:
        item: Dict[str, Any] = {
            "request_id": result.request_id,
            "status": result.status.value,
            "accepted_at": result.accepted_at,
            "ttl": int(time.time()) + self._ttl_seconds,
        }
        if result.completed_at:
            item["completed_at"] = result.completed_at
        if result.model_name:
            item["model_name"] = result.model_name
        if result.result:
            item["result"] = result.result
        if result.error:
            item["error"] = result.error
        self._table.put_item(Item=item)

    def get(self, request_id: str) -> Optional[InferenceResult]:
        resp = self._table.get_item(Key={"request_id": request_id})
        item = resp.get("Item")
        if not item:
            return None
        return InferenceResult(
            request_id=item["request_id"],
            status=RequestStatus(item["status"]),
            accepted_at=item["accepted_at"],
            completed_at=item.get("completed_at"),
            model_name=item.get("model_name"),
            result=item.get("result"),
            error=item.get("error"),
        )

    def scan_by_status(self, status: RequestStatus) -> list[InferenceResult]:
        resp = self._table.scan(
            FilterExpression="#s = :status",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":status": status.value},
        )
        return [
            InferenceResult(
                request_id=item["request_id"],
                status=RequestStatus(item["status"]),
                accepted_at=item["accepted_at"],
                completed_at=item.get("completed_at"),
                model_name=item.get("model_name"),
                result=item.get("result"),
                error=item.get("error"),
            )
            for item in resp.get("Items", [])
        ]
