import pytest

from test_scheduler_task_executor import (
    test_execute_two_tank_solution_fill_start_sends_sensor_mode_activation,
    test_execute_two_tank_solution_fill_timeout_sends_sensor_mode_deactivation,
)


@pytest.mark.asyncio
async def test_e2e_26_sensor_mode_lifecycle():
    await test_execute_two_tank_solution_fill_start_sends_sensor_mode_activation()
    await test_execute_two_tank_solution_fill_timeout_sends_sensor_mode_deactivation()
