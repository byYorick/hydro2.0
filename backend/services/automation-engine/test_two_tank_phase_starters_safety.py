from __future__ import annotations

import pytest

from executor.two_tank_phase_starters_prepare import start_two_tank_prepare_recirculation
from executor.two_tank_phase_starters_recovery import start_two_tank_irrigation_recovery
from executor.two_tank_phase_starters_startup import start_two_tank_solution_fill


async def _unexpected_async(*_args, **_kwargs):
    raise AssertionError("unexpected call")


def _unexpected_sync(*_args, **_kwargs):
    raise AssertionError("unexpected call")


def _runtime_cfg() -> dict:
    return {
        "commands": {
            "solution_fill_start": [{"channel": "pump_main", "cmd": "set_relay", "params": {"state": True}}],
            "prepare_recirculation_start": [{"channel": "pump_main", "cmd": "set_relay", "params": {"state": True}}],
            "irrigation_recovery_start": [{"channel": "pump_main", "cmd": "set_relay", "params": {"state": True}}],
        },
        "solution_fill_timeout_sec": 300,
        "prepare_recirculation_timeout_sec": 300,
        "irrigation_recovery_timeout_sec": 300,
        "poll_interval_sec": 30,
    }


@pytest.mark.asyncio
async def test_solution_fill_start_blocked_by_pump_safety(monkeypatch):
    async def fake_can_run_pump(*, zone_id, pump_channel, min_water_level=None, node_id=None):
        _ = (zone_id, pump_channel, min_water_level, node_id)
        return False, "Node offline"

    monkeypatch.setattr(
        "executor.two_tank_phase_starters_startup.can_run_pump",
        fake_can_run_pump,
    )

    result = await start_two_tank_solution_fill(
        zone_id=2,
        payload={},
        context={},
        runtime_cfg=_runtime_cfg(),
        dispatch_two_tank_command_plan_fn=_unexpected_async,
        dispatch_sensor_mode_command_for_nodes_fn=_unexpected_async,
        merge_command_dispatch_results_fn=_unexpected_sync,
        update_zone_workflow_phase_fn=_unexpected_async,
        enqueue_two_tank_check_fn=_unexpected_async,
        compensate_two_tank_start_enqueue_failure_fn=_unexpected_async,
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
    assert result["reason_code"] == "safety_blocked"
    assert result["error_code"] == "two_tank_pump_safety_blocked"
    assert result["mode"] == "two_tank_solution_fill_safety_blocked"


@pytest.mark.asyncio
async def test_solution_fill_start_enforces_pump_safety_when_feature_flag_disabled(monkeypatch):
    calls = {"count": 0}

    async def fake_can_run_pump(*, zone_id, pump_channel, min_water_level=None, node_id=None):
        _ = (zone_id, pump_channel, min_water_level, node_id)
        calls["count"] += 1
        return False, "Node offline"

    monkeypatch.setattr(
        "executor.two_tank_phase_starters_startup.can_run_pump",
        fake_can_run_pump,
    )

    result = await start_two_tank_solution_fill(
        zone_id=2,
        payload={},
        context={},
        runtime_cfg=_runtime_cfg(),
        dispatch_two_tank_command_plan_fn=_unexpected_async,
        dispatch_sensor_mode_command_for_nodes_fn=_unexpected_async,
        merge_command_dispatch_results_fn=_unexpected_sync,
        update_zone_workflow_phase_fn=_unexpected_async,
        enqueue_two_tank_check_fn=_unexpected_async,
        compensate_two_tank_start_enqueue_failure_fn=_unexpected_async,
        emit_task_event_fn=_unexpected_async,
        two_tank_safety_guards_enabled_fn=lambda: False,
        workflow_phase_tank_filling="tank_filling",
        reason_solution_fill_started="solution_fill_started",
        reason_cycle_refill_command_failed="cycle_refill_command_failed",
        reason_cycle_self_task_enqueue_failed="cycle_self_task_enqueue_failed",
        err_two_tank_command_failed="two_tank_command_failed",
        err_two_tank_enqueue_failed="two_tank_enqueue_failed",
    )

    assert calls["count"] == 1
    assert result["success"] is False
    assert result["mode"] == "two_tank_solution_fill_safety_blocked"


@pytest.mark.asyncio
async def test_prepare_recirculation_start_blocked_by_pump_safety(monkeypatch):
    async def fake_can_run_pump(*, zone_id, pump_channel, min_water_level=None, node_id=None):
        _ = (zone_id, pump_channel, min_water_level, node_id)
        return False, "Active critical alert"

    monkeypatch.setattr(
        "executor.two_tank_phase_starters_prepare.can_run_pump",
        fake_can_run_pump,
    )

    result = await start_two_tank_prepare_recirculation(
        zone_id=2,
        payload={},
        context={},
        runtime_cfg=_runtime_cfg(),
        dispatch_two_tank_command_plan_fn=_unexpected_async,
        dispatch_sensor_mode_command_for_nodes_fn=_unexpected_async,
        merge_command_dispatch_results_fn=_unexpected_sync,
        update_zone_workflow_phase_fn=_unexpected_async,
        enqueue_two_tank_check_fn=_unexpected_async,
        compensate_two_tank_start_enqueue_failure_fn=_unexpected_async,
        two_tank_safety_guards_enabled_fn=lambda: True,
        workflow_phase_tank_recirc="tank_recirc",
        reason_prepare_recirculation_started="prepare_recirculation_started",
        reason_cycle_refill_command_failed="cycle_refill_command_failed",
        reason_cycle_self_task_enqueue_failed="cycle_self_task_enqueue_failed",
        err_two_tank_command_failed="two_tank_command_failed",
        err_two_tank_enqueue_failed="two_tank_enqueue_failed",
    )

    assert result["success"] is False
    assert result["reason_code"] == "safety_blocked"
    assert result["error_code"] == "two_tank_pump_safety_blocked"
    assert result["mode"] == "two_tank_prepare_recirculation_safety_blocked"


@pytest.mark.asyncio
async def test_prepare_recirculation_start_enforces_pump_safety_when_feature_flag_disabled(monkeypatch):
    calls = {"count": 0}

    async def fake_can_run_pump(*, zone_id, pump_channel, min_water_level=None, node_id=None):
        _ = (zone_id, pump_channel, min_water_level, node_id)
        calls["count"] += 1
        return False, "Active critical alert"

    monkeypatch.setattr(
        "executor.two_tank_phase_starters_prepare.can_run_pump",
        fake_can_run_pump,
    )

    result = await start_two_tank_prepare_recirculation(
        zone_id=2,
        payload={},
        context={},
        runtime_cfg=_runtime_cfg(),
        dispatch_two_tank_command_plan_fn=_unexpected_async,
        dispatch_sensor_mode_command_for_nodes_fn=_unexpected_async,
        merge_command_dispatch_results_fn=_unexpected_sync,
        update_zone_workflow_phase_fn=_unexpected_async,
        enqueue_two_tank_check_fn=_unexpected_async,
        compensate_two_tank_start_enqueue_failure_fn=_unexpected_async,
        two_tank_safety_guards_enabled_fn=lambda: False,
        workflow_phase_tank_recirc="tank_recirc",
        reason_prepare_recirculation_started="prepare_recirculation_started",
        reason_cycle_refill_command_failed="cycle_refill_command_failed",
        reason_cycle_self_task_enqueue_failed="cycle_self_task_enqueue_failed",
        err_two_tank_command_failed="two_tank_command_failed",
        err_two_tank_enqueue_failed="two_tank_enqueue_failed",
    )

    assert calls["count"] == 1
    assert result["success"] is False
    assert result["mode"] == "two_tank_prepare_recirculation_safety_blocked"


@pytest.mark.asyncio
async def test_irrigation_recovery_start_blocked_by_pump_safety(monkeypatch):
    async def fake_can_run_pump(*, zone_id, pump_channel, min_water_level=None, node_id=None):
        _ = (zone_id, pump_channel, min_water_level, node_id)
        return False, "Too many recent failures"

    monkeypatch.setattr(
        "executor.two_tank_phase_starters_recovery.can_run_pump",
        fake_can_run_pump,
    )

    result = await start_two_tank_irrigation_recovery(
        zone_id=2,
        payload={},
        context={},
        runtime_cfg=_runtime_cfg(),
        attempt=1,
        dispatch_two_tank_command_plan_fn=_unexpected_async,
        update_zone_workflow_phase_fn=_unexpected_async,
        enqueue_two_tank_check_fn=_unexpected_async,
        compensate_two_tank_start_enqueue_failure_fn=_unexpected_async,
        two_tank_safety_guards_enabled_fn=lambda: True,
        workflow_phase_irrig_recirc="irrig_recirc",
        reason_irrigation_recovery_started="irrigation_recovery_started",
        reason_irrigation_recovery_failed="irrigation_recovery_failed",
        reason_cycle_self_task_enqueue_failed="cycle_self_task_enqueue_failed",
        err_two_tank_command_failed="two_tank_command_failed",
        err_two_tank_enqueue_failed="two_tank_enqueue_failed",
    )

    assert result["success"] is False
    assert result["reason_code"] == "safety_blocked"
    assert result["error_code"] == "two_tank_pump_safety_blocked"
    assert result["mode"] == "two_tank_irrigation_recovery_safety_blocked"


@pytest.mark.asyncio
async def test_irrigation_recovery_start_enforces_pump_safety_when_feature_flag_disabled(monkeypatch):
    calls = {"count": 0}

    async def fake_can_run_pump(*, zone_id, pump_channel, min_water_level=None, node_id=None):
        _ = (zone_id, pump_channel, min_water_level, node_id)
        calls["count"] += 1
        return False, "Too many recent failures"

    monkeypatch.setattr(
        "executor.two_tank_phase_starters_recovery.can_run_pump",
        fake_can_run_pump,
    )

    result = await start_two_tank_irrigation_recovery(
        zone_id=2,
        payload={},
        context={},
        runtime_cfg=_runtime_cfg(),
        attempt=1,
        dispatch_two_tank_command_plan_fn=_unexpected_async,
        update_zone_workflow_phase_fn=_unexpected_async,
        enqueue_two_tank_check_fn=_unexpected_async,
        compensate_two_tank_start_enqueue_failure_fn=_unexpected_async,
        two_tank_safety_guards_enabled_fn=lambda: False,
        workflow_phase_irrig_recirc="irrig_recirc",
        reason_irrigation_recovery_started="irrigation_recovery_started",
        reason_irrigation_recovery_failed="irrigation_recovery_failed",
        reason_cycle_self_task_enqueue_failed="cycle_self_task_enqueue_failed",
        err_two_tank_command_failed="two_tank_command_failed",
        err_two_tank_enqueue_failed="two_tank_enqueue_failed",
    )

    assert calls["count"] == 1
    assert result["success"] is False
    assert result["mode"] == "two_tank_irrigation_recovery_safety_blocked"
