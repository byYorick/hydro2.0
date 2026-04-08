"""Tests for command status delivery queue behavior."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from common.command_status_queue import (
    CommandStatus,
    StatusDeliveryResult,
    StatusUpdateQueue,
    deliver_status_to_laravel,
    _PENDING_STATUS_UPDATES_DLQ_REQUIRED_COLUMNS,
    _PENDING_STATUS_UPDATES_REQUIRED_COLUMNS,
    _decode_details_payload,
    _sanitize_status_details,
    normalize_status,
    repair_stuck_commands_once,
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


class _PendingConnStub:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, query, *args):
        return self._rows


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


def test_normalize_status_accepts_timeout_and_send_failed():
    assert normalize_status("TIMEOUT") == CommandStatus.TIMEOUT
    assert normalize_status("send_failed") == CommandStatus.SEND_FAILED


def test_sanitize_status_details_strips_simulation_only_keys():
    sanitized = _sanitize_status_details({
        "virtual": True,
        "delta_ph": -0.5,
        "phase_factor": 2.0,
        "ph_after": 5.9,
        "zone_id": 7,
        "snapshot": {"pump_main": True},
    })

    assert sanitized == {
        "zone_id": 7,
        "snapshot": {"pump_main": True},
    }


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
async def test_send_status_to_laravel_strips_simulation_fields_before_delivery():
    settings = SimpleNamespace(
        laravel_api_url="http://laravel",
        history_logger_api_token="token",
        ingest_token="token",
    )
    queue = AsyncMock()

    with patch("common.command_status_queue.get_settings", return_value=settings), \
         patch("common.command_status_queue.make_request", new=AsyncMock(return_value=_ResponseStub(200, "ok"))) as mock_request, \
         patch("common.command_status_queue.get_status_queue", new=AsyncMock(return_value=queue)):
        ok = await send_status_to_laravel(
            "cmd-sim-details",
            CommandStatus.DONE,
            {
                "virtual": True,
                "delta_ec": 0.4,
                "ec_after": 1.3,
                "zone_id": 1,
                "node_uid": "nd-test-ec-1",
            },
        )

    assert ok is True
    queue.enqueue.assert_not_called()
    payload = mock_request.await_args.kwargs["json"]
    assert payload["details"] == {
        "zone_id": 1,
        "node_uid": "nd-test-ec-1",
    }


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
async def test_deliver_status_to_laravel_marks_dropped_when_retry_enqueue_fails():
    settings = SimpleNamespace(
        laravel_api_url="http://laravel",
        history_logger_api_token="token",
        ingest_token="token",
    )
    queue = AsyncMock()
    queue.enqueue.return_value = False
    queue.get_queue_metrics.return_value = {"size": 3, "dlq_size": 1}
    response = _ResponseStub(500, text='{"status":"error"}')

    with patch("common.command_status_queue.get_settings", return_value=settings), \
         patch("common.command_status_queue.make_request", new=AsyncMock(return_value=response)), \
         patch("common.command_status_queue.get_status_queue", new=AsyncMock(return_value=queue)), \
         patch("common.command_status_queue._emit_status_retry_enqueue_failed_alert", new=AsyncMock()) as mock_alert:
        result = await deliver_status_to_laravel(
            "cmd-enqueue-fail",
            CommandStatus.ERROR,
            {"zone_id": 7, "node_uid": "nd-1", "channel": "pump_1"},
        )

    assert result.delivered is False
    assert result.queued is False
    assert result.dropped is True
    assert result.reason == "http_500"
    assert result.http_status == 500
    assert result.queue_error == "queue_enqueue_failed"
    queue.enqueue.assert_awaited_once()
    queue.get_queue_metrics.assert_awaited_once()
    mock_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_status_to_laravel_ignores_command_not_found_for_e2e_cmd():
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
            "e2e:cmd-missing",
            CommandStatus.ACK,
            {"zone_id": 7, "node_uid": "nd-1", "channel": "pump_1"},
        )

    assert ok is True
    queue.enqueue.assert_not_called()
    mock_alert.assert_not_awaited()


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
         patch("common.command_status_queue.calculate_backoff_with_jitter", return_value=1), \
         patch("common.command_status_queue.record_command_status_retry") as mock_record_metric, \
         patch("common.command_status_queue.update_command_status_retry_scan") as mock_update_scan:
        await asyncio.wait_for(retry_worker(interval=0.01, shutdown_event=shutdown_event), timeout=1.0)

    mock_send.assert_awaited_once()
    assert mock_send.await_args.kwargs["enqueue_on_failure"] is False
    queue.mark_retry.assert_awaited_once()
    mock_record_metric.assert_called_once_with(outcome="retry_scheduled", status="ACK")
    assert any(
        kwargs == {
            "processed": 1,
            "delivered": 0,
            "retry_scheduled": 1,
            "dlq_moved": 0,
            "dlq_move_failed": 0,
        }
        for _, kwargs in mock_update_scan.call_args_list
    )


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
async def test_ensure_table_revalidates_after_schema_error_backoff():
    queue = StatusUpdateQueue()
    queue._schema_retry_interval_sec = 5.0

    bad_schema_conn = _SchemaConnStub(
        {
            "pending_status_updates": sorted(
                _PENDING_STATUS_UPDATES_REQUIRED_COLUMNS - {"moved_to_dlq_at"}
            ),
            "pending_status_updates_dlq": sorted(
                _PENDING_STATUS_UPDATES_DLQ_REQUIRED_COLUMNS
            ),
        }
    )
    good_schema_conn = _SchemaConnStub(
        {
            "pending_status_updates": sorted(_PENDING_STATUS_UPDATES_REQUIRED_COLUMNS),
            "pending_status_updates_dlq": sorted(
                _PENDING_STATUS_UPDATES_DLQ_REQUIRED_COLUMNS
            ),
        }
    )
    pool_mock = AsyncMock(
        side_effect=[_PoolStub(bad_schema_conn), _PoolStub(good_schema_conn)]
    )

    with patch("common.command_status_queue.get_pool", new=pool_mock), patch(
        "common.command_status_queue.time.monotonic",
        side_effect=[100.0, 105.0, 106.0, 111.0],
    ):
        with pytest.raises(RuntimeError, match="pending_status_updates"):
            await queue.ensure_table()
        with pytest.raises(RuntimeError, match="pending_status_updates"):
            await queue.ensure_table()
        await queue.ensure_table()

    assert pool_mock.await_count == 2
    assert queue._initialized is True
    assert queue._schema_error is None


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


@pytest.mark.asyncio
async def test_get_pending_quarantines_invalid_status_row():
    queue = StatusUpdateQueue()
    queue.ensure_table = AsyncMock(return_value=None)
    queue.move_to_dlq = AsyncMock(return_value=True)
    queue.mark_delivered = AsyncMock(return_value=None)

    rows = [
        {
            "id": 1,
            "cmd_id": "cmd-ok",
            "status": "ACK",
            "details": {"zone_id": 1},
            "retry_count": 0,
            "max_attempts": 10,
            "last_error": None,
        },
        {
            "id": 2,
            "cmd_id": "cmd-bad",
            "status": "ACCEPTED",
            "details": {"zone_id": 2},
            "retry_count": 3,
            "max_attempts": 10,
            "last_error": "old_error",
        },
    ]
    pool = _PoolStub(_PendingConnStub(rows))

    with patch("common.command_status_queue.get_pool", new=AsyncMock(return_value=pool)):
        pending = await queue.get_pending(limit=50)

    assert len(pending) == 1
    assert pending[0][1] == "cmd-ok"
    assert pending[0][2] == CommandStatus.ACK
    queue.move_to_dlq.assert_awaited_once()
    queue.mark_delivered.assert_awaited_once_with(2)


@pytest.mark.asyncio
async def test_retry_worker_does_not_delete_pending_when_dlq_move_fails():
    shutdown_event = asyncio.Event()
    queue = AsyncMock()
    pending_item = (
        501,
        "cmd-501",
        CommandStatus.ACK,
        {"zone_id": 9},
        2,  # retry_count
        3,  # max_attempts => next retry reaches max
        "prev_error",
    )

    calls = {"count": 0}

    async def _get_pending(limit=50):
        if calls["count"] == 0:
            calls["count"] += 1
            return [pending_item]
        shutdown_event.set()
        return []

    queue.get_pending = AsyncMock(side_effect=_get_pending)
    queue.move_to_dlq = AsyncMock(return_value=False)
    queue.mark_delivered = AsyncMock()
    queue.mark_retry = AsyncMock()

    with patch("common.command_status_queue.get_status_queue", new=AsyncMock(return_value=queue)), \
         patch("common.command_status_queue.send_status_to_laravel", new=AsyncMock(return_value=False)), \
         patch("common.command_status_queue.calculate_backoff_with_jitter", return_value=1), \
         patch("common.command_status_queue.record_command_status_retry") as mock_record_metric, \
         patch("common.command_status_queue.update_command_status_retry_scan") as mock_update_scan:
        await asyncio.wait_for(retry_worker(interval=0.01, shutdown_event=shutdown_event), timeout=1.0)

    queue.move_to_dlq.assert_awaited_once()
    queue.mark_delivered.assert_not_awaited()
    queue.mark_retry.assert_awaited_once()
    assert "dlq_move_failed" in str(queue.mark_retry.await_args.args[3])
    mock_record_metric.assert_called_once_with(outcome="dlq_move_failed", status="ACK")
    assert any(
        kwargs == {
            "processed": 1,
            "delivered": 0,
            "retry_scheduled": 0,
            "dlq_moved": 0,
            "dlq_move_failed": 1,
        }
        for _, kwargs in mock_update_scan.call_args_list
    )


@pytest.mark.asyncio
async def test_retry_worker_records_delivered_metric_and_scan_summary():
    shutdown_event = asyncio.Event()
    queue = AsyncMock()
    pending_item = (
        777,
        "cmd-777",
        CommandStatus.DONE,
        {"zone_id": 4},
        0,
        5,
        None,
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
         patch("common.command_status_queue.send_status_to_laravel", new=AsyncMock(return_value=True)) as mock_send, \
         patch("common.command_status_queue.record_command_status_retry") as mock_record_metric, \
         patch("common.command_status_queue.update_command_status_retry_scan") as mock_update_scan:
        await asyncio.wait_for(retry_worker(interval=0.01, shutdown_event=shutdown_event), timeout=1.0)

    mock_send.assert_awaited_once()
    queue.mark_delivered.assert_awaited_once_with(777)
    mock_record_metric.assert_called_once_with(outcome="delivered", status="DONE")
    assert any(
        kwargs == {
            "processed": 1,
            "delivered": 1,
            "retry_scheduled": 0,
            "dlq_moved": 0,
            "dlq_move_failed": 0,
        }
        for _, kwargs in mock_update_scan.call_args_list
    )


@pytest.mark.asyncio
async def test_repair_stuck_commands_once_replays_pending_terminal_status():
    queue = AsyncMock()
    queue.ensure_table = AsyncMock()
    queue.mark_delivered = AsyncMock()
    queue.purge_dlq_item = AsyncMock()

    fetch_rows = [
        [
            {
                "id": 41,
                "cmd_id": "cmd-stuck-pending",
                "status": "SENT",
                "zone_id": 7,
                "node_id": 11,
                "channel": "storage_state",
                "cmd": "state",
                "source": "automation",
                "status_since": None,
            }
        ],
        [
            {
                "source": "pending",
                "id": 501,
                "cmd_id": "cmd-stuck-pending",
                "status": "DONE",
                "details": {"zone_id": 7, "node_uid": "nd-1"},
                "retry_count": 2,
                "max_attempts": 10,
                "last_error": None,
                "occurred_at": None,
            }
        ],
    ]

    with patch("common.command_status_queue.get_status_queue", new=AsyncMock(return_value=queue)), \
         patch("common.command_status_queue.fetch", new=AsyncMock(side_effect=fetch_rows)), \
         patch("common.command_status_queue.record_command_status_repair") as mock_metric, \
         patch(
             "common.command_status_queue.deliver_status_to_laravel",
             new=AsyncMock(
                 return_value=StatusDeliveryResult(
                     delivered=True,
                     queued=False,
                     dropped=False,
                     reason="delivered",
                 )
             ),
         ) as mock_deliver:
        summary = await repair_stuck_commands_once(stale_after_seconds=30.0, limit=10)

    assert summary["scanned"] == 1
    assert summary["repaired"] == 1
    queue.ensure_table.assert_awaited_once()
    queue.mark_delivered.assert_awaited_once_with(501)
    queue.purge_dlq_item.assert_not_awaited()
    mock_deliver.assert_awaited_once()
    mock_metric.assert_called_once_with(
        outcome="repaired",
        command_status="SENT",
        source="pending",
        replay_status="DONE",
    )
    assert mock_deliver.await_args.kwargs["cmd_id"] == "cmd-stuck-pending"
    assert mock_deliver.await_args.kwargs["status"] == CommandStatus.DONE
    assert mock_deliver.await_args.kwargs["enqueue_on_failure"] is False


@pytest.mark.asyncio
async def test_repair_stuck_commands_once_replays_dlq_terminal_status():
    queue = AsyncMock()
    queue.ensure_table = AsyncMock()
    queue.mark_delivered = AsyncMock()
    queue.purge_dlq_item = AsyncMock(return_value=True)

    fetch_rows = [
        [
            {
                "id": 42,
                "cmd_id": "cmd-stuck-dlq",
                "status": "ACK",
                "zone_id": 8,
                "node_id": 12,
                "channel": "pump_main",
                "cmd": "set_relay",
                "source": "device",
                "status_since": None,
            }
        ],
        [
            {
                "source": "dlq",
                "id": 777,
                "cmd_id": "cmd-stuck-dlq",
                "status": "ERROR",
                "details": {"zone_id": 8, "error_code": "pump_interlock_blocked"},
                "retry_count": 10,
                "max_attempts": 10,
                "last_error": "http_500",
                "occurred_at": None,
            }
        ],
    ]

    with patch("common.command_status_queue.get_status_queue", new=AsyncMock(return_value=queue)), \
         patch("common.command_status_queue.fetch", new=AsyncMock(side_effect=fetch_rows)), \
         patch("common.command_status_queue.record_command_status_repair") as mock_metric, \
         patch(
             "common.command_status_queue.deliver_status_to_laravel",
             new=AsyncMock(
                 return_value=StatusDeliveryResult(
                     delivered=True,
                     queued=False,
                     dropped=False,
                     reason="delivered",
                 )
             ),
         ) as mock_deliver:
        summary = await repair_stuck_commands_once(stale_after_seconds=30.0, limit=10)

    assert summary["scanned"] == 1
    assert summary["repaired"] == 1
    queue.mark_delivered.assert_not_awaited()
    queue.purge_dlq_item.assert_awaited_once_with(777)
    mock_deliver.assert_awaited_once()
    mock_metric.assert_called_once_with(
        outcome="repaired",
        command_status="ACK",
        source="dlq",
        replay_status="ERROR",
    )
    assert mock_deliver.await_args.kwargs["status"] == CommandStatus.ERROR


@pytest.mark.asyncio
async def test_repair_stuck_commands_once_skips_when_no_correlation():
    queue = AsyncMock()
    queue.ensure_table = AsyncMock()
    queue.mark_delivered = AsyncMock()
    queue.purge_dlq_item = AsyncMock()

    fetch_rows = [
        [
            {
                "id": 43,
                "cmd_id": "cmd-stuck-no-correlation",
                "status": "SENT",
                "zone_id": 9,
                "node_id": 13,
                "channel": "storage_state",
                "cmd": "state",
                "source": "automation",
                "status_since": None,
            }
        ],
        [],
    ]

    with patch("common.command_status_queue.get_status_queue", new=AsyncMock(return_value=queue)), \
         patch("common.command_status_queue.fetch", new=AsyncMock(side_effect=fetch_rows)), \
         patch("common.command_status_queue.record_command_status_repair") as mock_metric, \
         patch("common.command_status_queue.deliver_status_to_laravel", new=AsyncMock()) as mock_deliver:
        summary = await repair_stuck_commands_once(stale_after_seconds=30.0, limit=10)

    assert summary["scanned"] == 1
    assert summary["no_correlation"] == 1
    queue.mark_delivered.assert_not_awaited()
    queue.purge_dlq_item.assert_not_awaited()
    mock_metric.assert_called_once_with(
        outcome="no_correlation",
        command_status="SENT",
        source="none",
        replay_status="none",
    )
    mock_deliver.assert_not_awaited()


@pytest.mark.asyncio
async def test_repair_stuck_commands_once_records_replay_failed_metric():
    queue = AsyncMock()
    queue.ensure_table = AsyncMock()
    queue.mark_delivered = AsyncMock()
    queue.purge_dlq_item = AsyncMock()

    fetch_rows = [
        [
            {
                "id": 44,
                "cmd_id": "cmd-stuck-replay-failed",
                "status": "ACK",
                "zone_id": 10,
                "node_id": 14,
                "channel": "pump_main",
                "cmd": "set_relay",
                "status_since": None,
            }
        ],
        [
            {
                "source": "pending",
                "id": 778,
                "cmd_id": "cmd-stuck-replay-failed",
                "status": "ERROR",
                "details": {"zone_id": 10, "error_code": "pump_interlock_blocked"},
                "retry_count": 1,
                "max_attempts": 10,
                "last_error": None,
                "occurred_at": None,
            }
        ],
    ]

    with patch("common.command_status_queue.get_status_queue", new=AsyncMock(return_value=queue)), \
         patch("common.command_status_queue.fetch", new=AsyncMock(side_effect=fetch_rows)), \
         patch("common.command_status_queue.record_command_status_repair") as mock_metric, \
         patch(
             "common.command_status_queue.deliver_status_to_laravel",
             new=AsyncMock(
                 return_value=StatusDeliveryResult(
                     delivered=False,
                     queued=False,
                     dropped=True,
                     reason="http_500",
                     http_status=500,
                 )
             ),
         ) as mock_deliver:
        summary = await repair_stuck_commands_once(stale_after_seconds=30.0, limit=10)

    assert summary["scanned"] == 1
    assert summary["replay_failed"] == 1
    queue.mark_delivered.assert_not_awaited()
    queue.purge_dlq_item.assert_not_awaited()
    mock_deliver.assert_awaited_once()
    mock_metric.assert_called_once_with(
        outcome="replay_failed",
        command_status="ACK",
        source="pending",
        replay_status="ERROR",
    )
