import pytest

from test_zone_automation_service import (
    test_irrigation_event_persisted_only_after_publish_success,
)


@pytest.mark.asyncio
async def test_e2e_21_no_phantom_success_events():
    await test_irrigation_event_persisted_only_after_publish_success()
