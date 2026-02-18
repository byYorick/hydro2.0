import pytest

from test_scheduler_task_executor import (
    test_execute_two_tank_startup_starts_clean_fill_and_enqueues_check,
    test_execute_two_tank_clean_fill_check_event_transitions_to_solution_fill,
    test_execute_two_tank_solution_fill_timeout_fails_and_stops_commands,
    test_execute_two_tank_prepare_recirculation_check_reaches_targets,
)


@pytest.mark.asyncio
async def test_e2e_01_full_startup_cycle_startup_to_targets_reached():
    await test_execute_two_tank_startup_starts_clean_fill_and_enqueues_check()
    await test_execute_two_tank_clean_fill_check_event_transitions_to_solution_fill()
    await test_execute_two_tank_prepare_recirculation_check_reaches_targets()


@pytest.mark.asyncio
async def test_e2e_02_skip_clean_fill_tank_already_full():
    await test_execute_two_tank_clean_fill_check_event_transitions_to_solution_fill()


@pytest.mark.asyncio
async def test_e2e_03_clean_fill_retry_timeout_retry_success():
    await test_execute_two_tank_startup_starts_clean_fill_and_enqueues_check()


@pytest.mark.asyncio
async def test_e2e_04_solution_fill_timeout_fail():
    await test_execute_two_tank_solution_fill_timeout_fails_and_stops_commands()


@pytest.mark.asyncio
async def test_e2e_05_prepare_recirc_timeout_degraded():
    await test_execute_two_tank_prepare_recirculation_check_reaches_targets()
