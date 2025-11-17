"""Tests for health_monitor module."""
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from health_monitor import (
    calculate_zone_health,
    calculate_ph_stability,
    calculate_ec_stability,
    calculate_climate_quality,
    count_active_alerts,
    check_node_status,
)


@pytest.mark.asyncio
async def test_calculate_ph_stability_stable():
    """Test pH stability calculation when pH is stable."""
    with patch("health_monitor.fetch") as mock_fetch:
        # Стабильные значения pH (6.5 ± 0.05)
        mock_fetch.return_value = [
            {"value": 6.5, "created_at": datetime.utcnow() - timedelta(hours=1)},
            {"value": 6.52, "created_at": datetime.utcnow() - timedelta(minutes=30)},
            {"value": 6.48, "created_at": datetime.utcnow()},
        ]
        
        stability = await calculate_ph_stability(1, hours=2)
        # Стабильность должна быть высокой (>80)
        assert stability >= 80


@pytest.mark.asyncio
async def test_calculate_ph_stability_unstable():
    """Test pH stability calculation when pH is unstable."""
    with patch("health_monitor.fetch") as mock_fetch:
        # Нестабильные значения pH (6.0 - 7.0)
        mock_fetch.return_value = [
            {"value": 6.0, "created_at": datetime.utcnow() - timedelta(hours=1)},
            {"value": 7.0, "created_at": datetime.utcnow() - timedelta(minutes=30)},
            {"value": 6.5, "created_at": datetime.utcnow()},
        ]
        
        stability = await calculate_ph_stability(1, hours=2)
        # Стабильность должна быть низкой (<60)
        assert stability < 60


@pytest.mark.asyncio
async def test_calculate_ec_stability():
    """Test EC stability calculation."""
    with patch("health_monitor.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"value": 1.8, "created_at": datetime.utcnow() - timedelta(hours=1)},
            {"value": 1.82, "created_at": datetime.utcnow()},
        ]
        
        stability = await calculate_ec_stability(1, hours=2)
        assert 0 <= stability <= 100


@pytest.mark.asyncio
async def test_calculate_climate_quality_good():
    """Test climate quality when parameters are close to targets."""
    with patch("health_monitor.fetch") as mock_fetch:
        # Телеметрия близка к целям
        mock_fetch.side_effect = [
            [{"metric_type": "TEMP_AIR", "value": 25.0}, {"metric_type": "HUMIDITY", "value": 60.0}],
            [{"targets": {"temp_air": 25.0, "humidity_air": 60.0}}],
        ]
        
        quality = await calculate_climate_quality(1)
        # Качество должно быть высоким (>80)
        assert quality >= 80


@pytest.mark.asyncio
async def test_calculate_climate_quality_bad():
    """Test climate quality when parameters are far from targets."""
    with patch("health_monitor.fetch") as mock_fetch:
        # Телеметрия далека от целей
        mock_fetch.side_effect = [
            [{"metric_type": "TEMP_AIR", "value": 30.0}, {"metric_type": "HUMIDITY", "value": 80.0}],
            [{"targets": {"temp_air": 25.0, "humidity_air": 60.0}}],
        ]
        
        quality = await calculate_climate_quality(1)
        # Качество должно быть низким (<70)
        assert quality < 70


@pytest.mark.asyncio
async def test_count_active_alerts():
    """Test counting active alerts."""
    with patch("health_monitor.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"count": 3},
        ]
        
        count = await count_active_alerts(1)
        assert count == 3


@pytest.mark.asyncio
async def test_check_node_status():
    """Test checking node status."""
    with patch("health_monitor.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"status": "online", "count": 5},
            {"status": "offline", "count": 1},
        ]
        
        status = await check_node_status(1)
        assert status["online_count"] == 5
        assert status["offline_count"] == 1
        assert status["total_count"] == 6


@pytest.mark.asyncio
async def test_calculate_zone_health():
    """Test overall zone health calculation."""
    with patch("health_monitor.calculate_ph_stability") as mock_ph, \
         patch("health_monitor.calculate_ec_stability") as mock_ec, \
         patch("health_monitor.calculate_climate_quality") as mock_climate, \
         patch("health_monitor.count_active_alerts") as mock_alerts, \
         patch("health_monitor.check_node_status") as mock_nodes, \
         patch("health_monitor.check_water_level") as mock_water, \
         patch("health_monitor.check_flow") as mock_flow:
        
        mock_ph.return_value = 90.0
        mock_ec.return_value = 85.0
        mock_climate.return_value = 80.0
        mock_alerts.return_value = 0
        mock_nodes.return_value = {"online_count": 5, "offline_count": 0, "total_count": 5}
        mock_water.return_value = (True, 0.5)
        mock_flow.return_value = (True, 2.0)
        
        health = await calculate_zone_health(1)
        
        assert "health_score" in health
        assert "health_status" in health
        assert "details" in health
        assert 0 <= health["health_score"] <= 100
        assert health["health_status"] in ["ok", "warning", "alarm"]


@pytest.mark.asyncio
async def test_calculate_zone_health_alarm():
    """Test zone health when multiple issues exist."""
    with patch("health_monitor.calculate_ph_stability") as mock_ph, \
         patch("health_monitor.calculate_ec_stability") as mock_ec, \
         patch("health_monitor.calculate_climate_quality") as mock_climate, \
         patch("health_monitor.count_active_alerts") as mock_alerts, \
         patch("health_monitor.check_node_status") as mock_nodes, \
         patch("health_monitor.check_water_level") as mock_water, \
         patch("health_monitor.check_flow") as mock_flow:
        
        mock_ph.return_value = 30.0  # Низкая стабильность
        mock_ec.return_value = 25.0
        mock_climate.return_value = 20.0
        mock_alerts.return_value = 5  # Много алертов
        mock_nodes.return_value = {"online_count": 2, "offline_count": 3, "total_count": 5}
        mock_water.return_value = (False, 0.15)  # Низкий уровень воды
        mock_flow.return_value = (False, 0.0)  # Нет потока
        
        health = await calculate_zone_health(1)
        
        # Должен быть статус "alarm"
        assert health["health_status"] == "alarm"
        assert health["health_score"] < 50

