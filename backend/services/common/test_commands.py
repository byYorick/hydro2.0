from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_mark_command_timeout_returns_true_when_row_updated():
    from common.commands import mark_command_timeout

    with patch("common.commands.execute", new=AsyncMock(return_value="UPDATE 1")) as mock_execute:
        transitioned = await mark_command_timeout("cmd-timeout-1")

    assert transitioned is True
    mock_execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_command_timeout_returns_false_when_no_rows_updated():
    from common.commands import mark_command_timeout

    with patch("common.commands.execute", new=AsyncMock(return_value="UPDATE 0")):
        transitioned = await mark_command_timeout("cmd-timeout-2")

    assert transitioned is False


@pytest.mark.asyncio
async def test_mark_command_send_failed_returns_true_when_row_updated():
    from common.commands import mark_command_send_failed

    with patch("common.commands.execute", new=AsyncMock(return_value="UPDATE 1")) as mock_execute:
        transitioned = await mark_command_send_failed("cmd-send-failed-1", error_message="publish_failed")

    assert transitioned is True
    mock_execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_command_send_failed_returns_false_when_no_rows_updated():
    from common.commands import mark_command_send_failed

    with patch("common.commands.execute", new=AsyncMock(return_value="UPDATE 0")):
        transitioned = await mark_command_send_failed("cmd-send-failed-2", error_message="publish_failed")

    assert transitioned is False
