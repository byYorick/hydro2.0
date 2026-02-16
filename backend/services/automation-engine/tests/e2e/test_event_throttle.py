import pytest

from test_zone_automation_service import (
    test_process_correction_controllers_missing_flags_events_are_throttled,
)


@pytest.mark.asyncio
async def test_e2e_23_correction_skip_throttle():
    await test_process_correction_controllers_missing_flags_events_are_throttled()
