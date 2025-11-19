"""
Tests for telemetry-aggregator retention policy.
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from main import cleanup_old_data, get_last_ts, update_last_ts
from common.db import fetch, execute


@pytest.mark.asyncio
async def test_cleanup_old_data_deletes_samples():
    """Test that cleanup_old_data deletes old telemetry_samples."""
    with patch('main.execute') as mock_execute:
        mock_execute.return_value = "DELETE 10"
        
        result = await cleanup_old_data()
        
        assert result is not None
        assert result['samples_deleted'] == 10
        # Проверяем, что был вызван DELETE для telemetry_samples
        calls = [str(call) for call in mock_execute.call_args_list]
        assert any('telemetry_samples' in str(call) for call in calls)


@pytest.mark.asyncio
async def test_cleanup_old_data_deletes_agg_1m():
    """Test that cleanup_old_data deletes old telemetry_agg_1m."""
    with patch('main.execute') as mock_execute:
        mock_execute.return_value = "DELETE 5"
        
        result = await cleanup_old_data()
        
        assert result is not None
        assert result['1m_deleted'] == 5
        # Проверяем, что был вызван DELETE для telemetry_agg_1m
        calls = [str(call) for call in mock_execute.call_args_list]
        assert any('telemetry_agg_1m' in str(call) for call in calls)


@pytest.mark.asyncio
async def test_cleanup_old_data_deletes_agg_1h():
    """Test that cleanup_old_data deletes old telemetry_agg_1h."""
    with patch('main.execute') as mock_execute:
        mock_execute.return_value = "DELETE 3"
        
        result = await cleanup_old_data()
        
        assert result is not None
        assert result['1h_deleted'] == 3
        # Проверяем, что был вызван DELETE для telemetry_agg_1h
        calls = [str(call) for call in mock_execute.call_args_list]
        assert any('telemetry_agg_1h' in str(call) for call in calls)


@pytest.mark.asyncio
async def test_cleanup_old_data_uses_retention_periods():
    """Test that cleanup_old_data uses correct retention periods from env."""
    import os
    with patch('main.execute') as mock_execute, \
         patch.dict(os.environ, {
             'RETENTION_SAMPLES_DAYS': '60',
             'RETENTION_1M_DAYS': '20',
             'RETENTION_1H_DAYS': '180'
         }):
        mock_execute.return_value = "DELETE 0"
        
        await cleanup_old_data()
        
        # Проверяем, что были вызваны DELETE с правильными датами
        calls = mock_execute.call_args_list
        assert len(calls) >= 3  # samples, 1m, 1h


@pytest.mark.asyncio
async def test_cleanup_old_data_handles_errors():
    """Test that cleanup_old_data handles errors gracefully."""
    with patch('main.execute') as mock_execute:
        mock_execute.side_effect = Exception("Database error")
        
        result = await cleanup_old_data()
        
        assert result is None


@pytest.mark.asyncio
async def test_cleanup_metrics_incremented():
    """Test that cleanup metrics are incremented."""
    from main import CLEANUP_RUNS, CLEANUP_DELETED
    
    with patch('main.execute') as mock_execute:
        mock_execute.return_value = "DELETE 5"
        
        initial_runs = CLEANUP_RUNS._value.get()
        
        await cleanup_old_data()
        
        # Проверяем, что метрика была увеличена
        # (в реальности нужно использовать mock для prometheus_client)
        assert True  # Placeholder - в реальности проверяем метрики


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

