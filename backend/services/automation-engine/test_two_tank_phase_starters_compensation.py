from __future__ import annotations

import pytest

from executor.two_tank_phase_starters_prepare import start_two_tank_prepare_recirculation
from executor.two_tank_phase_starters_recovery import start_two_tank_irrigation_recovery
from executor.two_tank_phase_starters_startup import start_two_tank_solution_fill


async def _unexpected_async(*_args, **_kwargs):
    raise AssertionError("unexpected call")


def _merge_command_dispatch_results(plan_result: dict, sensor_mode_result: dict) -> dict:
    return {
        "success": bool(plan_result.get("success")) and bool(sensor_mode_result.get("success")),
        "commands_total": int(plan_result.get("commands_total", 0)) + int(sensor_mode_result.get("commands_total", 0)),
        "commands_failed": int(plan_result.get("commands_failed", 0))
        + int(sensor_mode_result.get("commands_failed", 0)),
        "command_statuses": list(sensor_mode_result.get("command_statuses", []))
        + list(plan_result.get("command_statuses", [])),
        "error": str(plan_result.get("error") or ""),
        "error_code": str(plan_result.get("error_code") or ""),
    }


async def _sensor_mode_ok(*_args, **_kwargs):
    return {
        "success": True,
        "commands_total": 2,
        "commands_failed": 0,
        "command_statuses": [{"status": "DONE", "channel": "ph_sensor_mode"}],
    }


async def _dispatch_plan_failed(*_args, **_kwargs):
    return _failed_plan_result()


def _failed_plan_result() -> dict:
    return {
        "success": False,
        "commands_total": 2,
        "commands_failed": 1,
        "command_statuses": [
            {"status": "DONE", "channel": "pump_main"},
            {"status": "TIMEOUT", "channel": "valve_solution_supply"},
        ],
        "error": "command_timeout",
        "error_code": "command_timeout",
    }


def _runtime_cfg() -> dict:
    return {
        "commands": {
            "solution_fill_start": [{"channel": "pump_main", "cmd": "set_relay", "params": {"state": True}}],
            "solution_fill_stop": [{"channel": "pump_main", "cmd": "set_relay", "params": {"state": False}}],
            "prepare_recirculation_start": [{"channel": "pump_main", "cmd": "set_relay", "params": {"state": True}}],
            "prepare_recirculation_stop": [{"channel": "pump_main", "cmd": "set_relay", "params": {"state": False}}],
            "irrigation_recovery_start": [{"channel": "pump_main", "cmd": "set_relay", "params": {"state": True}}],
            "irrigation_recovery_stop": [{"channel": "pump_main", "cmd": "set_relay", "params": {"state": False}}],
        },
        "solution_fill_timeout_sec": 300,
        "prepare_recirculation_timeout_sec": 300,
        "irrigation_recovery_timeout_sec": 300,
        "poll_interval_sec": 30,
    }


@pytest.mark.asyncio
async def test_solution_fill_command_failed_triggers_compensating_stop(monkeypatch):
    async def fake_can_run_pump(**_kwargs):
        return True, None

    compensation_calls: list[dict] = []

    async def fake_compensate(**kwargs):
        compensation_calls.append(dict(kwargs))
        return {"success": True, "commands_total": 3, "commands_failed": 0, "command_statuses": []}

    monkeypatch.setattr("executor.two_tank_phase_starters_startup.can_run_pump", fake_can_run_pump)

    result = await start_two_tank_solution_fill(
        zone_id=4,
        payload={},
        context={"task_id": "st-1"},
        runtime_cfg=_runtime_cfg(),
        dispatch_two_tank_command_plan_fn=_dispatch_plan_failed,
        dispatch_sensor_mode_command_for_nodes_fn=_sensor_mode_ok,
        merge_command_dispatch_results_fn=_merge_command_dispatch_results,
        update_zone_workflow_phase_fn=_unexpected_async,
        enqueue_two_tank_check_fn=_unexpected_async,
        compensate_two_tank_start_enqueue_failure_fn=fake_compensate,
        emit_task_event_fn=_unexpected_async,
        two_tank_safety_guards_enabled_fn=lambda: True,
        workflow_phase_tank_filling="tank_filling",
        reason_solution_fill_started="solution_fill_started",
        reason_cycle_refill_command_failed="cycle_refill_command_failed",
        reason_cycle_self_task_enqueue_failed="cycle_self_task_enqueue_failed",
        err_two_tank_command_failed="two_tank_command_failed",
        err_two_tank_enqueue_failed="two_tank_enqueue_failed",
    )

    assert result["success"] is False
    assert result["mode"] == "two_tank_solution_fill_command_failed"
    assert result["error_code"] == "command_timeout"
    assert result["feature_flag_state"] is True
    assert result["stop_result"]["success"] is True
    assert compensation_calls[0]["workflow"] == "startup"
    assert compensation_calls[0]["phase"] == "solution_fill_start"


