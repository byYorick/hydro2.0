from executor.workflow_phase_policy import (
    WORKFLOW_PHASE_IDLE,
    WORKFLOW_PHASE_IRRIGATING,
    WORKFLOW_PHASE_IRRIG_RECIRC,
    WORKFLOW_PHASE_READY,
    WORKFLOW_PHASE_TANK_FILLING,
    WORKFLOW_PHASE_TANK_RECIRC,
    derive_workflow_phase,
    resolve_workflow_stage_for_state_sync,
)


def test_derive_workflow_phase_for_diagnostics_transitions():
    phase = derive_workflow_phase(
        task_type="diagnostics",
        payload={"workflow": "startup"},
        result={"success": True, "mode": "two_tank_clean_fill_in_progress"},
    )
    assert phase == WORKFLOW_PHASE_TANK_FILLING

    phase_ready = derive_workflow_phase(
        task_type="diagnostics",
        payload={"workflow": "prepare_recirculation_check"},
        result={"success": True, "mode": "two_tank_prepare_recirculation_completed"},
    )
    assert phase_ready == WORKFLOW_PHASE_READY


def test_derive_workflow_phase_for_diagnostics_terminal_failure_moves_to_idle():
    phase_failed = derive_workflow_phase(
        task_type="diagnostics",
        payload={"workflow": "startup"},
        result={
            "success": False,
            "mode": "two_tank_solution_fill_command_failed",
            "reason_code": "cycle_start_refill_command_failed",
            "action_required": True,
            "decision": "run",
        },
    )
    assert phase_failed == WORKFLOW_PHASE_IDLE


def test_derive_workflow_phase_for_diagnostics_transient_retry_keeps_phase():
    phase_retry = derive_workflow_phase(
        task_type="diagnostics",
        payload={"workflow": "prepare_recirculation_check"},
        result={
            "success": False,
            "mode": "two_tank_prepare_recirculation_irr_state_retry",
            "reason_code": "irr_state_stale",
            "action_required": True,
            "decision": "run",
            "irr_state_retry": True,
            "next_check": {"task_id": "st-next"},
        },
    )
    assert phase_retry is None


def test_derive_workflow_phase_for_diagnostics_irr_state_mismatch_keeps_blocking_phase():
    phase_blocked = derive_workflow_phase(
        task_type="diagnostics",
        payload={"workflow": "startup"},
        result={
            "success": False,
            "mode": "two_tank_irr_state_mismatch",
            "reason_code": "irr_state_mismatch",
            "action_required": True,
            "decision": "run",
        },
    )
    assert phase_blocked == WORKFLOW_PHASE_TANK_FILLING


def test_derive_workflow_phase_for_diagnostics_safety_blocked_keeps_workflow_phase():
    phase_blocked = derive_workflow_phase(
        task_type="diagnostics",
        payload={"workflow": "prepare_recirculation_check"},
        result={
            "success": False,
            "mode": "two_tank_prepare_recirculation_safety_blocked",
            "reason_code": "safety_blocked",
            "action_required": True,
            "decision": "run",
        },
    )
    assert phase_blocked == WORKFLOW_PHASE_TANK_RECIRC


def test_derive_workflow_phase_for_irrigation_recovery_and_run():
    recovery = derive_workflow_phase(
        task_type="irrigation",
        payload={"workflow": "irrigation_recovery"},
        result={"success": True, "mode": "irrigation_recovery"},
    )
    assert recovery == WORKFLOW_PHASE_IRRIG_RECIRC

    run = derive_workflow_phase(
        task_type="irrigation",
        payload={"workflow": "irrigation"},
        result={"success": True, "action_required": True, "decision": "run"},
    )
    assert run == WORKFLOW_PHASE_IRRIGATING


def test_resolve_workflow_stage_for_state_sync_from_mode_and_payload():
    stage_from_mode = resolve_workflow_stage_for_state_sync(
        payload={"workflow": "startup"},
        result={"mode": "two_tank_solution_fill_in_progress"},
        workflow_phase=WORKFLOW_PHASE_TANK_FILLING,
    )
    assert stage_from_mode == "solution_fill_check"

    stage_from_payload = resolve_workflow_stage_for_state_sync(
        payload={"workflow": "prepare_recirculation"},
        result={},
        workflow_phase=WORKFLOW_PHASE_TANK_FILLING,
    )
    assert stage_from_payload == "prepare_recirculation_check"
