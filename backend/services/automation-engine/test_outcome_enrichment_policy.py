"""Unit tests for outcome enrichment policy."""

from domain.models.decision_models import DecisionOutcome
from domain.policies.outcome_enrichment_policy import ensure_extended_outcome


def test_ensure_extended_outcome_builds_default_steps_and_safety_flags():
    decision = DecisionOutcome(
        action_required=True,
        decision="run",
        reason_code="x",
        reason="x",
        details={"safety_flags": ["from_details"]},
    )
    result = ensure_extended_outcome(
        task_type="diagnostics",
        payload={},
        decision=decision,
        result={"success": False, "reason_code": "low_water"},
        extract_next_due_at=lambda _d, _r: "2030-01-01T00:00:00",
        safe_int=lambda _v: None,
        extract_topology=lambda _p: "",
        extract_two_tank_chemistry_orchestration=lambda _p: {},
        wind_blocked_reason="wind_blocked",
        outside_temp_blocked_reason="outside_temp_blocked",
    )
    assert result["executed_steps"][0]["status"] == "failed"
    assert set(result["safety_flags"]) == {"low_water", "from_details"}
    assert result["next_due_at"] == "2030-01-01T00:00:00"


def test_ensure_extended_outcome_uses_targets_state_when_no_measurements_snapshot():
    decision = DecisionOutcome(action_required=True, decision="run", reason_code="x", reason="x", details={})
    result = ensure_extended_outcome(
        task_type="diagnostics",
        payload={},
        decision=decision,
        result={"targets_state": {"ph": {"value": 6.2}, "ec": {"value": 1.5}}},
        extract_next_due_at=lambda _d, _r: None,
        safe_int=lambda _v: None,
        extract_topology=lambda _p: "",
        extract_two_tank_chemistry_orchestration=lambda _p: {},
        wind_blocked_reason="wind_blocked",
        outside_temp_blocked_reason="outside_temp_blocked",
    )
    assert result["measurements_before_after"]["before"] == {"ph": 6.2, "ec": 1.5}


def test_ensure_extended_outcome_adds_two_tank_chemistry_and_retry_fields():
    decision = DecisionOutcome(
        action_required=True,
        decision="retry",
        reason_code="x",
        reason="x",
        details={"retry_attempt": 2, "retry_max_attempts": 5, "retry_backoff_sec": 15, "run_mode": "auto"},
    )
    result = ensure_extended_outcome(
        task_type="diagnostics",
        payload={"config": {"execution": {"topology": "two_tank_drip_substrate_trays"}}},
        decision=decision,
        result={"success": False},
        extract_next_due_at=lambda _d, _r: None,
        safe_int=lambda v: int(v) if v is not None else None,
        extract_topology=lambda _p: "two_tank_drip_substrate_trays",
        extract_two_tank_chemistry_orchestration=lambda _p: {"prepare_sequence": ["npk", "ph"]},
        wind_blocked_reason="wind_blocked",
        outside_temp_blocked_reason="outside_temp_blocked",
    )
    assert result["run_mode"] == "auto"
    assert result["retry_attempt"] == 2
    assert result["retry_max_attempts"] == 5
    assert result["retry_backoff_sec"] == 15
    assert result["chemistry_orchestration"] == {"prepare_sequence": ["npk", "ph"]}
