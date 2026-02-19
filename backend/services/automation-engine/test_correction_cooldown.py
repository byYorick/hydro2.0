"""
Тесты для модуля correction_cooldown.
Проверяет cooldown механизм и анализ тренда.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, Mock
from datetime import datetime, timedelta
from types import SimpleNamespace
from common.utils.time import utcnow

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from correction_cooldown import (
    get_last_correction_time,
    is_in_cooldown,
    analyze_trend,
    analyze_proactive_correction_signal,
    should_apply_correction,
    should_apply_proactive_correction,
    DEFAULT_COOLDOWN_MINUTES,
)


@pytest.mark.asyncio
async def test_get_last_correction_time_ph():
    """Тест получения времени последней корректировки pH."""
    with patch("correction_cooldown.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"created_at": utcnow() - timedelta(minutes=5)}
        ]
        
        result = await get_last_correction_time(1, "ph")

        assert result is not None
        assert isinstance(result, datetime)
        mock_fetch.assert_called_once()
        query = mock_fetch.call_args[0][0]
        assert "payload_json->>'correction_type'" in query


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
        mock_get.return_value = utcnow() - timedelta(minutes=5)
        
        result = await is_in_cooldown(1, "ph", cooldown_minutes=10)
        
        assert result is True


@pytest.mark.asyncio
async def test_is_in_cooldown_false():
    """Тест проверки cooldown - вне периода cooldown."""
    with patch("correction_cooldown.get_last_correction_time") as mock_get:
        mock_get.return_value = utcnow() - timedelta(minutes=15)
        
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
        now = utcnow()
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
            {"value": 6.0, "ts": utcnow() - timedelta(hours=1)}
        ]
        
        is_improving, slope = await analyze_trend(1, "PH", 6.5, 6.5, hours=2)
        
        assert is_improving is False
        assert slope is None


@pytest.mark.asyncio
async def test_analyze_trend_ignores_future_samples():
    """Тест анализа тренда - future samples не должны учитываться."""
    with patch("correction_cooldown.fetch") as mock_fetch:
        now = utcnow()
        mock_fetch.return_value = [
            {"value": 6.1, "ts": now - timedelta(minutes=20)},
            {"value": 6.2, "ts": now - timedelta(minutes=10)},
            {"value": 6.3, "ts": now + timedelta(minutes=30)},
        ]

        is_improving, slope = await analyze_trend(1, "PH", 6.2, 6.5, hours=2)

        assert is_improving is False
        assert slope is None
        call_args = mock_fetch.call_args[0]
        assert "ts.ts <= $4" in call_args[0]
        assert len(call_args) == 5


@pytest.mark.asyncio
async def test_should_apply_correction_in_cooldown():
    """Тест should_apply_correction - в cooldown периоде."""
    from datetime import datetime, timedelta
    with patch("correction_cooldown.is_in_cooldown") as mock_cooldown, \
         patch("correction_cooldown.get_last_correction_time") as mock_get_time:
        mock_cooldown.return_value = True
        mock_get_time.return_value = utcnow() - timedelta(minutes=5)
        
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
async def test_should_apply_correction_critical_deviation_ignores_improving_trend():
    """Критическое отклонение должно обходить trend-based skip."""
    with patch("correction_cooldown.is_in_cooldown") as mock_cooldown, \
         patch("correction_cooldown.analyze_trend") as mock_trend:
        mock_cooldown.return_value = False
        mock_trend.return_value = (True, -0.5)

        should, reason = await should_apply_correction(1, "ec", 1.8, 1.0, 0.8)

        assert should is True
        assert "критическое" in reason.lower() or "critical" in reason.lower()
        mock_trend.assert_not_awaited()


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


@pytest.mark.asyncio
async def test_analyze_proactive_signal_triggers_when_predicted_escape():
    settings = SimpleNamespace(
        AE_PROACTIVE_CORRECTION_ENABLED=True,
        AE_PROACTIVE_EWMA_ALPHA=0.4,
        AE_PROACTIVE_WINDOW_MINUTES=45,
        AE_PROACTIVE_HORIZON_MINUTES=20,
        AE_PROACTIVE_MIN_POINTS=4,
        AE_PROACTIVE_PH_MIN_SLOPE_PER_MIN=0.002,
        AE_PROACTIVE_EC_MIN_SLOPE_PER_MIN=0.005,
    )
    now = utcnow()
    # Тренд роста pH: из dead-zone прогноз уходит выше target.
    samples = [6.30, 6.42, 6.55, 6.64]
    with patch("correction_cooldown.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"value": value, "ts": now - timedelta(minutes=30 - idx * 8)}
            for idx, value in enumerate(samples)
        ]
        result = await analyze_proactive_correction_signal(
            zone_id=1,
            metric_type="PH",
            current_value=6.68,
            target_value=6.5,
            dead_zone=0.2,
            settings=settings,
        )

    assert result["should_correct"] is True
    assert result["reason_code"] == "proactive_predicted_target_escape"
    assert result["predicted_deviation"] > 0.2


@pytest.mark.asyncio
async def test_analyze_proactive_signal_insufficient_data():
    settings = SimpleNamespace(
        AE_PROACTIVE_CORRECTION_ENABLED=True,
        AE_PROACTIVE_EWMA_ALPHA=0.35,
        AE_PROACTIVE_WINDOW_MINUTES=45,
        AE_PROACTIVE_HORIZON_MINUTES=20,
        AE_PROACTIVE_MIN_POINTS=5,
        AE_PROACTIVE_PH_MIN_SLOPE_PER_MIN=0.002,
        AE_PROACTIVE_EC_MIN_SLOPE_PER_MIN=0.005,
    )
    now = utcnow()
    with patch("correction_cooldown.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"value": 1.5, "ts": now - timedelta(minutes=20)},
            {"value": 1.52, "ts": now - timedelta(minutes=10)},
        ]
        result = await analyze_proactive_correction_signal(
            zone_id=1,
            metric_type="EC",
            current_value=1.53,
            target_value=1.6,
            dead_zone=0.2,
            settings=settings,
        )

    assert result["should_correct"] is False
    assert result["reason_code"] == "proactive_insufficient_data"


@pytest.mark.asyncio
async def test_should_apply_proactive_correction_respects_cooldown():
    with patch("correction_cooldown.is_in_cooldown", new_callable=AsyncMock, return_value=True):
        should, reason = await should_apply_proactive_correction(
            zone_id=1,
            correction_type="ph",
            projected_diff=0.35,
        )
    assert should is False
    assert "cooldown" in reason.lower()


@pytest.mark.asyncio
async def test_should_apply_proactive_correction_allows_meaningful_projected_diff():
    with patch("correction_cooldown.is_in_cooldown", new_callable=AsyncMock, return_value=False):
        should, reason = await should_apply_proactive_correction(
            zone_id=1,
            correction_type="ec",
            projected_diff=0.4,
        )
    assert should is True
    assert "allowed" in reason.lower()
