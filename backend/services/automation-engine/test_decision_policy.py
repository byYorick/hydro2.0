"""Unit tests for scheduler decision policy module."""

from domain.policies.decision_policy import (
    decide_action,
    decide_irrigation_action,
    extract_next_due_at,
)


def test_decide_action_skips_when_already_running():
    result = decide_action(
        task_type="irrigation",
        payload={"already_running": True},
        auto_logic_decision_v1=True,
        auto_logic_new_sensors_v1=True,
    )
    assert result.action_required is False
    assert result.decision == "skip"
    assert result.reason_code == "already_running"


def test_decide_action_runs_for_lighting_state_change():
    result = decide_action(
        task_type="lighting",
        payload={"desired_state": True, "current_state": False},
        auto_logic_decision_v1=True,
        auto_logic_new_sensors_v1=True,
    )
    assert result.action_required is True
    assert result.decision == "run"
    assert result.reason_code == "lighting_required"


def test_decide_irrigation_action_retries_on_low_water():
    result = decide_irrigation_action(
        payload={
            "low_water": True,
            "decision_retry_attempt": 0,
            "config": {"execution": {"decision": {"max_retry": 3, "backoff_sec": 30}}},
        },
        auto_logic_new_sensors_v1=True,
    )
    assert result.action_required is False
    assert result.decision == "retry"
    assert result.reason_code == "low_water"
    assert result.details["retry_max_attempts"] == 3


def test_decide_irrigation_action_fails_after_retry_limit():
    result = decide_irrigation_action(
        payload={
            "nodes_unavailable": True,
            "decision_retry_attempt": 5,
            "config": {"execution": {"decision": {"max_retry": 3, "backoff_sec": 30}}},
        },
        auto_logic_new_sensors_v1=True,
    )
    assert result.action_required is False
    assert result.decision == "fail"
    assert result.reason_code == "nodes_unavailable"


def test_extract_next_due_at_prefers_result_then_decision_details():
    fallback = type("Decision", (), {"details": {"next_due_at": "2026-01-01T10:00:00"}})()
    result = extract_next_due_at(decision=fallback, result={"next_due_at": "2026-01-01T09:00:00"})
    assert result == "2026-01-01T09:00:00"


def test_extract_next_due_at_uses_next_check_when_next_due_absent():
    fallback = type("Decision", (), {"details": {"next_due_at": "2026-01-01T10:00:00"}})()
    result = extract_next_due_at(
        decision=fallback,
        result={"next_check": {"scheduled_for": "2026-01-01T09:30:00"}},
    )
    assert result == "2026-01-01T09:30:00"
