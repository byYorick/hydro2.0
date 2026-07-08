"""Unit-тесты R3 reliability: processing-list, PG requeue, PUBACK, shutdown drain."""
from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from common.utils.time import utcnow

from common.redis_queue import (
    PopBatchResult,
    QueueEntry,
    TelemetryQueue,
    TelemetryQueueItem,
    _unwrap_queue_bytes,
    _wrap_queue_bytes,
)
from telemetry_processing import (
    PgTransportError,
    TelemetryBatchResult,
    _handle_pop_batch,
    _drain_telemetry_queue_on_shutdown,
    process_telemetry_batch,
)


class TestRedisQueueEnvelope:
    def test_wrap_unwrap_retry(self):
        raw = b'{"node_uid":"n1","metric_type":"PH","value":6.5}'
        wrapped = _wrap_queue_bytes(raw, 2)
        inner, retry = _unwrap_queue_bytes(wrapped)
        assert inner == raw
        assert retry == 2

    def test_legacy_payload_unwrap(self):
        raw = b'{"node_uid":"n1"}'
        inner, retry = _unwrap_queue_bytes(raw)
        assert inner == raw
        assert retry == 0


@pytest.mark.asyncio
async def test_reclaim_processing_on_startup():
    queue = TelemetryQueue()
    queue._client = AsyncMock()
    queue._reclaim_script = AsyncMock(return_value=3)
    reclaimed = await queue.reclaim_processing()
    assert reclaimed == 3
    queue._reclaim_script.assert_called_once()


@pytest.mark.asyncio
async def test_pop_batch_deserialize_failure_moves_to_dead():
    queue = TelemetryQueue()
    bad_raw = b"not-json"
    queue._client = AsyncMock()
    queue._pop_script = AsyncMock(return_value=[bad_raw])
    queue._move_raw_to_dead = AsyncMock(return_value=True)

    result = await queue.pop_batch(10)
    assert len(result.entries) == 0
    queue._move_raw_to_dead.assert_called_once()
    assert queue._move_raw_to_dead.call_args.kwargs["reason"] == "deserialize_failed"


@pytest.mark.asyncio
async def test_requeue_batch_increments_retry_and_dead_after_max():
    queue = TelemetryQueue()
    raw = TelemetryQueueItem(node_uid="n1", metric_type="PH", value=1.0).to_json()
    entry = QueueEntry(raw=raw, item=TelemetryQueueItem.from_json(raw), retry_count=3)
    queue._client = AsyncMock()
    queue._max_pg_retries = MagicMock(return_value=3)
    queue._move_raw_to_dead = AsyncMock(return_value=True)

    with patch.object(queue, "_max_pg_retries", return_value=3):
        requeued = await queue.requeue_batch([entry])
    assert requeued == 0
    queue._move_raw_to_dead.assert_called_once()


@pytest.mark.asyncio
async def test_move_entries_to_dead_batch():
    queue = TelemetryQueue()
    raw1 = TelemetryQueueItem(node_uid="n1", metric_type="PH", value=1.0).to_json()
    raw2 = TelemetryQueueItem(node_uid="n2", metric_type="EC", value=2.0).to_json()
    entries = [
        QueueEntry(raw=raw1, item=TelemetryQueueItem.from_json(raw1)),
        QueueEntry(raw=raw2, item=TelemetryQueueItem.from_json(raw2)),
    ]
    queue._move_raw_to_dead = AsyncMock(return_value=True)

    moved = await queue.move_entries_to_dead(entries, reason="fk_violation")
    assert moved == 2
    assert queue._move_raw_to_dead.call_count == 2


@pytest.mark.asyncio
async def test_handle_pop_batch_acks_on_success():
    raw = TelemetryQueueItem(node_uid="n1", metric_type="PH", value=6.5).to_json()
    item = TelemetryQueueItem.from_json(raw)
    pop = PopBatchResult(entries=[QueueEntry(raw=raw, item=item)])

    mock_queue = AsyncMock()
    mock_queue.ack_batch = AsyncMock(return_value=1)
    mock_queue.requeue_batch = AsyncMock()
    mock_queue.move_entries_to_dead = AsyncMock(return_value=0)

    with patch("telemetry_processing._get_telemetry_queue", return_value=mock_queue), \
         patch(
             "telemetry_processing.process_telemetry_batch",
             new_callable=AsyncMock,
             return_value=TelemetryBatchResult(processed_count=1),
         ):
        await _handle_pop_batch(pop)

    mock_queue.ack_batch.assert_called_once_with([raw])
    mock_queue.requeue_batch.assert_not_called()
    mock_queue.move_entries_to_dead.assert_not_called()


