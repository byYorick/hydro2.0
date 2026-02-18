import pytest

from test_scheduler_task_executor import (
    test_execute_irrigation_two_tank_failure_starts_recovery_workflow,
    test_execute_two_tank_irrigation_recovery_timeout_blocks_restart_when_stop_not_confirmed,
    test_execute_two_tank_irrigation_recovery_check_attempts_exceeded,
)


@pytest.mark.asyncio
async def test_e2e_06_recovery_success_drift_to_targets_reached():
    await test_execute_irrigation_two_tank_failure_starts_recovery_workflow()


@pytest.mark.asyncio
async def test_e2e_07_recovery_degraded_timeout_degraded_ok():
    await test_execute_two_tank_irrigation_recovery_timeout_blocks_restart_when_stop_not_confirmed()


@pytest.mark.asyncio
async def test_e2e_08_recovery_max_attempts_fail():
    await test_execute_two_tank_irrigation_recovery_check_attempts_exceeded()
