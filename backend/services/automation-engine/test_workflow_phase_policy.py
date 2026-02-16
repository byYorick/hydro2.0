"""Unit tests for workflow phase/stage policy helpers."""

from application.workflow_phase_policy import (
    WORKFLOW_PHASE_IDLE,
    WORKFLOW_PHASE_IRRIGATING,
    WORKFLOW_PHASE_IRRIG_RECIRC,
    WORKFLOW_PHASE_READY,
    WORKFLOW_PHASE_TANK_FILLING,
    build_workflow_state_payload,
    derive_workflow_phase,
    normalize_workflow_phase,
    normalize_workflow_stage,
    resolve_workflow_stage_for_state_sync,
)


def test_derive_workflow_phase_diagnostics_ready_mode():
    phase = derive_workflow_phase(
        task_type="diagnostics",
        payload={"workflow": "startup"},
        result={"mode": "two_tank_startup_completed", "success": True},
    )

    assert phase == WORKFLOW_PHASE_READY


def test_derive_workflow_phase_irrigation_recovery_mode():
    phase = derive_workflow_phase(
        task_type="irrigation",
        payload={"workflow": "irrigation_recovery"},
        result={"mode": "any", "success": True, "action_required": True, "decision": "run"},
    )

    assert phase == WORKFLOW_PHASE_IRRIG_RECIRC


def test_derive_workflow_phase_irrigation_running_mode():
    phase = derive_workflow_phase(
        task_type="irrigation",
        payload={},
        result={"mode": "run", "success": True, "action_required": True, "decision": "run"},
    )

    assert phase == WORKFLOW_PHASE_IRRIGATING


def test_resolve_workflow_stage_for_state_sync_startup_defaults_to_solution_fill_check():
    stage = resolve_workflow_stage_for_state_sync(
        payload={"workflow": "startup"},
        result={"workflow": "startup"},
        workflow_phase=WORKFLOW_PHASE_TANK_FILLING,
    )

    assert stage == "solution_fill_check"


def test_build_workflow_state_payload_sets_and_clears_workflow_stage_alias():
    with_stage = build_workflow_state_payload(
        payload={"workflow": "startup", "workflow_stage": "startup"},
        result={"mode": "m1", "reason_code": "r1"},
        workflow_phase=WORKFLOW_PHASE_TANK_FILLING,
        workflow_stage="solution_fill_check",
    )
    assert with_stage["workflow"] == "solution_fill_check"
    assert with_stage["workflow_stage"] == "solution_fill_check"

    without_stage = build_workflow_state_payload(
        payload={"workflow": "startup", "workflow_stage": "startup"},
        result={"mode": "m1", "reason_code": "r1"},
        workflow_phase=WORKFLOW_PHASE_IDLE,
        workflow_stage="",
    )
    assert without_stage["workflow"] == "startup"
    assert "workflow_stage" not in without_stage


def test_normalize_helpers_return_defaults_for_invalid_values():
    assert normalize_workflow_phase("invalid_phase") == WORKFLOW_PHASE_IDLE
    assert normalize_workflow_stage("invalid_stage") == ""
