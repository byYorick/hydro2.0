from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_send_command_uses_cmd_field_for_history_logger_request():
    from common.command_orchestrator import send_command

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "ok"}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("common.command_orchestrator.fetch", new=AsyncMock(return_value=[])), \
         patch("common.command_orchestrator.execute", new=AsyncMock(return_value="INSERT 0 1")), \
         patch("common.command_orchestrator.get_settings") as mock_settings, \
         patch("common.command_orchestrator.httpx.AsyncClient", return_value=mock_client), \
         patch("common.command_orchestrator.mark_command_send_failed", new=AsyncMock()) as mock_mark_failed:
        mock_settings.return_value.history_logger_url = "http://history-logger:9300"
        mock_settings.return_value.history_logger_api_token = "test-token"

        result = await send_command(
            zone_id=1,
            node_uid="nd-irrig-1",
            channel="pump_main",
            cmd="run_pump",
            params={"duration_ms": 15000},
            greenhouse_uid="gh-1",
            cmd_id="cmd-test-1",
        )

    assert result["status"] == "sent"
    mock_mark_failed.assert_not_awaited()
    post_kwargs = mock_client.post.await_args.kwargs
    assert post_kwargs["json"]["cmd"] == "run_pump"
    assert "type" not in post_kwargs["json"]


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
