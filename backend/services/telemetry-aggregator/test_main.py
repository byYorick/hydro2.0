"""Tests for telemetry-aggregator."""
import pytest
from unittest.mock import AsyncMock, patch, Mock
from datetime import datetime, timedelta
from common.utils.time import utcnow
from main import (
    get_last_ts,
    update_last_ts,
    aggregate_1m,
    aggregate_1h,
    aggregate_daily,
)


@pytest.mark.asyncio
async def test_get_last_ts_exists():
    """Test getting last timestamp when it exists."""
    last_ts = utcnow() - timedelta(hours=1)
    
    with patch("main.fetch") as mock_fetch:
        mock_fetch.return_value = [{"last_ts": last_ts}]
        
        result = await get_last_ts("1m")
        
    assert result == last_ts


@pytest.fixture(autouse=True)
def mock_simulation_events():
    with patch("main.record_simulation_event", new=AsyncMock(return_value=True)) as mock:
        yield mock


@pytest.mark.asyncio
async def test_get_last_ts_none():
    """Test getting last timestamp when it doesn't exist."""
    with patch("main.fetch") as mock_fetch:
        mock_fetch.return_value = [{"last_ts": None}]
        
        result = await get_last_ts("1m")
        
        assert result is None


@pytest.mark.asyncio
async def test_get_last_ts_no_record():
    """Test getting last timestamp when no record exists."""
    with patch("main.fetch") as mock_fetch:
        mock_fetch.return_value = []
        
        result = await get_last_ts("1m")
        
        assert result is None


@pytest.mark.asyncio
async def test_update_last_ts():
    """Test updating last timestamp."""
    last_ts = utcnow()
    
    with patch("main.execute") as mock_execute:
        await update_last_ts("1m", last_ts)
        
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        # Первый аргумент - SQL запрос, второй - last_ts ($1), третий - aggregation_type ($2)
        assert call_args[0][1] == last_ts
        assert call_args[0][2] == "1m"


@pytest.mark.asyncio
async def test_aggregate_1m_success(mock_simulation_events):
    """Test aggregating 1m telemetry."""
    last_ts = utcnow() - timedelta(hours=1)
    new_ts = utcnow()
    
    mock_rows = [
        {"zone_id": 1, "ts": new_ts - timedelta(minutes=5)},
        {"zone_id": 2, "ts": new_ts - timedelta(minutes=3)},
        {"zone_id": 1, "ts": new_ts},
    ]
    
    with patch("main.get_last_ts") as mock_get_ts, \
         patch("main.fetch") as mock_fetch, \
         patch("main.update_last_ts") as mock_update_ts:
        mock_get_ts.return_value = last_ts
        mock_fetch.return_value = mock_rows
        
        count = await aggregate_1m()
        
        assert count == len(mock_rows)
        mock_fetch.assert_called_once()
        mock_update_ts.assert_called_once()
        assert mock_simulation_events.await_count == 2


@pytest.mark.asyncio
async def test_aggregate_1m_no_data():
    """Test aggregating 1m when no new data."""
    last_ts = utcnow() - timedelta(hours=1)
    
    with patch("main.get_last_ts") as mock_get_ts, \
         patch("main.fetch") as mock_fetch, \
         patch("main.update_last_ts") as mock_update_ts:
        mock_get_ts.return_value = last_ts
        mock_fetch.return_value = []  # Нет новых данных
        
        count = await aggregate_1m()
        
        assert count == 0
        mock_update_ts.assert_not_called()


@pytest.mark.asyncio
async def test_aggregate_1m_with_time_bucket_fallback():
    """Test aggregating 1m with date_trunc fallback when time_bucket fails."""
    last_ts = utcnow() - timedelta(hours=1)
    new_ts = utcnow()
    
    mock_rows = [{"zone_id": 1, "ts": new_ts}]
    
    with patch("main.get_last_ts") as mock_get_ts, \
         patch("main.fetch") as mock_fetch, \
         patch("main.update_last_ts") as mock_update_ts:
        mock_get_ts.return_value = last_ts
        # Первый вызов (time_bucket) вызывает исключение, затем fallback возвращает данные
        mock_fetch.side_effect = [Exception("time_bucket not found"), mock_rows]
        
        count = await aggregate_1m()
        
        assert count == len(mock_rows)


@pytest.mark.asyncio
async def test_aggregate_1h_success():
    """Test aggregating 1h telemetry."""
    last_ts = utcnow() - timedelta(days=1)
    new_ts = utcnow()
    
    mock_rows = [
        {"zone_id": 1, "ts": new_ts - timedelta(hours=2)},
        {"zone_id": 1, "ts": new_ts - timedelta(hours=1)},
        {"zone_id": 1, "ts": new_ts},
    ]
    
    with patch("main.get_last_ts") as mock_get_ts, \
         patch("main.fetch") as mock_fetch, \
         patch("main.update_last_ts") as mock_update_ts:
        mock_get_ts.return_value = last_ts
        mock_fetch.return_value = mock_rows
        
        count = await aggregate_1h()
        
        assert count == len(mock_rows)
        mock_update_ts.assert_called_once()


@pytest.mark.asyncio
async def test_aggregate_1h_no_data():
    """Test aggregating 1h when no new data."""
    last_ts = utcnow() - timedelta(days=1)
    
    with patch("main.get_last_ts") as mock_get_ts, \
         patch("main.fetch") as mock_fetch, \
         patch("main.update_last_ts") as mock_update_ts:
        mock_get_ts.return_value = last_ts
        mock_fetch.return_value = []
        
        count = await aggregate_1h()
        
        assert count == 0
        mock_update_ts.assert_not_called()


@pytest.mark.asyncio
async def test_aggregate_daily_success():
    """Test aggregating daily telemetry."""
    last_ts = utcnow() - timedelta(days=7)
    new_date = utcnow().date()
    
    mock_rows = [
        {"zone_id": 1, "date": new_date - timedelta(days=2)},
        {"zone_id": 1, "date": new_date - timedelta(days=1)},
        {"zone_id": 1, "date": new_date},
    ]
    
    with patch("main.get_last_ts") as mock_get_ts, \
         patch("main.fetch") as mock_fetch, \
         patch("main.update_last_ts") as mock_update_ts:
        mock_get_ts.return_value = last_ts
        mock_fetch.return_value = mock_rows
        
        count = await aggregate_daily()
        
        assert count == len(mock_rows)
        mock_update_ts.assert_called_once()


@pytest.mark.asyncio
async def test_aggregate_daily_no_data():
    """Test aggregating daily when no new data."""
    last_ts = utcnow() - timedelta(days=7)
    
    with patch("main.get_last_ts") as mock_get_ts, \
         patch("main.fetch") as mock_fetch, \
         patch("main.update_last_ts") as mock_update_ts:
        mock_get_ts.return_value = last_ts
        mock_fetch.return_value = []
        
        count = await aggregate_daily()
        
        assert count == 0
        mock_update_ts.assert_not_called()


@pytest.mark.asyncio
async def test_aggregate_1m_error_handling():
    """Test aggregate_1m error handling."""
    last_ts = utcnow() - timedelta(hours=1)
    
    with patch("main.get_last_ts") as mock_get_ts, \
         patch("main.fetch") as mock_fetch:
        mock_get_ts.return_value = last_ts
        mock_fetch.side_effect = Exception("Database error")
        
        # Не должно выбрасывать исключение, должно вернуть 0
        count = await aggregate_1m()
        
        assert count == 0
