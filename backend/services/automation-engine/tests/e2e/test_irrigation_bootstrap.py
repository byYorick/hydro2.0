import pytest

from test_irrigation_controller import (
    test_check_and_control_irrigation_bootstrap_first_run_without_history,
)


@pytest.mark.asyncio
async def test_e2e_20_first_irrigation_bootstrap():
    await test_check_and_control_irrigation_bootstrap_first_run_without_history()
