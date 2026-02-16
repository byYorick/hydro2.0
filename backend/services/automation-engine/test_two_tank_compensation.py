"""Unit tests for application.two_tank_compensation helpers."""

from unittest.mock import AsyncMock, Mock

import pytest

from application.two_tank_compensation import compensate_two_tank_start_enqueue_failure


@pytest.mark.asyncio
async def test_compensate_two_tank_start_enqueue_failure_happy_path():
    dispatch = AsyncMock(return_value={"success": True})
    merge = AsyncMock(return_value={"success": True})
    log_guard = Mock()

    result = await compensate_two_tank_start_enqueue_failure(
        zone_id=1,
        context={"task_id": "st-1"},
        workflow="startup",
        phase="clean_fill",
        stop_command_plan=[{"channel": "pump_main", "cmd": "set", "params": {"state": False}}],
        reason_code_cycle_refill_command_failed="cycle_refill_command_failed",
        dispatch_two_tank_command_plan_fn=dispatch,
        merge_with_sensor_mode_deactivate_fn=merge,
        log_two_tank_safety_guard_fn=log_guard,
    )

    assert result["success"] is True
    dispatch.assert_awaited_once()
    merge.assert_awaited_once()
    log_guard.assert_called_once()
