import pytest

from test_scheduler_task_executor import (
    test_execute_two_tank_startup_compensates_stop_when_enqueue_fails,
    test_execute_two_tank_clean_fill_timeout_blocks_retry_when_stop_not_confirmed,
)


@pytest.mark.asyncio
async def test_e2e_17_enqueue_failure_compensating_stop():
    await test_execute_two_tank_startup_compensates_stop_when_enqueue_fails()


@pytest.mark.asyncio
async def test_e2e_18_stop_not_confirmed_no_restart():
    await test_execute_two_tank_clean_fill_timeout_blocks_retry_when_stop_not_confirmed()
