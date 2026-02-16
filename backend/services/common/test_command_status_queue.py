"""Tests for command status delivery queue behavior."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from common.command_status_queue import (
    CommandStatus,
    StatusUpdateQueue,
    _PENDING_STATUS_UPDATES_DLQ_REQUIRED_COLUMNS,
    _PENDING_STATUS_UPDATES_REQUIRED_COLUMNS,
    _decode_details_payload,
    normalize_status,
    retry_worker,
    send_status_to_laravel,
)


class _ResponseStub:
    def __init__(self, status_code: int, text: str = "", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON payload")
        return self._payload


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _PoolStub:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _AcquireCtx(self._conn)


class _SchemaConnStub:
    def __init__(self, columns_by_table):
        self.columns_by_table = columns_by_table

    async def fetch(self, query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from information_schema.columns" in normalized:
            table_name = args[0] if args else None
            return [
                {"column_name": column}
                for column in self.columns_by_table.get(table_name, [])
            ]
        return []


def test_decode_details_payload_accepts_dict_and_json_string():
    dict_payload = {"zone_id": 11, "node_uid": "nd-1"}
    assert _decode_details_payload(dict_payload) == dict_payload
    assert _decode_details_payload('{"zone_id": 11, "node_uid": "nd-1"}') == dict_payload


def test_decode_details_payload_handles_invalid_string():
    decoded = _decode_details_payload("{bad-json")
    assert decoded == {"raw_details": "{bad-json"}


def test_normalize_status_rejects_legacy_accepted_alias():
    assert normalize_status("ACCEPTED") is None
    assert normalize_status("FAILED") is None


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


@pytest.mark.asyncio
async def test_send_status_to_laravel_does_not_enqueue_when_disabled():
    settings = SimpleNamespace(
        laravel_api_url="http://laravel",
        history_logger_api_token="token",
        ingest_token="token",
    )
    queue = AsyncMock()
    response = _ResponseStub(500, text='{"status":"error"}')

    with patch("common.command_status_queue.get_settings", return_value=settings), \
         patch("common.command_status_queue.make_request", new=AsyncMock(return_value=response)), \
         patch("common.command_status_queue.get_status_queue", new=AsyncMock(return_value=queue)):
        ok = await send_status_to_laravel(
            "cmd-fail",
            CommandStatus.ACK,
            {"zone_id": 3},
            enqueue_on_failure=False,
        )

    assert ok is False
    queue.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_send_status_to_laravel_missing_url_does_not_enqueue_when_disabled():
    settings = SimpleNamespace(
        laravel_api_url=None,
        history_logger_api_token="token",
        ingest_token="token",
    )
    queue = AsyncMock()

    with patch("common.command_status_queue.get_settings", return_value=settings), \
         patch("common.command_status_queue.get_status_queue", new=AsyncMock(return_value=queue)):
        ok = await send_status_to_laravel(
            "cmd-no-url",
            CommandStatus.ACK,
            {"zone_id": 8},
            enqueue_on_failure=False,
        )

    assert ok is False
    queue.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_retry_worker_passes_shutdown_quickly_on_processing_pause():
    shutdown_event = asyncio.Event()
    queue = AsyncMock()
    pending_item = (
        101,               # update_id
        "cmd-101",        # cmd_id
        CommandStatus.ACK, # status
        {"zone_id": 5},   # details
        0,                 # retry_count
        3,                 # max_attempts
        None,              # last_error
    )

    calls = {"count": 0}

    async def _get_pending(limit=50):
        if calls["count"] == 0:
            calls["count"] += 1
            return [pending_item]
        shutdown_event.set()
        return []

    queue.get_pending = AsyncMock(side_effect=_get_pending)

    with patch("common.command_status_queue.get_status_queue", new=AsyncMock(return_value=queue)), \
         patch("common.command_status_queue.send_status_to_laravel", new=AsyncMock(return_value=False)) as mock_send, \
         patch("common.command_status_queue.calculate_backoff_with_jitter", return_value=1):
        await asyncio.wait_for(retry_worker(interval=0.01, shutdown_event=shutdown_event), timeout=1.0)

    mock_send.assert_awaited_once()
    assert mock_send.await_args.kwargs["enqueue_on_failure"] is False
    queue.mark_retry.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_table_validates_schema_from_laravel_migrations():
    queue = StatusUpdateQueue()
    schema_conn = _SchemaConnStub(
        {
            "pending_status_updates": sorted(_PENDING_STATUS_UPDATES_REQUIRED_COLUMNS),
            "pending_status_updates_dlq": sorted(
                _PENDING_STATUS_UPDATES_DLQ_REQUIRED_COLUMNS
            ),
        }
    )

    with patch("common.command_status_queue.get_pool", new=AsyncMock(return_value=_PoolStub(schema_conn))):
        await queue.ensure_table()

    assert queue._initialized is True


@pytest.mark.asyncio
async def test_ensure_table_fails_when_required_columns_missing():
    queue = StatusUpdateQueue()
    schema_conn = _SchemaConnStub(
        {
            "pending_status_updates": sorted(
                _PENDING_STATUS_UPDATES_REQUIRED_COLUMNS - {"moved_to_dlq_at"}
            ),
            "pending_status_updates_dlq": sorted(
                _PENDING_STATUS_UPDATES_DLQ_REQUIRED_COLUMNS
            ),
        }
    )

    with patch("common.command_status_queue.get_pool", new=AsyncMock(return_value=_PoolStub(schema_conn))):
        with pytest.raises(RuntimeError, match="pending_status_updates"):
            await queue.ensure_table()

    assert queue._schema_error is not None


@pytest.mark.asyncio
async def test_ensure_table_retries_after_transient_pool_error():
    queue = StatusUpdateQueue()
    schema_conn = _SchemaConnStub(
        {
            "pending_status_updates": sorted(_PENDING_STATUS_UPDATES_REQUIRED_COLUMNS),
            "pending_status_updates_dlq": sorted(
                _PENDING_STATUS_UPDATES_DLQ_REQUIRED_COLUMNS
            ),
        }
    )

    with patch(
        "common.command_status_queue.get_pool",
        new=AsyncMock(
            side_effect=[RuntimeError("db temporarily unavailable"), _PoolStub(schema_conn)]
        ),
    ):
        with pytest.raises(RuntimeError, match="temporary infrastructure error"):
            await queue.ensure_table()
        await queue.ensure_table()

    assert queue._schema_error is None
    assert queue._initialized is True
