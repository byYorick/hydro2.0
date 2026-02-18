import pytest

from test_irrigation_controller import (
    test_check_and_control_irrigation_blocked_by_workflow_phase,
)
from test_correction_controller import (
    test_ec_controller_check_and_correct_filters_components_to_npk_only,
    test_ec_controller_check_and_correct_filters_components_to_calmgmicro,
)
from test_zone_automation_service import (
    test_update_workflow_phase_resets_pid_on_transition_to_irrigating,
)
from test_scheduler_task_executor import (
    test_execute_two_tank_solution_fill_start_sends_sensor_mode_activation,
)


@pytest.mark.asyncio
async def test_e2e_09_no_irrigation_during_startup():
    await test_check_and_control_irrigation_blocked_by_workflow_phase()


@pytest.mark.asyncio
async def test_e2e_10_npk_only_during_tank_filling_tank_recirc():
    await test_ec_controller_check_and_correct_filters_components_to_npk_only()


@pytest.mark.asyncio
async def test_e2e_11_calmgmicro_during_irrigation():
    await test_ec_controller_check_and_correct_filters_components_to_calmgmicro()


@pytest.mark.asyncio
async def test_e2e_12_pid_reset_on_phase_change():
    await test_update_workflow_phase_resets_pid_on_transition_to_irrigating()


@pytest.mark.asyncio
async def test_e2e_13_sensor_mode_from_workflow():
    await test_execute_two_tank_solution_fill_start_sends_sensor_mode_activation()
