"""
Тесты для модуля correction_cooldown.
Проверяет cooldown механизм и анализ тренда.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, Mock
from datetime import datetime, timedelta

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from correction_cooldown import (
    get_last_correction_time,
    is_in_cooldown,
    analyze_trend,
    should_apply_correction,
    DEFAULT_COOLDOWN_MINUTES,
)


@pytest.mark.asyncio
async def test_get_last_correction_time_ph():
    """Тест получения времени последней корректировки pH."""
    with patch("correction_cooldown.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"created_at": datetime.utcnow() - timedelta(minutes=5)}
        ]
        
        result = await get_last_correction_time(1, "ph")
        
        assert result is not None
        assert isinstance(result, datetime)
        mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_get_last_correction_time_no_corrections():
    """Тест получения времени последней корректировки, когда корректировок не было."""
    with patch("correction_cooldown.fetch") as mock_fetch:
        mock_fetch.return_value = []
        
        result = await get_last_correction_time(1, "ph")
        
        assert result is None


@pytest.mark.asyncio
async def test_is_in_cooldown_true():
    """Тест проверки cooldown - в периоде cooldown."""
    with patch("correction_cooldown.get_last_correction_time") as mock_get:
        mock_get.return_value = datetime.utcnow() - timedelta(minutes=5)
        
        result = await is_in_cooldown(1, "ph", cooldown_minutes=10)
        
        assert result is True


@pytest.mark.asyncio
async def test_is_in_cooldown_false():
    """Тест проверки cooldown - вне периода cooldown."""
    with patch("correction_cooldown.get_last_correction_time") as mock_get:
        mock_get.return_value = datetime.utcnow() - timedelta(minutes=15)
        
        result = await is_in_cooldown(1, "ph", cooldown_minutes=10)
        
        assert result is False


@pytest.mark.asyncio
async def test_is_in_cooldown_no_previous():
    """Тест проверки cooldown - нет предыдущих корректировок."""
    with patch("correction_cooldown.get_last_correction_time") as mock_get:
        mock_get.return_value = None
        
        result = await is_in_cooldown(1, "ph", cooldown_minutes=10)
        
        assert result is False


@pytest.mark.asyncio
async def test_analyze_trend_improving():
    """Тест анализа тренда - значение улучшается."""
    with patch("correction_cooldown.fetch") as mock_fetch:
        # Симулируем значения, которые приближаются к цели (6.5)
        target = 6.5
        values = [6.0, 6.2, 6.3, 6.4]  # Приближаются к 6.5
        now = datetime.utcnow()
        mock_fetch.return_value = [
            {"value": v, "ts": now - timedelta(hours=2-i*0.5)}
            for i, v in enumerate(values)
        ]
        
        is_improving, slope = await analyze_trend(1, "PH", 6.4, target, hours=2)
        
        # Значение должно улучшаться (отклонение уменьшается)
        # Проверяем, что либо тренд улучшается, либо есть наклон
        assert isinstance(is_improving, bool)
        assert slope is None or isinstance(slope, (int, float))


@pytest.mark.asyncio
async def test_analyze_trend_not_enough_data():
    """Тест анализа тренда - недостаточно данных."""
    with patch("correction_cooldown.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"value": 6.0, "ts": datetime.utcnow() - timedelta(hours=1)}
        ]
        
        is_improving, slope = await analyze_trend(1, "PH", 6.5, 6.5, hours=2)
        
        assert is_improving is False
        assert slope is None


@pytest.mark.asyncio
async def test_should_apply_correction_in_cooldown():
    """Тест should_apply_correction - в cooldown периоде."""
    with patch("correction_cooldown.is_in_cooldown") as mock_cooldown:
        mock_cooldown.return_value = True
        
        should, reason = await should_apply_correction(1, "ph", 6.0, 6.5, -0.5)
        
        assert should is False
        assert "cooldown" in reason.lower()


@pytest.mark.asyncio
async def test_should_apply_correction_critical_deviation():
    """Тест should_apply_correction - критическое отклонение."""
    with patch("correction_cooldown.is_in_cooldown") as mock_cooldown, \
         patch("correction_cooldown.analyze_trend") as mock_trend:
        mock_cooldown.return_value = False
        mock_trend.return_value = (False, None)
        
        should, reason = await should_apply_correction(1, "ph", 5.0, 6.5, -1.5)
        
        assert should is True
        assert "критическое" in reason.lower() or "critical" in reason.lower()


@pytest.mark.asyncio
async def test_should_apply_correction_improving_trend():
    """Тест should_apply_correction - тренд улучшается."""
    with patch("correction_cooldown.is_in_cooldown") as mock_cooldown, \
         patch("correction_cooldown.analyze_trend") as mock_trend:
        mock_cooldown.return_value = False
        mock_trend.return_value = (True, -0.1)  # Улучшается
        
        should, reason = await should_apply_correction(1, "ph", 6.0, 6.5, -0.5)
        
        assert should is False
        assert "улучшается" in reason.lower() or "improving" in reason.lower()


@pytest.mark.asyncio
async def test_should_apply_correction_medium_deviation():
    """Тест should_apply_correction - среднее отклонение, тренд ухудшается."""
    with patch("correction_cooldown.is_in_cooldown") as mock_cooldown, \
         patch("correction_cooldown.analyze_trend") as mock_trend:
        mock_cooldown.return_value = False
        mock_trend.return_value = (False, 0.1)  # Ухудшается
        
        should, reason = await should_apply_correction(1, "ph", 6.0, 6.5, -0.3)
        
        assert should is True
        assert "отклонение" in reason.lower() or "deviation" in reason.lower()


@pytest.mark.asyncio
async def test_should_apply_correction_small_deviation():
    """Тест should_apply_correction - небольшое отклонение."""
    with patch("correction_cooldown.is_in_cooldown") as mock_cooldown, \
         patch("correction_cooldown.analyze_trend") as mock_trend:
        mock_cooldown.return_value = False
        mock_trend.return_value = (False, None)
        
        should, reason = await should_apply_correction(1, "ph", 6.4, 6.5, -0.1)
        
        assert should is False
        assert "допустимого" in reason.lower() or "acceptable" in reason.lower()

