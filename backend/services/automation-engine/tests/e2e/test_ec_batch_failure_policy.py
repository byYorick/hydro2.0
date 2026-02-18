import pytest

from test_correction_controller import (
    test_apply_correction_batch_aborts_when_command_unconfirmed_after_retries,
)


@pytest.mark.asyncio
async def test_e2e_22_ec_batch_partial_failure():
    await test_apply_correction_batch_aborts_when_command_unconfirmed_after_retries()
