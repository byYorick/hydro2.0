"""E214: ingest пишет cycle_id активной посадки зоны в telemetry_samples."""
import time
from unittest.mock import AsyncMock, patch

import pytest
import telemetry_processing as tp
from common.utils.time import utcnow
from models import TelemetrySampleModel
from telemetry_processing import (
    _node_cache,
    _resolve_active_cycle_ids,
    _sensor_cache,
    _zone_cache,
    _zone_greenhouse_cache,
    process_telemetry_batch,
)


def _prime_caches(*, zone_id: int = 1, node_id: int = 10, sensor_id: int = 101) -> None:
    _zone_cache.clear()
    _node_cache.clear()
    _zone_greenhouse_cache.clear()
    _sensor_cache.clear()
    tp._cache_last_update = time.time()
    _zone_cache[("zn-1", "gh-1")] = zone_id
    _zone_greenhouse_cache[zone_id] = 99
    _node_cache[("nd-1", "gh-1")] = (node_id, zone_id)
    _sensor_cache[(zone_id, node_id, "TEMPERATURE", "TEMPERATURE")] = sensor_id


def _sample() -> TelemetrySampleModel:
    return TelemetrySampleModel(
        zone_uid="zn-1",
        gh_uid="gh-1",
        node_uid="nd-1",
        metric_type="TEMPERATURE",
        value=25.0,
        ts=utcnow(),
    )


@pytest.mark.asyncio
async def test_e214_sample_gets_active_cycle_id():
    """Новый sample зоны с одной активной посадкой получает её grow_cycles.id."""
    _prime_caches()

    async def _fetch_side_effect(query, *args):
        sql = str(query)
        if "FROM grow_cycles" in sql:
            return [{"id": 456, "zone_id": 1}]
        if "telemetry_samples" in sql and "RETURNING" in sql:
            return [{"sensor_id": 101, "ts": args[1][0]}]
        if "FROM sensors" in sql and "ANY($1" in sql:
            return [{"id": 101}]
        return []

    with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("telemetry_processing.execute", new_callable=AsyncMock) as mock_execute:
        mock_fetch.side_effect = _fetch_side_effect
        mock_execute.return_value = None

        await process_telemetry_batch([_sample()])

    insert_call = next(
        call
        for call in mock_fetch.call_args_list
        if call.args and "INSERT INTO telemetry_samples" in str(call.args[0])
    )
    cycle_ids = insert_call.args[4]
    assert cycle_ids == [456]


@pytest.mark.asyncio
async def test_e214_sample_without_planting_has_null_cycle_id():
    """Нет активной посадки — cycle_id = NULL."""
    _prime_caches()

    async def _fetch_side_effect(query, *args):
        sql = str(query)
        if "FROM grow_cycles" in sql:
            return []
        if "telemetry_samples" in sql and "RETURNING" in sql:
            return [{"sensor_id": 101, "ts": args[1][0]}]
        if "FROM sensors" in sql and "ANY($1" in sql:
            return [{"id": 101}]
        return []

    with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("telemetry_processing.execute", new_callable=AsyncMock) as mock_execute:
        mock_fetch.side_effect = _fetch_side_effect
        mock_execute.return_value = None

        await process_telemetry_batch([_sample()])

    insert_call = next(
        call
        for call in mock_fetch.call_args_list
        if call.args and "INSERT INTO telemetry_samples" in str(call.args[0])
    )
    cycle_ids = insert_call.args[4]
    assert cycle_ids == [None]


@pytest.mark.asyncio
async def test_e214_ambiguous_active_plantings_null_and_logs_error(caplog):
    """Две активные посадки — NULL, без угадывания id, ошибка в лог."""
    _prime_caches()

    async def _fetch_side_effect(query, *args):
        sql = str(query)
        if "FROM grow_cycles" in sql:
            return [
                {"id": 10, "zone_id": 1},
                {"id": 11, "zone_id": 1},
            ]
        if "telemetry_samples" in sql and "RETURNING" in sql:
            return [{"sensor_id": 101, "ts": args[1][0]}]
        if "FROM sensors" in sql and "ANY($1" in sql:
            return [{"id": 101}]
        return []

    with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("telemetry_processing.execute", new_callable=AsyncMock) as mock_execute, \
         caplog.at_level("ERROR"):
        mock_fetch.side_effect = _fetch_side_effect
        mock_execute.return_value = None

        await process_telemetry_batch([_sample()])

    insert_call = next(
        call
        for call in mock_fetch.call_args_list
        if call.args and "INSERT INTO telemetry_samples" in str(call.args[0])
    )
    assert insert_call.args[4] == [None]
    assert any(
        "Несколько активных посадок" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_e214_resolve_active_cycle_ids_unit():
    """Прямой контракт резолва: 0 / 1 / >1 активных посадок."""
    with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [{"id": 77, "zone_id": 5}]
        one = await _resolve_active_cycle_ids([5])
        assert one == {5: 77}

        mock_fetch.return_value = []
        none = await _resolve_active_cycle_ids([5])
        assert none == {5: None}

        mock_fetch.return_value = [
            {"id": 1, "zone_id": 5},
            {"id": 2, "zone_id": 5},
        ]
        amb = await _resolve_active_cycle_ids([5])
        assert amb == {5: None}
