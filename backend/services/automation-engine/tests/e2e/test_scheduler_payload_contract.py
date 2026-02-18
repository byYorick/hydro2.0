import pytest

from test_scheduler_task_executor import (
    test_execute_three_tank_missing_workflow_fails_payload_validation,
)


@pytest.mark.asyncio
async def test_e2e_27_missing_workflow_in_payload_fail_closed():
    await test_execute_three_tank_missing_workflow_fails_payload_validation()
