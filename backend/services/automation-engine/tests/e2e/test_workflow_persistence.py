import pytest

from test_api import (
    test_recover_zone_workflow_states_enqueues_continuation_for_active_phase,
)


@pytest.mark.asyncio
async def test_e2e_19_workflow_recovery_after_restart():
    await test_recover_zone_workflow_states_enqueues_continuation_for_active_phase()
