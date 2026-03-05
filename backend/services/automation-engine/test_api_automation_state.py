from ae2lite.api_automation_state import derive_automation_state


def _extract_workflow(payload):
    return str(payload.get("workflow") or "").strip().lower() if isinstance(payload, dict) else ""


def test_derive_automation_state_manual_step_irrigation_recovery_maps_to_irrig_recirc():
    state = derive_automation_state(
        {
            "status": "running",
            "task_type": "diagnostics",
            "payload": {"workflow": "manual_step", "manual_step": "irrigation_recovery_start"},
            "result": {},
        },
        extract_workflow=_extract_workflow,
        state_idle="IDLE",
        state_tank_filling="TANK_FILLING",
        state_tank_recirc="TANK_RECIRC",
        state_ready="READY",
        state_irrigating="IRRIGATING",
        state_irrig_recirc="IRRIG_RECIRC",
    )

    assert state == "IRRIG_RECIRC"


def test_derive_automation_state_manual_step_prepare_recirculation_maps_to_tank_recirc():
    state = derive_automation_state(
        {
            "status": "accepted",
            "task_type": "diagnostics",
            "payload": {"workflow": "manual_step", "manual_step": "prepare_recirculation_stop"},
            "result": {},
        },
        extract_workflow=_extract_workflow,
        state_idle="IDLE",
        state_tank_filling="TANK_FILLING",
        state_tank_recirc="TANK_RECIRC",
        state_ready="READY",
        state_irrigating="IRRIGATING",
        state_irrig_recirc="IRRIG_RECIRC",
    )

    assert state == "TANK_RECIRC"


def test_derive_automation_state_manual_step_clean_fill_maps_to_tank_filling():
    state = derive_automation_state(
        {
            "status": "running",
            "task_type": "diagnostics",
            "payload": {"workflow": "manual_step", "manual_step": "clean_fill_start"},
            "result": {},
        },
        extract_workflow=_extract_workflow,
        state_idle="IDLE",
        state_tank_filling="TANK_FILLING",
        state_tank_recirc="TANK_RECIRC",
        state_ready="READY",
        state_irrigating="IRRIGATING",
        state_irrig_recirc="IRRIG_RECIRC",
    )

    assert state == "TANK_FILLING"
