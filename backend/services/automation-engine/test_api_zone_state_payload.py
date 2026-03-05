from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ae2lite.api_zone_state_payload import build_zone_automation_state_payload


@pytest.mark.asyncio
async def test_idle_payload_sanitizes_stale_irr_state_and_active_processes():
    stale_updated_at = (datetime.now(timezone.utc) - timedelta(minutes=10)).replace(tzinfo=None).isoformat()

    async def load_latest_zone_task(_zone_id: int):
        return {"payload": {}, "status": "completed"}

    async def load_zone_system_config(_zone_id: int, _payload: dict):
        return {}

    async def load_zone_current_levels(_zone_id: int):
        return {}

    async def load_latest_irr_node_state(_zone_id: int):
        return {
            "valve_clean_fill": False,
            "valve_clean_supply": False,
            "valve_solution_fill": True,
            "valve_solution_supply": True,
            "valve_irrigation": False,
            "pump_main": True,
            "updated_at": stale_updated_at,
        }

    async def load_automation_timeline(_zone_id: int):
        return []

    payload = await build_zone_automation_state_payload(
        5,
        load_latest_zone_task_fn=load_latest_zone_task,
        derive_automation_state_fn=lambda _task: "IDLE",
        resolve_state_started_at_fn=lambda _task, _state: None,
        estimate_progress_percent_fn=lambda _task, _state: 0,
        load_zone_system_config_fn=load_zone_system_config,
        load_zone_current_levels_fn=load_zone_current_levels,
        load_latest_irr_node_state_fn=load_latest_irr_node_state,
        derive_active_processes_fn=lambda _task, _state: {
            "pump_in": False,
            "circulation_pump": False,
            "ph_correction": False,
            "ec_correction": False,
        },
        load_automation_timeline_fn=load_automation_timeline,
        estimate_completion_seconds_fn=lambda _task: None,
        derive_failed_state_fn=lambda _task: False,
        automation_state_labels={"IDLE": "idle"},
        automation_state_idle="IDLE",
        automation_state_next={"IDLE": "TANK_FILLING"},
    )

    assert payload["irr_node_state"]["pump_main"] is False
    assert payload["irr_node_state"]["valve_solution_fill"] is False
    assert payload["irr_node_state"]["valve_solution_supply"] is False
    assert payload["irr_node_state"]["stale"] is True
    assert payload["active_processes"]["pump_in"] is False
    assert payload["active_processes"]["circulation_pump"] is False


@pytest.mark.asyncio
async def test_idle_payload_keeps_fresh_irr_state_override():
    fresh_updated_at = (datetime.now(timezone.utc) - timedelta(seconds=5)).replace(tzinfo=None).isoformat()

    async def load_latest_zone_task(_zone_id: int):
        return {"payload": {}, "status": "completed"}

    async def load_zone_system_config(_zone_id: int, _payload: dict):
        return {}

    async def load_zone_current_levels(_zone_id: int):
        return {}

    async def load_latest_irr_node_state(_zone_id: int):
        return {
            "valve_clean_fill": False,
            "valve_clean_supply": False,
            "valve_solution_fill": True,
            "valve_solution_supply": True,
            "valve_irrigation": False,
            "pump_main": True,
            "updated_at": fresh_updated_at,
        }

    async def load_automation_timeline(_zone_id: int):
        return []

    payload = await build_zone_automation_state_payload(
        5,
        load_latest_zone_task_fn=load_latest_zone_task,
        derive_automation_state_fn=lambda _task: "IDLE",
        resolve_state_started_at_fn=lambda _task, _state: None,
        estimate_progress_percent_fn=lambda _task, _state: 0,
        load_zone_system_config_fn=load_zone_system_config,
        load_zone_current_levels_fn=load_zone_current_levels,
        load_latest_irr_node_state_fn=load_latest_irr_node_state,
        derive_active_processes_fn=lambda _task, _state: {
            "pump_in": False,
            "circulation_pump": False,
            "ph_correction": False,
            "ec_correction": False,
        },
        load_automation_timeline_fn=load_automation_timeline,
        estimate_completion_seconds_fn=lambda _task: None,
        derive_failed_state_fn=lambda _task: False,
        automation_state_labels={"IDLE": "idle"},
        automation_state_idle="IDLE",
        automation_state_next={"IDLE": "TANK_FILLING"},
    )

    assert payload["irr_node_state"]["pump_main"] is True
    assert payload["irr_node_state"].get("stale") is None
    assert payload["active_processes"]["circulation_pump"] is True
