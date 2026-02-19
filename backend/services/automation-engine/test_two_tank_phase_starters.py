"""Unit tests for application.two_tank_phase_starters helpers."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

from application.two_tank_phase_starters import (
    start_two_tank_clean_fill,
    start_two_tank_irrigation_recovery,
    start_two_tank_prepare_recirculation,
    start_two_tank_solution_fill,
)


def _runtime_cfg():
    return {
        "commands": {
            "clean_fill_start": [{"channel": "valve_clean_fill"}],
            "clean_fill_stop": [{"channel": "valve_clean_fill"}],
            "solution_fill_start": [{"channel": "valve_solution_fill"}],
            "solution_fill_stop": [{"channel": "valve_solution_fill"}],
            "prepare_recirculation_start": [{"channel": "valve_solution_supply"}],
            "prepare_recirculation_stop": [{"channel": "valve_solution_supply"}],
            "irrigation_recovery_start": [{"channel": "pump_main"}],
            "irrigation_recovery_stop": [{"channel": "pump_main"}],
        },
        "clean_fill_timeout_sec": 60,
        "solution_fill_timeout_sec": 60,
        "prepare_recirculation_timeout_sec": 60,
        "irrigation_recovery_timeout_sec": 60,
        "irrigation_recovery_retry_timeout_multiplier": 1.5,
        "poll_interval_sec": 30,
    }


def _reason_kwargs():
    return {
        "reason_cycle_refill_command_failed": "cycle_refill_command_failed",
        "reason_cycle_self_task_enqueue_failed": "cycle_self_task_enqueue_failed",
        "err_two_tank_command_failed": "two_tank_command_failed",
        "err_two_tank_enqueue_failed": "two_tank_enqueue_failed",
    }


def test_start_two_tank_clean_fill_success():
    result = asyncio.run(
        start_two_tank_clean_fill(
            zone_id=1,
            payload={},
            context={},
            runtime_cfg=_runtime_cfg(),
            cycle=1,
            dispatch_two_tank_command_plan_fn=AsyncMock(return_value={"success": True}),
            enqueue_two_tank_check_fn=AsyncMock(return_value={"ok": True}),
            compensate_two_tank_start_enqueue_failure_fn=AsyncMock(return_value={"ok": True}),
            emit_task_event_fn=AsyncMock(return_value=None),
            two_tank_safety_guards_enabled_fn=lambda: True,
            reason_clean_fill_started="clean_fill_started",
            **_reason_kwargs(),
        )
    )
    assert result["success"] is True
    assert result["mode"] == "two_tank_clean_fill_in_progress"


def test_start_two_tank_solution_fill_returns_error_when_sensor_mode_failed():
    result = asyncio.run(
        start_two_tank_solution_fill(
            zone_id=1,
            payload={},
            context={},
            runtime_cfg=_runtime_cfg(),
            dispatch_two_tank_command_plan_fn=AsyncMock(return_value={"success": True}),
            dispatch_sensor_mode_command_for_nodes_fn=AsyncMock(return_value={"success": False, "error_code": "x"}),
            merge_command_dispatch_results_fn=lambda *_: {"success": False, "error_code": "x"},
            update_zone_workflow_phase_fn=AsyncMock(return_value=None),
            enqueue_two_tank_check_fn=AsyncMock(return_value={"ok": True}),
            compensate_two_tank_start_enqueue_failure_fn=AsyncMock(return_value={"ok": True}),
            emit_task_event_fn=AsyncMock(return_value=None),
            two_tank_safety_guards_enabled_fn=lambda: True,
            workflow_phase_tank_filling="tank_filling",
            reason_solution_fill_started="solution_fill_started",
            **_reason_kwargs(),
        )
    )
    assert result["success"] is False
    assert result["mode"] == "two_tank_solution_fill_sensor_mode_failed"


def test_start_two_tank_prepare_recirculation_success():
    result = asyncio.run(
        start_two_tank_prepare_recirculation(
            zone_id=1,
            payload={},
            context={},
            runtime_cfg=_runtime_cfg(),
            dispatch_two_tank_command_plan_fn=AsyncMock(return_value={"success": True}),
            dispatch_sensor_mode_command_for_nodes_fn=AsyncMock(return_value={"success": True}),
            merge_command_dispatch_results_fn=lambda *_: {"success": True, "commands_total": 2, "commands_failed": 0},
            update_zone_workflow_phase_fn=AsyncMock(return_value=None),
            enqueue_two_tank_check_fn=AsyncMock(return_value={"ok": True}),
            compensate_two_tank_start_enqueue_failure_fn=AsyncMock(return_value={"ok": True}),
            two_tank_safety_guards_enabled_fn=lambda: True,
            workflow_phase_tank_recirc="tank_recirc",
            reason_prepare_recirculation_started="prepare_recirculation_started",
            **_reason_kwargs(),
        )
    )
    assert result["success"] is True
    assert result["mode"] == "two_tank_prepare_recirculation_in_progress"


def test_start_two_tank_irrigation_recovery_success():
    result = asyncio.run(
        start_two_tank_irrigation_recovery(
            zone_id=1,
            payload={},
            context={},
            runtime_cfg=_runtime_cfg(),
            attempt=2,
            dispatch_two_tank_command_plan_fn=AsyncMock(return_value={"success": True}),
            update_zone_workflow_phase_fn=AsyncMock(return_value=None),
            enqueue_two_tank_check_fn=AsyncMock(return_value={"ok": True}),
            compensate_two_tank_start_enqueue_failure_fn=AsyncMock(return_value={"ok": True}),
            two_tank_safety_guards_enabled_fn=lambda: True,
            workflow_phase_irrig_recirc="irrig_recirc",
            reason_irrigation_recovery_started="irrigation_recovery_started",
            reason_irrigation_recovery_failed="irrigation_recovery_failed",
            reason_cycle_self_task_enqueue_failed="cycle_self_task_enqueue_failed",
            err_two_tank_command_failed="two_tank_command_failed",
            err_two_tank_enqueue_failed="two_tank_enqueue_failed",
        )
    )
    assert result["success"] is True
    assert result["irrigation_recovery_attempt"] == 2
    started_at = datetime.fromisoformat(result["irrigation_recovery_started_at"])
    timeout_at = datetime.fromisoformat(result["irrigation_recovery_timeout_at"])
    assert int((timeout_at - started_at).total_seconds()) == 90