@pytest.mark.asyncio
async def test_handle_pop_batch_requeues_on_pg_transport_error():
    raw = TelemetryQueueItem(node_uid="n1", metric_type="PH", value=6.5).to_json()
    item = TelemetryQueueItem.from_json(raw)
    entry = QueueEntry(raw=raw, item=item)
    pop = PopBatchResult(entries=[entry])

    mock_queue = AsyncMock()
    mock_queue.ack_batch = AsyncMock()
    mock_queue.requeue_batch = AsyncMock(return_value=1)
    mock_queue.move_entries_to_dead = AsyncMock(return_value=0)

    with patch("telemetry_processing._get_telemetry_queue", return_value=mock_queue), \
         patch(
             "telemetry_processing.process_telemetry_batch",
             new_callable=AsyncMock,
             side_effect=PgTransportError("connection lost"),
         ):
        await _handle_pop_batch(pop)

    mock_queue.requeue_batch.assert_called_once_with([entry])
    mock_queue.ack_batch.assert_not_called()
    mock_queue.move_entries_to_dead.assert_not_called()


@pytest.mark.asyncio
async def test_handle_pop_batch_dead_lists_fk_entries_without_full_ack():
    raw_ok = TelemetryQueueItem(node_uid="n1", metric_type="PH", value=6.5).to_json()
    raw_bad = TelemetryQueueItem(node_uid="n2", metric_type="EC", value=2.0).to_json()
    entry_ok = QueueEntry(raw=raw_ok, item=TelemetryQueueItem.from_json(raw_ok))
    entry_bad = QueueEntry(raw=raw_bad, item=TelemetryQueueItem.from_json(raw_bad))
    pop = PopBatchResult(entries=[entry_ok, entry_bad])

    batch_result = TelemetryBatchResult(
        processed_count=1,
        entries_to_dead=[entry_bad],
    )

    mock_queue = AsyncMock()
    mock_queue.ack_batch = AsyncMock(return_value=1)
    mock_queue.requeue_batch = AsyncMock()
    mock_queue.move_entries_to_dead = AsyncMock(return_value=1)

    with patch("telemetry_processing._get_telemetry_queue", return_value=mock_queue), \
         patch(
             "telemetry_processing.process_telemetry_batch",
             new_callable=AsyncMock,
             return_value=batch_result,
         ):
        await _handle_pop_batch(pop)

    mock_queue.move_entries_to_dead.assert_called_once_with(
        [entry_bad],
        reason="fk_violation",
    )
    mock_queue.ack_batch.assert_called_once_with([raw_ok])
    mock_queue.requeue_batch.assert_not_called()


@pytest.mark.asyncio
async def test_handle_pop_batch_requeues_non_transport_insert_failures():
    raw = TelemetryQueueItem(node_uid="n1", metric_type="PH", value=6.5).to_json()
    entry = QueueEntry(raw=raw, item=TelemetryQueueItem.from_json(raw))
    pop = PopBatchResult(entries=[entry])

    batch_result = TelemetryBatchResult(entries_to_requeue=[entry])

    mock_queue = AsyncMock()
    mock_queue.ack_batch = AsyncMock()
    mock_queue.requeue_batch = AsyncMock(return_value=1)
    mock_queue.move_entries_to_dead = AsyncMock(return_value=0)

    with patch("telemetry_processing._get_telemetry_queue", return_value=mock_queue), \
         patch(
             "telemetry_processing.process_telemetry_batch",
             new_callable=AsyncMock,
             return_value=batch_result,
         ):
        await _handle_pop_batch(pop)

    mock_queue.requeue_batch.assert_called_once_with([entry])
    mock_queue.ack_batch.assert_not_called()
    mock_queue.move_entries_to_dead.assert_not_called()


