import logging

from executor.workflow_phase_policy import (
    WORKFLOW_PHASE_IDLE,
    WORKFLOW_PHASE_IRRIGATING,
    WORKFLOW_PHASE_IRRIG_RECIRC,
    WORKFLOW_PHASE_READY,
    WORKFLOW_PHASE_TANK_FILLING,
    WORKFLOW_PHASE_TANK_RECIRC,
    WORKFLOW_PHASE_VALID_TRANSITIONS,
    build_workflow_state_payload,
    derive_workflow_phase,
    is_valid_phase_transition,
    resolve_workflow_stage_for_state_sync,
    validate_phase_transition,
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


def test_derive_workflow_phase_for_recovery_safety_blocked_resets_to_idle():
    phase_blocked = derive_workflow_phase(
        task_type="diagnostics",
        payload={"workflow": "irrigation_recovery_check"},
        result={
            "success": False,
            "mode": "two_tank_irrigation_recovery_safety_blocked",
            "reason_code": "safety_blocked",
            "action_required": True,
            "decision": "run",
        },
    )
    assert phase_blocked == WORKFLOW_PHASE_IDLE


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


def test_derive_workflow_phase_for_diagnostics_recovery_attempts_exhausted_maps_to_irrigating():
    phase = derive_workflow_phase(
        task_type="diagnostics",
        payload={"workflow": "irrigation_recovery_check"},
        result={
            "success": True,
            "mode": "two_tank_irrigation_recovery_attempts_exhausted_continue_irrigation",
            "reason_code": "irrigation_correction_attempts_exhausted_continue_irrigation",
            "decision": "skip",
            "action_required": True,
        },
    )
    assert phase == WORKFLOW_PHASE_IRRIGATING


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


def test_build_workflow_state_payload_prefers_next_check_continuation_payload():
    state_payload = build_workflow_state_payload(
        payload={"workflow": "irrigation_recovery_check"},
        result={
            "mode": "two_tank_irrigation_recovery_in_progress",
            "reason_code": "irrigation_recovery_started",
            "next_check": {
                "details": {
                    "payload": {
                        "workflow": "irrigation_recovery_check",
                        "irrigation_recovery_attempt": 2,
                        "irrigation_recovery_started_at": "2026-03-04T10:17:04.521465",
                        "irrigation_recovery_timeout_at": "2026-03-04T10:27:04.521465",
                    }
                }
            },
        },
        workflow_phase=WORKFLOW_PHASE_IRRIG_RECIRC,
        workflow_stage="irrigation_recovery_check",
    )

    assert state_payload["workflow"] == "irrigation_recovery_check"
    assert state_payload["workflow_stage"] == "irrigation_recovery_check"
    assert state_payload["workflow_phase"] == WORKFLOW_PHASE_IRRIG_RECIRC
    assert state_payload["workflow_mode"] == "two_tank_irrigation_recovery_in_progress"
    assert state_payload["workflow_reason_code"] == "irrigation_recovery_started"
    assert state_payload["irrigation_recovery_attempt"] == 2
    assert state_payload["irrigation_recovery_started_at"] == "2026-03-04T10:17:04.521465"
    assert state_payload["irrigation_recovery_timeout_at"] == "2026-03-04T10:27:04.521465"


def test_is_valid_phase_transition_accepts_all_declared_transitions():
    for from_phase, to_phases in WORKFLOW_PHASE_VALID_TRANSITIONS.items():
        for to_phase in to_phases:
            assert is_valid_phase_transition(from_phase, to_phase) is True


def test_validate_phase_transition_logs_warning_for_invalid_transition(caplog):
    logger = logging.getLogger("test_workflow_phase_policy")
    with caplog.at_level(logging.WARNING):
        ok = validate_phase_transition(
            from_phase=WORKFLOW_PHASE_IDLE,
            to_phase=WORKFLOW_PHASE_IRRIGATING,
            zone_id=15,
            logger=logger,
        )

    assert ok is False
    assert "invalid workflow phase transition idle -> irrigating" in caplog.text
