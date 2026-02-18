import pytest

from test_zone_automation_service import (
    test_process_correction_controllers_skips_when_flags_stale_and_deactivates_sensor_mode,
)


@pytest.mark.asyncio
async def test_e2e_24_stale_correction_flags_fail_closed():
    await test_process_correction_controllers_skips_when_flags_stale_and_deactivates_sensor_mode()
