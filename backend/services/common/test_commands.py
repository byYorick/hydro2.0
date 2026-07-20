from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_send_command_uses_cmd_field_for_history_logger_request():
    from common.command_orchestrator import send_command

    # MagicMock (not AsyncMock) because httpx Response.json() is synchronous.
    # AsyncMock would make .json() return a coroutine that is never awaited,
    # triggering RuntimeWarning: coroutine was never awaited.
    mock_response = MagicMock()
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
async def test_mark_command_sent_backfills_ack_stub_without_status_regression():
    from common.commands import mark_command_sent

    execute_mock = AsyncMock(side_effect=["UPDATE 0", "UPDATE 1"])
    with patch("common.commands.execute", new=execute_mock), \
         patch("common.commands.fetch", new=AsyncMock()) as fetch_mock:
        transitioned = await mark_command_sent("cmd-ack-stub")

    assert transitioned is True
    assert execute_mock.await_count == 2
    ack_backfill_query = execute_mock.await_args_list[1].args[0]
    assert "SET sent_at=NOW(), updated_at=NOW()" in ack_backfill_query
    assert "status='SENT'" not in ack_backfill_query
    assert "status = 'ACK' AND sent_at IS NULL" in ack_backfill_query
    fetch_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_command_sent_idempotent_when_already_ack_with_sent_at():
    from common.commands import mark_command_sent

    execute_mock = AsyncMock(side_effect=["UPDATE 0", "UPDATE 0"])
    fetch_mock = AsyncMock(return_value=[{"status": "ACK", "sent_at": "2026-07-20T12:00:00Z"}])
    with patch("common.commands.execute", new=execute_mock), \
         patch("common.commands.fetch", new=fetch_mock):
        transitioned = await mark_command_sent("cmd-ack-raced")

    assert transitioned is True
    fetch_mock.assert_awaited_once()
    # No extra backfill — sent_at already set
    assert execute_mock.await_count == 2


@pytest.mark.asyncio
async def test_mark_command_sent_idempotent_when_already_terminal_done():
    from common.commands import mark_command_sent

    execute_mock = AsyncMock(side_effect=["UPDATE 0", "UPDATE 0"])
    fetch_mock = AsyncMock(return_value=[{"status": "DONE", "sent_at": "2026-07-20T12:00:00Z"}])
    with patch("common.commands.execute", new=execute_mock), \
         patch("common.commands.fetch", new=fetch_mock):
        transitioned = await mark_command_sent("cmd-done-raced")

    assert transitioned is True
    fetch_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_command_sent_idempotent_for_each_terminal_after_publish():
    from common.commands import mark_command_sent

    for status in ("DONE", "NO_EFFECT", "ERROR", "INVALID", "BUSY", "TIMEOUT"):
        execute_mock = AsyncMock(side_effect=["UPDATE 0", "UPDATE 0"])
        fetch_mock = AsyncMock(return_value=[{"status": status, "sent_at": None}])
        with patch("common.commands.execute", new=execute_mock), \
             patch("common.commands.fetch", new=fetch_mock):
            assert await mark_command_sent(f"cmd-{status.lower()}") is True


@pytest.mark.asyncio
async def test_mark_command_sent_still_raises_when_send_failed_without_resend():
    from common.commands import MarkCommandSentError, mark_command_sent

    execute_mock = AsyncMock(return_value="UPDATE 0")
    fetch_mock = AsyncMock(return_value=[{"status": "SEND_FAILED", "sent_at": None}])
    with patch("common.commands.execute", new=execute_mock), \
         patch("common.commands.fetch", new=fetch_mock):
        with pytest.raises(MarkCommandSentError):
            await mark_command_sent("cmd-send-failed", allow_resend=False)

    execute_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_command_sent_queued_to_sent_still_works():
    from common.commands import mark_command_sent

    execute_mock = AsyncMock(return_value="UPDATE 1")
    with patch("common.commands.execute", new=execute_mock), \
         patch("common.commands.fetch", new=AsyncMock()) as fetch_mock:
        assert await mark_command_sent("cmd-queued") is True

    assert "status='SENT'" in execute_mock.await_args.args[0]
    assert "QUEUED" in execute_mock.await_args.args[0]
    fetch_mock.assert_not_awaited()


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
