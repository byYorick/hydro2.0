"""Tests for command status delivery queue behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from common.command_status_queue import CommandStatus, send_status_to_laravel


class _ResponseStub:
    def __init__(self, status_code: int, text: str = "", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON payload")
        return self._payload


@pytest.mark.asyncio
async def test_send_status_to_laravel_success_does_not_enqueue():
    settings = SimpleNamespace(
        laravel_api_url="http://laravel",
        history_logger_api_token="token",
        ingest_token="token",
    )
    queue = AsyncMock()

    with patch("common.command_status_queue.get_settings", return_value=settings), \
         patch("common.command_status_queue.make_request", new=AsyncMock(return_value=_ResponseStub(200, "ok"))), \
         patch("common.command_status_queue.get_status_queue", new=AsyncMock(return_value=queue)):
        ok = await send_status_to_laravel("cmd-1", CommandStatus.SENT, {"zone_id": 1})

    assert ok is True
    queue.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_send_status_to_laravel_queues_and_alerts_on_command_not_found():
    settings = SimpleNamespace(
        laravel_api_url="http://laravel",
        history_logger_api_token="token",
        ingest_token="token",
    )
    queue = AsyncMock()
    response = _ResponseStub(
        404,
        text='{"status":"error","code":"COMMAND_NOT_FOUND"}',
        payload={"status": "error", "code": "COMMAND_NOT_FOUND", "message": "Command not found"},
    )

    with patch("common.command_status_queue.get_settings", return_value=settings), \
         patch("common.command_status_queue.make_request", new=AsyncMock(return_value=response)), \
         patch("common.command_status_queue.get_status_queue", new=AsyncMock(return_value=queue)), \
         patch("common.command_status_queue._emit_command_ack_not_found_alert", new=AsyncMock()) as mock_alert:
        ok = await send_status_to_laravel(
            "cmd-missing",
            CommandStatus.SENT,
            {"zone_id": 7, "node_uid": "nd-1", "channel": "pump_1"},
        )

    assert ok is False
    queue.enqueue.assert_awaited_once()
    mock_alert.assert_awaited_once()

