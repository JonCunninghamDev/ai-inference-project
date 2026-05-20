"""Tests for the reconciliation engine."""
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

from ai_inference.core.reconciliation import (
    ReconciliationAction,
    ReconciliationConfig,
    ReconciliationEngine,
)
from ai_inference.core.result_store import InferenceResult, InMemoryResultStore, RequestStatus


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _past_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _build_engine(store=None, config=None, publisher=None, sns=None, bedrock=None):
    store = store or InMemoryResultStore()
    config = config or ReconciliationConfig()
    return ReconciliationEngine(
        config=config,
        result_store=store,
        queue_publisher=publisher,
        sns_publisher=sns,
        bedrock_analyzer=bedrock,
    ), store


# --- No stale records ---


def test_no_stale_records_returns_empty():
    engine, store = _build_engine()
    store.put(InferenceResult(request_id="r1", status=RequestStatus.COMPLETED, accepted_at=_now_iso()))
    events = engine.run_once()
    assert events == []


def test_fresh_pending_not_stale():
    engine, store = _build_engine()
    store.put(InferenceResult(request_id="r1", status=RequestStatus.PENDING, accepted_at=_now_iso()))
    events = engine.run_once()
    assert events == []


# --- Dry run mode ---


def test_dry_run_logs_but_does_not_heal():
    config = ReconciliationConfig(dry_run_enabled=True, stale_pending_timeout_seconds=10)
    engine, store = _build_engine(config=config)
    store.put(InferenceResult(request_id="r1", status=RequestStatus.PENDING, accepted_at=_past_iso(60)))

    events = engine.run_once()

    assert len(events) == 1
    assert events[0].action == ReconciliationAction.RESUBMIT
    assert events[0].dry_run is True
    # Record should NOT have changed
    assert store.get("r1").status == RequestStatus.PENDING


def test_dry_run_stale_processing_suggests_mark_failed():
    config = ReconciliationConfig(dry_run_enabled=True, stale_processing_timeout_seconds=10)
    engine, store = _build_engine(config=config)
    store.put(InferenceResult(request_id="r1", status=RequestStatus.PROCESSING, accepted_at=_past_iso(60)))

    events = engine.run_once()

    assert len(events) == 1
    assert events[0].action == ReconciliationAction.MARK_FAILED
    assert events[0].dry_run is True
    assert store.get("r1").status == RequestStatus.PROCESSING


# --- Heal mode ---


def test_heal_resubmits_stale_pending():
    publisher = Mock()
    config = ReconciliationConfig(heal_enabled=True, stale_pending_timeout_seconds=10)
    engine, store = _build_engine(config=config, publisher=publisher)
    store.put(InferenceResult(
        request_id="r1", status=RequestStatus.PENDING,
        accepted_at=_past_iso(60), model_name="test-model",
    ))

    events = engine.run_once()

    assert len(events) == 1
    assert events[0].action == ReconciliationAction.RESUBMIT
    publisher.publish.assert_called_once()
    payload = publisher.publish.call_args[0][0]
    assert payload["event_id"] == "r1"
    assert payload["requested_model"] == "test-model"


def test_heal_marks_stale_processing_as_failed():
    config = ReconciliationConfig(heal_enabled=True, stale_processing_timeout_seconds=10)
    engine, store = _build_engine(config=config)
    store.put(InferenceResult(request_id="r1", status=RequestStatus.PROCESSING, accepted_at=_past_iso(60)))

    events = engine.run_once()

    assert len(events) == 1
    assert events[0].action == ReconciliationAction.MARK_FAILED
    result = store.get("r1")
    assert result.status == RequestStatus.FAILED
    assert "Reconciliation" in result.error


def test_heal_without_publisher_marks_failed():
    config = ReconciliationConfig(heal_enabled=True, stale_pending_timeout_seconds=10)
    engine, store = _build_engine(config=config, publisher=None)
    store.put(InferenceResult(request_id="r1", status=RequestStatus.PENDING, accepted_at=_past_iso(60)))

    events = engine.run_once()

    assert events[0].action == ReconciliationAction.RESUBMIT
    result = store.get("r1")
    assert result.status == RequestStatus.FAILED
    assert "no queue publisher" in result.error


# --- Bedrock analysis ---


