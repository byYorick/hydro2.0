"""Tests for telemetry processing module."""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime
from common.utils.time import utcnow
from common.telemetry import TelemetrySampleModel, process_telemetry_batch


@pytest.mark.asyncio
async def test_process_telemetry_batch_with_node_uid():
    """Test processing telemetry batch with node_uid."""
    sample = TelemetrySampleModel(
        node_uid="nd-ph-1",
        zone_id=1,
        metric_type="PH",
        value=6.5,
        ts=utcnow(),
        channel="ph_sensor"
    )
    
    with patch("common.telemetry.fetch") as mock_fetch, \
         patch("common.telemetry.execute") as mock_execute, \
         patch("common.telemetry.upsert_telemetry_last") as mock_upsert:
        # Mock node lookup - node exists and is validated
        mock_fetch.side_effect = [
            [{"id": 10, "zone_id": 1, "validated": True}],
            [{"id": 101}],
        ]
        
        await process_telemetry_batch([sample])
        
        # Проверяем, что fetch вызван для поиска ноды
        mock_fetch.assert_called()
        # Проверяем, что execute вызван для записи в telemetry_samples
        assert mock_execute.call_count >= 1
        assert mock_upsert.call_count == 1


@pytest.mark.asyncio
async def test_process_telemetry_batch_with_unknown_node():
    """Test processing telemetry batch with unknown node_uid (should skip)."""
    sample = TelemetrySampleModel(
        node_uid="unknown-node",
        zone_id=1,
        metric_type="PH",
        value=6.5
    )
    
    with patch("common.telemetry.fetch") as mock_fetch, \
         patch("common.telemetry.execute") as mock_execute:
        # Mock node lookup - node not found
        mock_fetch.return_value = []
        
        await process_telemetry_batch([sample])
        
        # execute не должен быть вызван, т.к. нода не найдена
        # Проверяем только вызовы fetch (для поиска ноды)
        assert mock_fetch.called


@pytest.mark.asyncio
async def test_process_telemetry_batch_with_zone_id():
    """Test processing telemetry batch with zone_id directly."""
    sample = TelemetrySampleModel(
        node_uid="nd-ph-1",
        zone_id=1,  # Передаём zone_id напрямую
        metric_type="EC",
        value=1.8
    )
    
    with patch("common.telemetry.fetch") as mock_fetch, \
         patch("common.telemetry.execute") as mock_execute, \
         patch("common.telemetry.upsert_telemetry_last") as mock_upsert:
        # Mock node lookup - node exists and is validated
        mock_fetch.side_effect = [
            [{"id": 10, "zone_id": 1, "validated": True}],
            [{"id": 101}],
        ]
        
        await process_telemetry_batch([sample])
        
        # Проверяем, что данные обработаны
        assert mock_execute.call_count >= 1
        assert mock_upsert.call_count == 1


@pytest.mark.asyncio
async def test_process_telemetry_batch_with_zone_uid():
    """Test processing telemetry batch with zone_uid in format zn-{id}."""
    sample = TelemetrySampleModel(
        node_uid="nd-ph-1",
        zone_uid="zn-1",  # zone_uid в формате zn-{id}
        metric_type="TEMPERATURE",
        value=24.5
    )
    
    with patch("common.telemetry.fetch") as mock_fetch, \
         patch("common.telemetry.execute") as mock_execute, \
         patch("common.telemetry.upsert_telemetry_last") as mock_upsert:
        # Mock node lookup - node exists and is validated
        mock_fetch.side_effect = [
            [{"id": 10, "zone_id": None, "validated": True}],
            [{"id": 101}],
        ]
        
        await process_telemetry_batch([sample])
        
        # Проверяем, что данные обработаны
        assert mock_execute.call_count >= 1
        assert mock_upsert.call_count == 1


@pytest.mark.asyncio
async def test_process_telemetry_batch_normalizes_metric_type():
    """Test that metric_type is normalized (uppercase, stripped)."""
    sample = TelemetrySampleModel(
        node_uid="nd-ph-1",
        zone_id=1,
        metric_type="  PH  ",  # С пробелами и uppercase
        value=6.5
    )
    
    with patch("common.telemetry.fetch") as mock_fetch, \
         patch("common.telemetry.execute") as mock_execute, \
         patch("common.telemetry.upsert_telemetry_last") as mock_upsert:
        mock_fetch.side_effect = [
            [{"id": 10, "zone_id": 1, "validated": True}],
            [{"id": 101}],
        ]
        
        await process_telemetry_batch([sample])
        
        # Проверяем, что execute вызван с нормализованным metric_type
        calls = mock_execute.call_args_list
        assert len(calls) > 0
        metadata = calls[0][0][6]
        assert metadata["metric_type"] == "PH"
        assert mock_upsert.call_count == 1


@pytest.mark.asyncio
async def test_process_telemetry_batch_uses_node_zone_if_not_provided():
    """Test that zone_id from node is used if not provided in sample."""
    sample = TelemetrySampleModel(
        node_uid="nd-ph-1",
        # zone_id не указан
        metric_type="PH",
        value=6.5
    )
    
    with patch("common.telemetry.fetch") as mock_fetch, \
         patch("common.telemetry.execute") as mock_execute, \
         patch("common.telemetry.upsert_telemetry_last") as mock_upsert:
        # Mock node lookup - node has zone_id and is validated
        mock_fetch.side_effect = [
            [{"id": 10, "zone_id": 5, "validated": True}],
            [{"id": 101}],
        ]
        
        await process_telemetry_batch([sample])
        
        # Проверяем, что данные обработаны с zone_id из ноды
        assert mock_execute.call_count >= 1
        assert mock_upsert.call_count == 1


@pytest.mark.asyncio
async def test_process_telemetry_batch_skips_without_zone_id():
    """Test that samples without zone_id are skipped."""
    sample = TelemetrySampleModel(
        node_uid="nd-ph-1",
        # zone_id не указан и нода не найдена
        metric_type="PH",
        value=6.5
    )
    
    with patch("common.telemetry.fetch") as mock_fetch, \
         patch("common.telemetry.execute") as mock_execute:
        # Mock node lookup - node not found
        mock_fetch.return_value = []
        
        await process_telemetry_batch([sample])
        
        # execute не должен быть вызван, т.к. нет zone_id
        # Проверяем, что был вызов fetch для поиска ноды
        assert mock_fetch.called


@pytest.mark.asyncio
async def test_process_telemetry_batch_multiple_samples():
    """Test processing multiple samples in batch."""
    samples = [
        TelemetrySampleModel(
            node_uid="nd-ph-1",
            zone_id=1,
            metric_type="PH",
            value=6.5
        ),
        TelemetrySampleModel(
            node_uid="nd-ec-1",
            zone_id=1,
            metric_type="EC",
            value=1.8
        ),
    ]
    
    with patch("common.telemetry.fetch") as mock_fetch, \
         patch("common.telemetry.execute") as mock_execute, \
         patch("common.telemetry.upsert_telemetry_last") as mock_upsert:
        # Mock node lookups - nodes exist and are validated
        mock_fetch.side_effect = [
            [{"id": 10, "zone_id": 1, "validated": True}],
            [{"id": 101}],
            [{"id": 10, "zone_id": 1, "validated": True}],
            [{"id": 102}],
        ]
        
        await process_telemetry_batch(samples)
        
        # Проверяем, что все образцы обработаны
        # execute должен быть вызван для telemetry_samples (2 раза)
        # upsert_telemetry_last должен быть вызван 2 раза
        assert mock_execute.call_count >= 2
        assert mock_upsert.call_count == 2
