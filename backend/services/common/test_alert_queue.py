"""Tests for alert queue zone-id fail-safe behavior."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from common.alert_queue import AlertQueue, retry_worker, send_alert_to_laravel


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


class _ConnStub:
    def __init__(self, zone_exists: bool):
        self.zone_exists = zone_exists
        self.executed = []

    async def fetchval(self, query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "select exists(select 1 from zones where id = $1)" in normalized:
            return self.zone_exists
        return None

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "INSERT 0 1"


class _ResponseStub:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


@pytest.mark.asyncio
async def test_enqueue_invalid_zone_falls_back_to_unassigned():
    """If zone does not exist, alert should be queued with zone_id=NULL."""
    queue = AlertQueue()
    conn = _ConnStub(zone_exists=False)

    with patch.object(queue, "ensure_table", new=AsyncMock(return_value=None)), \
         patch("common.alert_queue.get_pool", new=AsyncMock(return_value=_PoolStub(conn))):
        ok = await queue.enqueue(
            zone_id=1,
            source="infra",
            code="infra_test",
            type="Infrastructure Error",
            status="ACTIVE",
            details={"message": "test"},
        )

    assert ok is True
    assert len(conn.executed) == 1
    insert_args = conn.executed[0][1]
    assert insert_args[0] is None
    assert insert_args[5]["requested_zone_id"] == 1


@pytest.mark.asyncio
async def test_enqueue_valid_zone_keeps_zone_id():
    """When zone exists, queue must preserve provided zone_id."""
    queue = AlertQueue()
    conn = _ConnStub(zone_exists=True)

    with patch.object(queue, "ensure_table", new=AsyncMock(return_value=None)), \
         patch("common.alert_queue.get_pool", new=AsyncMock(return_value=_PoolStub(conn))):
        ok = await queue.enqueue(
            zone_id=327,
            source="infra",
            code="infra_test",
            type="Infrastructure Error",
            status="ACTIVE",
            details={"message": "test"},
        )

    assert ok is True
    assert len(conn.executed) == 1
    insert_args = conn.executed[0][1]
    assert insert_args[0] == 327


@pytest.mark.asyncio
async def test_send_alert_to_laravel_retry_mode_does_not_enqueue_on_failure():
    """Retry mode must not create duplicated queue entries on delivery failure."""
    settings = type("S", (), {"laravel_api_url": "http://laravel", "history_logger_api_token": None, "ingest_token": None})()
    queue = AsyncMock()

    with patch("common.alert_queue.get_settings", return_value=settings), \
         patch("common.alert_queue.make_request", new=AsyncMock(return_value=_ResponseStub(500, "boom"))), \
         patch("common.alert_queue.get_alert_queue", new=AsyncMock(return_value=queue)):
        ok = await send_alert_to_laravel(
            zone_id=1,
            source="infra",
            code="infra_test",
            type="Infrastructure Error",
            status="ACTIVE",
            details={"message": "test"},
            enqueue_on_failure=False,
        )

    assert ok is False
    queue.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_retry_worker_passes_enqueue_on_failure_false():
    shutdown_event = asyncio.Event()
    queue = AsyncMock()
    pending_item = (
        42,          # alert_id
        1,           # zone_id
        "infra",     # source
        "infra_x",   # code
        "Infra",     # type
        "ACTIVE",    # status
        {"a": 1},    # details
        0,           # attempts
        3,           # max_attempts
        None,        # last_error
    )

    calls = {"count": 0}

    async def _get_pending(limit=50):
        if calls["count"] == 0:
            calls["count"] += 1
            return [pending_item]
        shutdown_event.set()
        return []

    queue.get_pending = AsyncMock(side_effect=_get_pending)

    with patch("common.alert_queue.get_alert_queue", new=AsyncMock(return_value=queue)), \
         patch("common.alert_queue.send_alert_to_laravel", new=AsyncMock(return_value=False)) as mock_send, \
         patch("common.alert_queue.calculate_backoff_with_jitter", return_value=1):
        await asyncio.wait_for(retry_worker(interval=0.01, shutdown_event=shutdown_event), timeout=1.0)

    mock_send.assert_awaited_once()
    assert mock_send.await_args.kwargs["enqueue_on_failure"] is False
    queue.mark_retry.assert_awaited_once()
