"""
Tests for Digital Twin calibration module.
"""
import pytest
from unittest.mock import AsyncMock, patch, Mock
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import calibration module directly
from calibration import (
    calibrate_ph_model,
    calibrate_ec_model,
    calibrate_climate_model,
    calibrate_zone_models,
)


@pytest.mark.asyncio
async def test_calibrate_ph_model_insufficient_data():
    """Test PH model calibration with insufficient data."""
    with patch("calibration.fetch") as mock_fetch:
        mock_fetch.return_value = []  # Нет данных
        
        result = await calibrate_ph_model(1, days=7)
        
        # Должны вернуться значения по умолчанию
        assert result["buffer_capacity"] == 0.1
        assert result["natural_drift"] == 0.01
        assert result["correction_rate"] == 0.05


@pytest.mark.asyncio
async def test_calibrate_ph_model_natural_drift():
    """Test PH model calibration - natural drift calculation."""
    now = datetime.utcnow()
    
    # Создаем тестовые данные: pH постепенно снижается без дозировок
    ph_samples = [
        {"ts": now - timedelta(hours=10), "value": 6.5},
        {"ts": now - timedelta(hours=8), "value": 6.48},
        {"ts": now - timedelta(hours=6), "value": 6.46},
        {"ts": now - timedelta(hours=4), "value": 6.44},
        {"ts": now - timedelta(hours=2), "value": 6.42},
        {"ts": now, "value": 6.40},
    ]
    
    with patch("calibration.fetch") as mock_fetch:
        # Первый вызов - pH samples, второй - dosing commands
        mock_fetch.side_effect = [
            ph_samples,
            [],  # Нет команд дозирования
        ]
        
        result = await calibrate_ph_model(1, days=7)
        
        # Должен быть рассчитан natural_drift
        assert "natural_drift" in result
        assert result["natural_drift"] > 0
        assert result["natural_drift"] <= 0.05  # Ограничение


@pytest.mark.asyncio
async def test_calibrate_ph_model_correction_rate():
    """Test PH model calibration - correction rate after dosing."""
    now = datetime.utcnow()
    
    # pH samples с дозировкой в середине
    ph_samples = [
        {"ts": now - timedelta(hours=4), "value": 6.0},
        {"ts": now - timedelta(hours=3), "value": 6.0},
        {"ts": now - timedelta(hours=2), "value": 6.2},  # После дозировки
        {"ts": now - timedelta(hours=1), "value": 6.2},
        {"ts": now, "value": 6.2},
    ]
    
    # Команда дозировки
    dosing_commands = [
        {
            "created_at": now - timedelta(hours=2, minutes=30),
            "params": {"duration_ms": 5000},
        }
    ]
    
    with patch("calibration.fetch") as mock_fetch:
        mock_fetch.side_effect = [
            ph_samples,
            dosing_commands,
        ]
        
        result = await calibrate_ph_model(1, days=7)
        
        # Должен быть рассчитан correction_rate
        assert "correction_rate" in result
        assert result["correction_rate"] > 0
        assert result["correction_rate"] <= 0.2  # Ограничение


@pytest.mark.asyncio
async def test_calibrate_ec_model_insufficient_data():
    """Test EC model calibration with insufficient data."""
    with patch("calibration.fetch") as mock_fetch:
        mock_fetch.return_value = []
        
        result = await calibrate_ec_model(1, days=7)
        
        # Должны вернуться значения по умолчанию
        assert result["evaporation_rate"] == 0.02
        assert result["dilution_rate"] == 0.01
        assert result["nutrient_addition_rate"] == 0.03


@pytest.mark.asyncio
async def test_calibrate_ec_model_evaporation():
    """Test EC model calibration - evaporation rate."""
    now = datetime.utcnow()
    
    # EC постепенно увеличивается без дозировок (испарение)
    ec_samples = [
        {"ts": now - timedelta(hours=10), "value": 1.2},
        {"ts": now - timedelta(hours=8), "value": 1.21},
        {"ts": now - timedelta(hours=6), "value": 1.22},
        {"ts": now - timedelta(hours=4), "value": 1.23},
        {"ts": now - timedelta(hours=2), "value": 1.24},
        {"ts": now, "value": 1.25},
    ]
    
    with patch("calibration.fetch") as mock_fetch:
        mock_fetch.side_effect = [
            ec_samples,
            [],  # Нет команд дозирования
        ]
        
        result = await calibrate_ec_model(1, days=7)
        
        # Должен быть рассчитан evaporation_rate
        assert "evaporation_rate" in result
        assert result["evaporation_rate"] > 0
        assert result["evaporation_rate"] <= 0.05  # Ограничение