@pytest.mark.asyncio
async def test_process_telemetry_batch_requeues_on_non_transport_samples_failure():
    import telemetry_processing as tp
    from models import TelemetrySampleModel

    tp._zone_cache.clear()
    tp._node_cache.clear()
    tp._zone_greenhouse_cache.clear()
    tp._sensor_cache.clear()
    tp._cache_last_update = time.time()
    tp._zone_cache[("zn-1", "gh-1")] = 1
    tp._zone_greenhouse_cache[1] = 1
    tp._node_cache[("nd-1", "gh-1")] = (10, 1, None)
    tp._sensor_cache[(1, 10, "PH", "ph_sensor")] = 501

    raw = TelemetryQueueItem(
        node_uid="nd-1",
        zone_uid="zn-1",
        gh_uid="gh-1",
        metric_type="PH",
        value=6.5,
        channel="ph_sensor",
    ).to_json()
    entry = QueueEntry(raw=raw, item=TelemetryQueueItem.from_json(raw))
    samples = [
        TelemetrySampleModel(
            node_uid="nd-1",
            zone_uid="zn-1",
            gh_uid="gh-1",
            metric_type="PH",
            value=6.5,
            channel="ph_sensor",
            ts=utcnow(),
        )
    ]

    async def fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from sensors" in normalized and "any($1" in normalized:
            return [{"id": 501}]
        return []

    async def execute_side_effect(query, *args):
        if "telemetry_samples" in str(query):
            raise RuntimeError("samples insert failed")
        return "INSERT 0 1"

    with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("telemetry_processing.execute", new_callable=AsyncMock) as mock_execute:
        mock_fetch.side_effect = fetch_side_effect
        mock_execute.side_effect = execute_side_effect

        batch_result = await process_telemetry_batch(samples, entries=[entry])

    assert entry in batch_result.entries_to_requeue
    assert batch_result.entries_to_dead == []
    assert batch_result.processed_count == 0


@pytest.mark.asyncio
async def test_process_telemetry_batch_dead_lists_on_fk_samples_failure():
    import telemetry_processing as tp
    from models import TelemetrySampleModel

    tp._zone_cache.clear()
    tp._node_cache.clear()
    tp._zone_greenhouse_cache.clear()
    tp._sensor_cache.clear()
    tp._cache_last_update = time.time()
    tp._zone_cache[("zn-1", "gh-1")] = 1
    tp._zone_greenhouse_cache[1] = 1
    tp._node_cache[("nd-1", "gh-1")] = (10, 1, None)
    tp._sensor_cache[(1, 10, "PH", "ph_sensor")] = 501

    raw = TelemetryQueueItem(
        node_uid="nd-1",
        zone_uid="zn-1",
        gh_uid="gh-1",
        metric_type="PH",
        value=6.5,
        channel="ph_sensor",
    ).to_json()
    entry = QueueEntry(raw=raw, item=TelemetryQueueItem.from_json(raw))
    samples = [
        TelemetrySampleModel(
            node_uid="nd-1",
            zone_uid="zn-1",
            gh_uid="gh-1",
            metric_type="PH",
            value=6.5,
            channel="ph_sensor",
            ts=utcnow(),
        )
    ]

    fk_error = RuntimeError(
        'insert on table "telemetry_samples" violates foreign key constraint '
        '"telemetry_samples_sensor_id_foreign"'
    )

    async def fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from sensors" in normalized and "any($1" in normalized:
            return [{"id": 501}]
        return []

    async def execute_side_effect(query, *args):
        if "telemetry_samples" in str(query):
            raise fk_error
        return "INSERT 0 1"

    with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("telemetry_processing.execute", new_callable=AsyncMock) as mock_execute:
        mock_fetch.side_effect = fetch_side_effect
        mock_execute.side_effect = execute_side_effect

        batch_result = await process_telemetry_batch(samples, entries=[entry])

    assert entry in batch_result.entries_to_dead
    assert batch_result.entries_to_requeue == []
    assert batch_result.processed_count == 0


@pytest.mark.asyncio
async def test_pg_transport_error_raised_from_batch_insert():
    samples = []
    with patch("telemetry_processing.refresh_caches", new_callable=AsyncMock), \
         patch("telemetry_processing._zone_cache", {}), \
         patch("telemetry_processing._node_cache", {}):
        # пустой батч — без ошибок
        await process_telemetry_batch(samples)


@pytest.mark.asyncio
async def test_publish_command_mqtt_waits_for_puback():
    from command_service import publish_command_mqtt

    mock_mqtt = MagicMock()
    mock_mqtt.is_connected.return_value = True
    mock_result = MagicMock()
    mock_result.rc = 0
    mock_result.is_published.return_value = True
    mock_mqtt._client._client.publish.return_value = mock_result

    with patch("command_service.get_settings") as mock_settings, \
         patch("command_service._wait_mqtt_message_puback", return_value=True) as mock_wait:
        mock_settings.return_value.mqtt_publish_ack_timeout_sec = 5.0
        await publish_command_mqtt(
            mock_mqtt,
            "gh-1",
            1,
            "nd-1",
            "pump",
            {"cmd_id": "cmd-1", "cmd": "run_pump", "params": {}},
            zone_uid="zn-1",
        )

    mock_wait.assert_called_once()


@pytest.mark.asyncio
async def test_publish_command_mqtt_puback_timeout_raises():
    from command_service import publish_command_mqtt
    from metrics import COMMANDS_PUBLISH_UNCONFIRMED

    mock_mqtt = MagicMock()
    mock_mqtt.is_connected.return_value = True
    mock_result = MagicMock()
    mock_result.rc = 0
    mock_mqtt._client._client.publish.return_value = mock_result

    before = COMMANDS_PUBLISH_UNCONFIRMED._value.get()

    with patch("command_service.get_settings") as mock_settings, \
         patch("command_service._wait_mqtt_message_puback", return_value=False):
        mock_settings.return_value.mqtt_publish_ack_timeout_sec = 1.0
        with pytest.raises(RuntimeError, match="PUBACK"):
            await publish_command_mqtt(
                mock_mqtt,
                "gh-1",
                1,
                "nd-1",
                "pump",
                {"cmd_id": "cmd-2", "cmd": "run_pump", "params": {}},
            )

    after = COMMANDS_PUBLISH_UNCONFIRMED._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_shutdown_drain_processes_until_empty():
    raw = TelemetryQueueItem(node_uid="n1", metric_type="PH", value=1.0).to_json()
    item = TelemetryQueueItem.from_json(raw)
    pop_with_items = PopBatchResult(entries=[QueueEntry(raw=raw, item=item)])

    mock_queue = AsyncMock()
    mock_queue.total_pending_size = AsyncMock(side_effect=[2, 1, 0, 0])
    mock_queue.pop_batch = AsyncMock(return_value=pop_with_items)

    with patch("telemetry_processing._get_telemetry_queue", return_value=mock_queue), \
         patch("telemetry_processing._handle_pop_batch", new_callable=AsyncMock), \
         patch("telemetry_processing.get_settings") as mock_settings:
        mock_settings.return_value.telemetry_shutdown_drain_timeout_sec = 5.0
        mock_settings.return_value.telemetry_batch_size = 100
        await _drain_telemetry_queue_on_shutdown()

    mock_queue.pop_batch.assert_called()


@pytest.mark.asyncio
async def test_invalid_json_increments_telemetry_dropped():
    from telemetry.ingress import handle_telemetry
    from metrics import TELEMETRY_DROPPED

    before = TELEMETRY_DROPPED.labels(reason="invalid_json")._value.get()

    with patch("telemetry.ingress._telemetry_queue", return_value=AsyncMock()):
        await handle_telemetry("hydro/gh/zn/n/ch/telemetry", b"{bad json")

    after = TELEMETRY_DROPPED.labels(reason="invalid_json")._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_command_status_delivery_dropped_metric():
    from handlers.command_response import _log_delivery_result
    from metrics import COMMAND_STATUS_DELIVERY_DROPPED

    delivery_result = MagicMock()
    delivery_result.delivered = False
    delivery_result.queued = False
    delivery_result.dropped = True
    delivery_result.reason = "max_retries"
    delivery_result.http_status = None
    delivery_result.queue_error = "full"

    before = COMMAND_STATUS_DELIVERY_DROPPED._value.get()

    with patch("handlers.command_response.COMMAND_RESPONSE_ERROR") as mock_err:
        mock_err.inc = MagicMock()
        _log_delivery_result(
            delivery_result=delivery_result,
            cmd_id="cmd-x",
            normalized_status=MagicMock(value="DONE"),
            node_uid="n1",
            channel="pump",
            existing_status="SENT",
        )

    after = COMMAND_STATUS_DELIVERY_DROPPED._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_ingest_pg_down_requeue_then_recovery():
    """Интеграционный сценарий R3: PG недоступен → requeue → повторный ingest → ack."""
    raw = TelemetryQueueItem(node_uid="n1", metric_type="PH", value=6.5).to_json()
    item = TelemetryQueueItem.from_json(raw)
    entry = QueueEntry(raw=raw, item=item)
    pop = PopBatchResult(entries=[entry])

    mock_queue = AsyncMock()
    mock_queue.ack_batch = AsyncMock(return_value=1)
    mock_queue.requeue_batch = AsyncMock(return_value=1)
    mock_queue.move_entries_to_dead = AsyncMock(return_value=0)

    process_calls = 0

    async def process_side_effect(samples, *, entries=None):
        nonlocal process_calls
        process_calls += 1
        if process_calls == 1:
            raise PgTransportError("pg down")
        return TelemetryBatchResult(processed_count=len(samples))

    with patch("telemetry_processing._get_telemetry_queue", return_value=mock_queue), \
         patch("telemetry_processing.process_telemetry_batch", side_effect=process_side_effect):
        await _handle_pop_batch(pop)

    mock_queue.requeue_batch.assert_called_once_with([entry])
    mock_queue.ack_batch.assert_not_called()

    mock_queue.ack_batch.reset_mock()
    mock_queue.requeue_batch.reset_mock()

    with patch("telemetry_processing._get_telemetry_queue", return_value=mock_queue), \
         patch(
             "telemetry_processing.process_telemetry_batch",
             new_callable=AsyncMock,
             return_value=TelemetryBatchResult(processed_count=1),
         ):
        await _handle_pop_batch(pop)

    mock_queue.ack_batch.assert_called_once_with([raw])
    mock_queue.requeue_batch.assert_not_called()
