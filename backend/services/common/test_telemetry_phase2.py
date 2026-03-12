"""Additional tests for telemetry processing with Phase 2 features."""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime
from common.telemetry import TelemetrySampleModel, process_telemetry_batch
from common.metrics import UnknownMetricError


@pytest.mark.asyncio
async def test_process_telemetry_batch_ignores_unvalidated_node():
    """Test that telemetry from unvalidated node is ignored."""
    sample = TelemetrySampleModel(
        node_uid="nd-ph-1",
        zone_id=1,
        metric_type="ph",
        value=6.5
    )
    
    with patch("common.telemetry.fetch") as mock_fetch, \
         patch("common.telemetry.execute") as mock_execute, \
         patch("common.telemetry.upsert_telemetry_last") as mock_upsert:
        # Mock node lookup - node exists but not validated
        mock_fetch.return_value = [{"id": 10, "zone_id": 1, "validated": False}]
        
        await process_telemetry_batch([sample])
        
        # execute should not be called because node is not validated
        mock_execute.assert_not_called()
        mock_upsert.assert_not_called()


@pytest.mark.asyncio
async def test_process_telemetry_batch_ignores_unknown_metric():
    """Test that telemetry with unknown metric type is ignored."""
    sample = TelemetrySampleModel(
        node_uid="nd-ph-1",
        zone_id=1,
        metric_type="unknown_metric_type",
        value=6.5
    )
    
    with patch("common.telemetry.fetch") as mock_fetch, \
         patch("common.telemetry.execute") as mock_execute, \
         patch("common.telemetry.upsert_telemetry_last") as mock_upsert:
        # Mock node lookup
        mock_fetch.return_value = [{"id": 10, "zone_id": 1, "validated": True}]
        
        await process_telemetry_batch([sample])
        
        # execute should not be called because metric type is unknown
        mock_execute.assert_not_called()
        mock_upsert.assert_not_called()


@pytest.mark.asyncio
async def test_process_telemetry_batch_normalizes_metric_type():
    """Test that metric types are normalized correctly."""
    sample = TelemetrySampleModel(
        node_uid="nd-ph-1",
        zone_id=1,
        metric_type="  PH  ",  # With spaces and uppercase
        value=6.5
    )
    
    with patch("common.telemetry.fetch") as mock_fetch, \
         patch("common.telemetry.execute") as mock_execute, \
         patch("common.telemetry.upsert_telemetry_last") as mock_upsert:
        # Mock node lookup
        mock_fetch.return_value = [{"id": 10, "zone_id": 1, "validated": True}]
        
        await process_telemetry_batch([sample])
        
        # Check that execute was called with normalized metric_type
        mock_execute.assert_called()
        call_args = mock_execute.call_args
        # metric_type should be normalized to "ph"
        assert call_args[0][4] == "ph"  # normalized_metric_type


@pytest.mark.asyncio
async def test_process_telemetry_batch_validated_node():
    """Test that telemetry from validated node is processed."""
    sample = TelemetrySampleModel(
        node_uid="nd-ph-1",
        zone_id=1,
        metric_type="ph",
        value=6.5
    )
    
    with patch("common.telemetry.fetch") as mock_fetch, \
         patch("common.telemetry.execute") as mock_execute, \
         patch("common.telemetry.upsert_telemetry_last") as mock_upsert:
        # Mock node lookup - node exists and is validated
        mock_fetch.return_value = [{"id": 10, "zone_id": 1, "validated": True}]
        
        await process_telemetry_batch([sample])
        
        # execute should be called for validated node
        assert mock_execute.call_count >= 1
        assert mock_upsert.call_count == 1