@pytest.mark.asyncio
async def test_calibrate_ec_model_nutrient_addition():
    """Test EC model calibration - nutrient addition rate."""
    now = datetime.utcnow()
    
    # EC samples с дозировкой питательных веществ
    ec_samples = [
        {"ts": now - timedelta(hours=4), "value": 1.2},
        {"ts": now - timedelta(hours=3), "value": 1.2},
        {"ts": now - timedelta(hours=2), "value": 1.25},  # После дозировки
        {"ts": now - timedelta(hours=1), "value": 1.25},
        {"ts": now, "value": 1.25},
    ]
    
    # Команда дозировки питательных веществ
    nutrient_commands = [
        {
            "created_at": now - timedelta(hours=2, minutes=30),
            "params": {"duration_ms": 5000},
        }
    ]
    
    with patch("calibration.fetch") as mock_fetch:
        mock_fetch.side_effect = [
            ec_samples,
            nutrient_commands,
        ]
        
        result = await calibrate_ec_model(1, days=7)
        
        # Должен быть рассчитан nutrient_addition_rate
        assert "nutrient_addition_rate" in result
        assert result["nutrient_addition_rate"] > 0
        assert result["nutrient_addition_rate"] <= 0.1  # Ограничение


@pytest.mark.asyncio
async def test_calibrate_climate_model_insufficient_data():
    """Test climate model calibration with insufficient data."""
    with patch("calibration.fetch") as mock_fetch:
        mock_fetch.return_value = []
        
        result = await calibrate_climate_model(1, days=7)
        
        # Должны вернуться значения по умолчанию
        assert result["heat_loss_rate"] == 0.5
        assert result["humidity_decay_rate"] == 0.02
        assert result["ventilation_cooling"] == 1.0


@pytest.mark.asyncio
async def test_calibrate_climate_model_heat_loss():
    """Test climate model calibration - heat loss rate."""
    now = datetime.utcnow()
    
    # Температура постепенно снижается
    temp_samples = [
        {"ts": now - timedelta(hours=10), "value": 25.0},
        {"ts": now - timedelta(hours=8), "value": 24.5},
        {"ts": now - timedelta(hours=6), "value": 24.0},
        {"ts": now - timedelta(hours=4), "value": 23.5},
        {"ts": now - timedelta(hours=2), "value": 23.0},
        {"ts": now, "value": 22.5},
    ]
    
    with patch("calibration.fetch") as mock_fetch:
        # Первый вызов - temp samples, второй - humidity samples
        mock_fetch.side_effect = [
            temp_samples,
            [],  # Нет данных по влажности
        ]
        
        result = await calibrate_climate_model(1, days=7)
        
        # Должен быть рассчитан heat_loss_rate
        assert "heat_loss_rate" in result
        assert result["heat_loss_rate"] > 0
        assert result["heat_loss_rate"] <= 1.5  # Ограничение


@pytest.mark.asyncio
async def test_calibrate_climate_model_humidity_decay():
    """Test climate model calibration - humidity decay rate."""
    now = datetime.utcnow()
    
    # Температура (нужна для первого запроса)
    temp_samples = [
        {"ts": now - timedelta(hours=2), "value": 22.0},
        {"ts": now, "value": 22.0},
    ]
    
    # Влажность постепенно снижается
    humidity_samples = [
        {"ts": now - timedelta(hours=10), "value": 70.0},
        {"ts": now - timedelta(hours=8), "value": 68.0},
        {"ts": now - timedelta(hours=6), "value": 66.0},
        {"ts": now - timedelta(hours=4), "value": 64.0},
        {"ts": now - timedelta(hours=2), "value": 62.0},
        {"ts": now, "value": 60.0},
    ]
    
    with patch("calibration.fetch") as mock_fetch:
        mock_fetch.side_effect = [
            temp_samples,
            humidity_samples,
        ]
        
        result = await calibrate_climate_model(1, days=7)
        
        # Должен быть рассчитан humidity_decay_rate
        assert "humidity_decay_rate" in result
        assert result["humidity_decay_rate"] > 0
        assert result["humidity_decay_rate"] <= 0.05  # Ограничение


