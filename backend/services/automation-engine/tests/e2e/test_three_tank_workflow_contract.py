import pytest

from test_scheduler_task_executor import (
    test_execute_three_tank_unknown_workflow_fails_closed,
)


@pytest.mark.asyncio
async def test_e2e_25_three_tank_unsupported_workflow_reject():
    await test_execute_three_tank_unknown_workflow_fails_closed()
