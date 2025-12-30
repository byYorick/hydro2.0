"""
Тесты для realtime очереди history-logger.
Проверяют coalescing, bounded queue и flush.
"""
from unittest.mock import AsyncMock, patch

import pytest
import telemetry_processing as tp
from telemetry_processing import _enqueue_realtime_update, _flush_realtime_updates


@pytest.mark.asyncio
async def test_realtime_queue_coalesces_by_key():
    tp._realtime_updates.clear()

    with patch("telemetry_processing.get_settings") as mock_settings:
        mock_settings.return_value.realtime_queue_max_size = 10

        await _enqueue_realtime_update(("sensor", 1), {
            "zone_id": 1,
            "node_id": 10,
            "channel": "ph_sensor",
            "metric_type": "PH",
            "value": 6.2,
            "timestamp": 1700000000000,
        })
        await _enqueue_realtime_update(("sensor", 1), {
            "zone_id": 1,
            "node_id": 10,
            "channel": "ph_sensor",
            "metric_type": "PH",
            "value": 6.4,
            "timestamp": 1700000001000,
        })

    assert len(tp._realtime_updates) == 1
    update = next(iter(tp._realtime_updates.values()))
    assert update["value"] == 6.4


@pytest.mark.asyncio
async def test_realtime_queue_drops_oldest_when_full():
    tp._realtime_updates.clear()

    with patch("telemetry_processing.get_settings") as mock_settings, \
         patch("telemetry_processing.REALTIME_DROPPED_UPDATES") as mock_dropped:
        mock_settings.return_value.realtime_queue_max_size = 1

        await _enqueue_realtime_update(("sensor", 1), {
            "zone_id": 1,
            "node_id": 10,
            "channel": "ph_sensor",
            "metric_type": "PH",
            "value": 6.2,
            "timestamp": 1700000000000,
        })
        await _enqueue_realtime_update(("sensor", 2), {
            "zone_id": 1,
            "node_id": 11,
            "channel": "ec_sensor",
            "metric_type": "EC",
            "value": 1.5,
            "timestamp": 1700000001000,
        })

        assert len(tp._realtime_updates) == 1
        update = next(iter(tp._realtime_updates.values()))
        assert update["node_id"] == 11
        assert mock_dropped.labels.called


@pytest.mark.asyncio
async def test_flush_realtime_updates_sends_batch():
    tp._realtime_updates.clear()
    tp._broadcast_backoff_until = None

    with patch("telemetry_processing.get_settings") as mock_settings, \
         patch("telemetry_processing._broadcast_telemetry_batch_to_laravel", new_callable=AsyncMock) as mock_broadcast:
        mock_settings.return_value.realtime_queue_max_size = 10
        mock_settings.return_value.realtime_batch_max_updates = 2
        mock_broadcast.return_value = True

        await _enqueue_realtime_update(("sensor", 1), {
            "zone_id": 1,
            "node_id": 10,
            "channel": "ph_sensor",
            "metric_type": "PH",
            "value": 6.2,
            "timestamp": 1700000000000,
        })
        await _enqueue_realtime_update(("sensor", 2), {
            "zone_id": 1,
            "node_id": 11,
            "channel": "ec_sensor",
            "metric_type": "EC",
            "value": 1.5,
            "timestamp": 1700000001000,
        })

        await _flush_realtime_updates()

        assert mock_broadcast.called
        assert len(tp._realtime_updates) == 0