@pytest.mark.asyncio
async def test_calibrate_zone_models_full():
    """Test full zone models calibration."""
    now = datetime.utcnow()
    
    # Подготовка данных для всех моделей
    ph_samples = [
        {"ts": now - timedelta(hours=2), "value": 6.0},
        {"ts": now, "value": 6.0},
    ]
    
    ec_samples = [
        {"ts": now - timedelta(hours=2), "value": 1.2},
        {"ts": now, "value": 1.2},
    ]
    
    temp_samples = [
        {"ts": now - timedelta(hours=2), "value": 22.0},
        {"ts": now, "value": 22.0},
    ]
    
    humidity_samples = [
        {"ts": now - timedelta(hours=2), "value": 60.0},
        {"ts": now, "value": 60.0},
    ]
    
    with patch("calibration.fetch") as mock_fetch, \
         patch("calibration.calibrate_ph_model") as mock_ph, \
         patch("calibration.calibrate_ec_model") as mock_ec, \
         patch("calibration.calibrate_climate_model") as mock_climate:
        
        mock_ph.return_value = {
            "buffer_capacity": 0.1,
            "natural_drift": 0.012,
            "correction_rate": 0.048,
        }
        
        mock_ec.return_value = {
            "evaporation_rate": 0.018,
            "dilution_rate": 0.01,
            "nutrient_addition_rate": 0.032,
        }
        
        mock_climate.return_value = {
            "heat_loss_rate": 0.52,
            "humidity_decay_rate": 0.019,
            "ventilation_cooling": 1.0,
        }
        
        result = await calibrate_zone_models(1, days=7)
        
        # Проверяем структуру результата
        assert result["zone_id"] == 1
        assert "calibrated_at" in result
        assert result["data_period_days"] == 7
        assert "models" in result
        
        # Проверяем модели
        assert "ph" in result["models"]
        assert "ec" in result["models"]
        assert "climate" in result["models"]
        
        # Проверяем параметры pH
        assert result["models"]["ph"]["buffer_capacity"] == 0.1
        assert result["models"]["ph"]["natural_drift"] == 0.012
        assert result["models"]["ph"]["correction_rate"] == 0.048
        
        # Проверяем параметры EC
        assert result["models"]["ec"]["evaporation_rate"] == 0.018
        assert result["models"]["ec"]["nutrient_addition_rate"] == 0.032
        
        # Проверяем параметры климата
        assert result["models"]["climate"]["heat_loss_rate"] == 0.52
        assert result["models"]["climate"]["humidity_decay_rate"] == 0.019


@pytest.mark.asyncio
async def test_calibrate_ph_model_with_dosing_commands():
    """Test PH model calibration with actual dosing commands."""
    now = datetime.utcnow()
    
    # pH samples: до дозировки 6.0, после 6.15
    ph_samples = [
        {"ts": now - timedelta(hours=3), "value": 6.0},
        {"ts": now - timedelta(hours=2, minutes=30), "value": 6.0},
        {"ts": now - timedelta(hours=2), "value": 6.15},  # После дозировки
        {"ts": now - timedelta(hours=1), "value": 6.15},
        {"ts": now, "value": 6.15},
    ]
    
    # Команда дозировки кислоты
    dosing_commands = [
        {
            "created_at": now - timedelta(hours=2, minutes=15),
            "params": {"duration_ms": 3000},
        }
    ]
    
    with patch("calibration.fetch") as mock_fetch:
        mock_fetch.side_effect = [
            ph_samples,
            dosing_commands,
        ]
        
        result = await calibrate_ph_model(1, days=7)
        
        # Проверяем, что параметры рассчитаны
        assert "natural_drift" in result
        assert "correction_rate" in result
        assert result["correction_rate"] > 0


@pytest.mark.asyncio
async def test_calibrate_ec_model_with_nutrient_commands():
    """Test EC model calibration with nutrient dosing commands."""
    now = datetime.utcnow()
    
    # EC samples: до дозировки 1.2, после 1.25
    ec_samples = [
        {"ts": now - timedelta(hours=3), "value": 1.2},
        {"ts": now - timedelta(hours=2, minutes=30), "value": 1.2},
        {"ts": now - timedelta(hours=2), "value": 1.25},  # После дозировки
        {"ts": now - timedelta(hours=1), "value": 1.25},
        {"ts": now, "value": 1.25},
    ]
    
    # Команда дозировки питательных веществ
    nutrient_commands = [
        {
            "created_at": now - timedelta(hours=2, minutes=15),
            "params": {"duration_ms": 5000},
        }
    ]
    
    with patch("calibration.fetch") as mock_fetch:
        mock_fetch.side_effect = [
            ec_samples,
            nutrient_commands,
        ]
        
        result = await calibrate_ec_model(1, days=7)
        
        # Проверяем, что параметры рассчитаны
        assert "evaporation_rate" in result
        assert "nutrient_addition_rate" in result
        assert result["nutrient_addition_rate"] > 0

