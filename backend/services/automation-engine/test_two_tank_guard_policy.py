"""Unit tests for two-tank guard helper policy."""

from datetime import datetime, timezone

from domain.policies.two_tank_guard_policy import (
    build_two_tank_check_payload,
    build_two_tank_stop_not_confirmed_result,
)


def test_build_two_tank_check_payload_for_clean_fill_sets_cycle():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    payload = build_two_tank_check_payload(
        payload={"task_type": "diagnostics"},
        workflow="clean_fill_check",
        phase_started_at=now,
        phase_timeout_at=now,
        phase_cycle=0,
    )
    assert payload["workflow"] == "clean_fill_check"
    assert payload["clean_fill_cycle"] == 1


def test_build_two_tank_check_payload_for_recovery_sets_attempt():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    payload = build_two_tank_check_payload(
        payload={"task_type": "diagnostics"},
        workflow="irrigation_recovery_check",
        phase_started_at=now,
        phase_timeout_at=now,
        phase_cycle=3,
    )
    assert payload["workflow"] == "irrigation_recovery_check"
    assert payload["irrigation_recovery_attempt"] == 3


def test_build_two_tank_stop_not_confirmed_result_fills_defaults():
    result = build_two_tank_stop_not_confirmed_result(
        workflow="solution_fill_check",
        mode="two_tank_startup",
        reason="stop_not_confirmed",
        stop_result={},
        reason_code="cycle_refill_failed",
        feature_flag_state=True,
        fallback_error_code="two_tank_command_failed",
    )
    assert result["success"] is False
    assert result["reason_code"] == "cycle_refill_failed"
    assert result["commands_failed"] == 1
    assert result["feature_flag_state"] is True