@pytest.mark.asyncio
async def test_prepare_recirculation_command_failed_triggers_compensating_stop(monkeypatch):
    async def fake_can_run_pump(**_kwargs):
        return True, None

    compensation_calls: list[dict] = []

    async def fake_compensate(**kwargs):
        compensation_calls.append(dict(kwargs))
        return {"success": True, "commands_total": 3, "commands_failed": 0, "command_statuses": []}

    monkeypatch.setattr("executor.two_tank_phase_starters_prepare.can_run_pump", fake_can_run_pump)

    result = await start_two_tank_prepare_recirculation(
        zone_id=4,
        payload={},
        context={"task_id": "st-2"},
        runtime_cfg=_runtime_cfg(),
        dispatch_two_tank_command_plan_fn=_dispatch_plan_failed,
        dispatch_sensor_mode_command_for_nodes_fn=_sensor_mode_ok,
        merge_command_dispatch_results_fn=_merge_command_dispatch_results,
        update_zone_workflow_phase_fn=_unexpected_async,
        enqueue_two_tank_check_fn=_unexpected_async,
        compensate_two_tank_start_enqueue_failure_fn=fake_compensate,
        two_tank_safety_guards_enabled_fn=lambda: True,
        workflow_phase_tank_recirc="tank_recirc",
        reason_prepare_recirculation_started="prepare_recirculation_started",
        reason_cycle_refill_command_failed="cycle_refill_command_failed",
        reason_cycle_self_task_enqueue_failed="cycle_self_task_enqueue_failed",
        err_two_tank_command_failed="two_tank_command_failed",
        err_two_tank_enqueue_failed="two_tank_enqueue_failed",
    )

    assert result["success"] is False
    assert result["mode"] == "two_tank_prepare_recirculation_command_failed"
    assert result["error_code"] == "command_timeout"
    assert result["feature_flag_state"] is True
    assert result["stop_result"]["success"] is True
    assert compensation_calls[0]["workflow"] == "prepare_recirculation"
    assert compensation_calls[0]["phase"] == "prepare_recirculation_start"


@pytest.mark.asyncio
async def test_irrigation_recovery_command_failed_triggers_compensating_stop(monkeypatch):
    async def fake_can_run_pump(**_kwargs):
        return True, None

    compensation_calls: list[dict] = []

    async def fake_compensate(**kwargs):
        compensation_calls.append(dict(kwargs))
        return {"success": True, "commands_total": 3, "commands_failed": 0, "command_statuses": []}

    monkeypatch.setattr("executor.two_tank_phase_starters_recovery.can_run_pump", fake_can_run_pump)

    result = await start_two_tank_irrigation_recovery(
        zone_id=4,
        payload={},
        context={"task_id": "st-3"},
        runtime_cfg=_runtime_cfg(),
        attempt=1,
        dispatch_two_tank_command_plan_fn=_dispatch_plan_failed,
        dispatch_sensor_mode_command_for_nodes_fn=_sensor_mode_ok,
        merge_command_dispatch_results_fn=_merge_command_dispatch_results,
        update_zone_workflow_phase_fn=_unexpected_async,
        enqueue_two_tank_check_fn=_unexpected_async,
        compensate_two_tank_start_enqueue_failure_fn=fake_compensate,
        two_tank_safety_guards_enabled_fn=lambda: True,
        workflow_phase_irrig_recirc="irrig_recirc",
        reason_irrigation_recovery_started="irrigation_recovery_started",
        reason_irrigation_recovery_failed="irrigation_recovery_failed",
        reason_cycle_self_task_enqueue_failed="cycle_self_task_enqueue_failed",
        err_two_tank_command_failed="two_tank_command_failed",
        err_two_tank_enqueue_failed="two_tank_enqueue_failed",
    )

    assert result["success"] is False
    assert result["mode"] == "two_tank_irrigation_recovery_command_failed"
    assert result["error_code"] == "command_timeout"
    assert result["feature_flag_state"] is True
    assert result["stop_result"]["success"] is True
    assert compensation_calls[0]["workflow"] == "irrigation_recovery"
    assert compensation_calls[0]["phase"] == "irrigation_recovery_start"
