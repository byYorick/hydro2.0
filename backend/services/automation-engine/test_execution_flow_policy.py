"""Unit tests for application.execution_flow_policy helpers."""

from domain.models.decision_models import DecisionOutcome
from application.execution_flow_policy import (
    apply_decision_defaults,
    build_decision_payload,
    build_execution_finished_zone_event_payload,
    build_execution_started_zone_event_payload,
    build_no_action_result,
    build_task_finished_payload,
    build_task_received_payload,
)


def test_build_decision_payload_includes_details():
    decision = DecisionOutcome(
        action_required=False,
        decision="retry",
        reason_code="low_water",
        reason="x",
        details={"retry_attempt": 2},
    )
    payload = build_decision_payload(decision)
    assert payload["decision"] == "retry"
    assert payload["decision_details"]["retry_attempt"] == 2


def test_build_no_action_result_with_retry_payload():
    decision = DecisionOutcome(
        action_required=False,
        decision="retry",
        reason_code="low_water",
        reason="need water",
        details={"retry_attempt": 1},
    )
    result = build_no_action_result(
        task_type="diagnostics",
        decision=decision,
        retry_enqueue={"status": "queued"},
    )
    assert result["success"] is True
    assert result["mode"] == "decision_retry"
    assert result["retry_enqueued"]["status"] == "queued"


def test_apply_decision_defaults_sets_missing_fields_only():
    decision = DecisionOutcome(
        action_required=True,
        decision="run",
        reason_code="ok",
        reason="ok",
        details={"x": 1},
    )
    patched = apply_decision_defaults(result={"decision": "override"}, decision=decision)
    assert patched["decision"] == "override"
    assert patched["action_required"] is True
    assert patched["reason_code"] == "ok"
    assert patched["decision_details"]["x"] == 1


def test_event_payload_builders_match_contract():
    context = {"task_id": "st-1", "correlation_id": "corr-1", "scheduled_for": "ts"}
    payload = {"workflow": "startup"}
    task_received = build_task_received_payload(payload=payload, context=context)
    assert task_received["scheduled_for"] == "ts"

    started = build_execution_started_zone_event_payload(
        task_type="diagnostics",
        payload=payload,
        context=context,
    )
    assert started["task_id"] == "st-1"

    finished = build_execution_finished_zone_event_payload(
        task_type="diagnostics",
        result={"success": True},
        context=context,
    )
    assert finished["success"] is True
    assert finished["correlation_id"] == "corr-1"

    finished_task_event = build_task_finished_payload({"decision": "run", "reason_code": "ok"})
    assert finished_task_event["decision"] == "run"