def test_bedrock_analysis_attached_on_failure():
    bedrock = Mock()
    bedrock.analyze.return_value = "GPU OOM likely. Reduce batch size."
    config = ReconciliationConfig(
        heal_enabled=True, bedrock_analysis_enabled=True,
        stale_processing_timeout_seconds=10,
    )
    engine, store = _build_engine(config=config, bedrock=bedrock)
    store.put(InferenceResult(request_id="r1", status=RequestStatus.PROCESSING, accepted_at=_past_iso(60)))

    events = engine.run_once()

    assert events[0].bedrock_analysis == "GPU OOM likely. Reduce batch size."
    bedrock.analyze.assert_called_once()


def test_bedrock_failure_does_not_crash_reconciliation():
    bedrock = Mock()
    bedrock.analyze.side_effect = RuntimeError("Bedrock unavailable")
    config = ReconciliationConfig(
        heal_enabled=True, bedrock_analysis_enabled=True,
        stale_processing_timeout_seconds=10,
    )
    engine, store = _build_engine(config=config, bedrock=bedrock)
    store.put(InferenceResult(request_id="r1", status=RequestStatus.PROCESSING, accepted_at=_past_iso(60)))

    events = engine.run_once()

    assert "unavailable" in events[0].bedrock_analysis
    assert store.get("r1").status == RequestStatus.FAILED


# --- SNS notification ---


def test_sns_notifies_on_unrecoverable_failure():
    sns = Mock()
    config = ReconciliationConfig(
        heal_enabled=True, sns_notification_enabled=True,
        stale_processing_timeout_seconds=10,
    )
    engine, store = _build_engine(config=config, sns=sns)
    store.put(InferenceResult(request_id="r1", status=RequestStatus.PROCESSING, accepted_at=_past_iso(60)))

    events = engine.run_once()

    assert events[0].notified is True
    sns.publish_failure.assert_called_once()


def test_sns_not_called_for_resubmit():
    sns = Mock()
    publisher = Mock()
    config = ReconciliationConfig(
        heal_enabled=True, sns_notification_enabled=True,
        stale_pending_timeout_seconds=10,
    )
    engine, store = _build_engine(config=config, publisher=publisher, sns=sns)
    store.put(InferenceResult(request_id="r1", status=RequestStatus.PENDING, accepted_at=_past_iso(60)))

    events = engine.run_once()

    # SNS should NOT fire for resubmits — only for mark_failed (unrecoverable)
    sns.publish_failure.assert_not_called()
    assert events[0].notified is False


def test_sns_failure_does_not_crash_reconciliation():
    sns = Mock()
    sns.publish_failure.side_effect = RuntimeError("SNS unavailable")
    config = ReconciliationConfig(
        heal_enabled=True, sns_notification_enabled=True,
        stale_processing_timeout_seconds=10,
    )
    engine, store = _build_engine(config=config, sns=sns)
    store.put(InferenceResult(request_id="r1", status=RequestStatus.PROCESSING, accepted_at=_past_iso(60)))

    events = engine.run_once()

    assert events[0].notified is False
    assert store.get("r1").status == RequestStatus.FAILED


# --- Multiple stale records ---


def test_multiple_stale_records_processed():
    publisher = Mock()
    config = ReconciliationConfig(
        heal_enabled=True,
        stale_pending_timeout_seconds=10,
        stale_processing_timeout_seconds=10,
    )
    engine, store = _build_engine(config=config, publisher=publisher)
    store.put(InferenceResult(request_id="r1", status=RequestStatus.PENDING, accepted_at=_past_iso(60)))
    store.put(InferenceResult(request_id="r2", status=RequestStatus.PROCESSING, accepted_at=_past_iso(60)))
    store.put(InferenceResult(request_id="r3", status=RequestStatus.COMPLETED, accepted_at=_past_iso(60)))

    events = engine.run_once()

    assert len(events) == 2
    actions = {e.request_id: e.action for e in events}
    assert actions["r1"] == ReconciliationAction.RESUBMIT
    assert actions["r2"] == ReconciliationAction.MARK_FAILED


# --- Neither dry run nor heal ---


def test_no_modes_enabled_just_logs():
    config = ReconciliationConfig(
        dry_run_enabled=False, heal_enabled=False,
        stale_pending_timeout_seconds=10,
    )
    engine, store = _build_engine(config=config)
    store.put(InferenceResult(request_id="r1", status=RequestStatus.PENDING, accepted_at=_past_iso(60)))

    events = engine.run_once()

    assert len(events) == 1
    assert events[0].action == ReconciliationAction.RESUBMIT
    # Nothing should have changed
    assert store.get("r1").status == RequestStatus.PENDING
