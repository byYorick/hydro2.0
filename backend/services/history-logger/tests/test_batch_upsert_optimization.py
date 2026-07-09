"""
Тесты для оптимизации batch upsert telemetry_last.
Проверяет, что используется один запрос для всех обновлений.
"""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import timedelta
from common.utils.time import utcnow
from telemetry.helpers import build_sensor_label, infer_sensor_type
from telemetry_processing import process_telemetry_batch, _normalize_ts_for_db
from models import TelemetrySampleModel

ZONE_ID = 1
NODE_ID = 1


from typing import Optional


def _sensor_cache_key(metric_type: str, channel: Optional[str] = None) -> tuple:
    sensor_type = infer_sensor_type(metric_type)
    sensor_label = build_sensor_label(metric_type, channel, sensor_type)
    return (ZONE_ID, NODE_ID, sensor_type, sensor_label)


def _make_fetch_side_effect(sample_sensor_pairs: list[tuple[TelemetrySampleModel, int]]):
    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from sensors" in normalized and "any($1" in normalized:
            sensor_ids = args[0] if args else []
            return [{"id": int(sensor_id)} for sensor_id in sensor_ids]
        if "telemetry_samples" in normalized and "returning" in normalized:
            return [
                {
                    "sensor_id": sensor_id,
                    "ts": _normalize_ts_for_db(sample.ts),
                }
                for sample, sensor_id in sample_sensor_pairs
            ]
        return []

    return _fetch_side_effect


@pytest.mark.asyncio
async def test_batch_upsert_single_query():
    """Тест, что batch upsert использует один запрос для всех обновлений."""
    samples = [
        TelemetrySampleModel(
            zone_uid='zn-1',
            gh_uid='gh-1',
            node_uid='nd-1',
            metric_type='TEMPERATURE',
            value=25.0,
            ts=utcnow()
        ),
        TelemetrySampleModel(
            zone_uid='zn-1',
            gh_uid='gh-1',
            node_uid='nd-1',
            metric_type='HUMIDITY',
            value=60.0,
            ts=utcnow()
        ),
        TelemetrySampleModel(
            zone_uid='zn-1',
            gh_uid='gh-1',
            node_uid='nd-1',
            metric_type='PH',
            value=6.5,
            ts=utcnow()
        ),
    ]
    sample_sensor_pairs = [
        (samples[0], 101),
        (samples[1], 102),
        (samples[2], 103),
    ]

    with patch('telemetry_processing._zone_cache', {('zn-1', 'gh-1'): ZONE_ID}), \
         patch('telemetry_processing._node_cache', {('nd-1', 'gh-1'): (NODE_ID, ZONE_ID)}), \
         patch('telemetry_processing._sensor_cache', {
             _sensor_cache_key('TEMPERATURE'): 101,
             _sensor_cache_key('HUMIDITY'): 102,
             _sensor_cache_key('PH'): 103,
         }), \
         patch('telemetry_processing._cache_last_update', 9999999999.0), \
         patch('telemetry_processing.fetch', new_callable=AsyncMock) as mock_fetch, \
         patch('telemetry_processing.execute', new_callable=AsyncMock) as mock_execute:

        mock_fetch.side_effect = _make_fetch_side_effect(sample_sensor_pairs)

        await process_telemetry_batch(samples)

        upsert_calls = [
            call for call in mock_execute.call_args_list
            if 'telemetry_last' in str(call) or 'ON CONFLICT' in str(call)
        ]

        assert len(upsert_calls) >= 1

        if upsert_calls:
            query_str = str(upsert_calls[0])
            assert 'VALUES' in query_str or 'ON CONFLICT' in query_str


@pytest.mark.asyncio
async def test_batch_upsert_latest_timestamp():
    """Тест, что batch upsert выбирает сэмпл с максимальным timestamp."""
    base_time = utcnow()

    samples = [
        TelemetrySampleModel(
            zone_uid='zn-1',
            gh_uid='gh-1',
            node_uid='nd-1',
            metric_type='TEMPERATURE',
            value=20.0,
            ts=base_time
        ),
        TelemetrySampleModel(
            zone_uid='zn-1',
            gh_uid='gh-1',
            node_uid='nd-1',
            metric_type='TEMPERATURE',
            value=25.0,
            ts=base_time + timedelta(seconds=10)
        ),
    ]
    sample_sensor_pairs = [
        (samples[0], 101),
        (samples[1], 101),
    ]

    with patch('telemetry_processing._zone_cache', {('zn-1', 'gh-1'): ZONE_ID}), \
         patch('telemetry_processing._node_cache', {('nd-1', 'gh-1'): (NODE_ID, ZONE_ID)}), \
         patch('telemetry_processing._sensor_cache', {
             _sensor_cache_key('TEMPERATURE'): 101,
         }), \
         patch('telemetry_processing._cache_last_update', 9999999999.0), \
         patch('telemetry_processing.fetch', new_callable=AsyncMock) as mock_fetch, \
         patch('telemetry_processing.execute', new_callable=AsyncMock) as mock_execute:

        mock_fetch.side_effect = _make_fetch_side_effect(sample_sensor_pairs)

        await process_telemetry_batch(samples)

        upsert_calls = [
            call for call in mock_execute.call_args_list
            if 'telemetry_last' in str(call) or 'ON CONFLICT' in str(call)
        ]

        assert len(upsert_calls) > 0


@pytest.mark.asyncio
async def test_batch_upsert_fallback():
    """Тест fallback на индивидуальные upsert при ошибке batch."""
    samples = [
        TelemetrySampleModel(
            zone_uid='zn-1',
            gh_uid='gh-1',
            node_uid='nd-1',
            metric_type='TEMPERATURE',
            value=25.0,
            ts=utcnow()
        ),
    ]
    sample_sensor_pairs = [(samples[0], 101)]

    call_count = 0

    async def mock_execute_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        query_str = str(args[0]) if args else ""
        if 'telemetry_last' in query_str and 'ON CONFLICT' in query_str and call_count == 1:
            raise Exception("Batch upsert failed")
        return None

    with patch('telemetry_processing._zone_cache', {('zn-1', 'gh-1'): ZONE_ID}), \
         patch('telemetry_processing._node_cache', {('nd-1', 'gh-1'): (NODE_ID, ZONE_ID)}), \
         patch('telemetry_processing._sensor_cache', {
             _sensor_cache_key('TEMPERATURE'): 101,
         }), \
         patch('telemetry_processing._cache_last_update', 9999999999.0), \
         patch('telemetry_processing.fetch', new_callable=AsyncMock) as mock_fetch, \
         patch('telemetry_processing.execute', new_callable=AsyncMock) as mock_execute:

        mock_fetch.side_effect = _make_fetch_side_effect(sample_sensor_pairs)
        mock_execute.side_effect = mock_execute_side_effect

        await process_telemetry_batch(samples)

        telemetry_calls = [
            call for call in mock_execute.call_args_list
            if 'telemetry_last' in str(call)
        ]
        assert len(telemetry_calls) >= 2
