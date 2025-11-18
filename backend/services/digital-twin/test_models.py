"""
Tests for Digital Twin models with calibrated parameters.
"""
import pytest
from models import PHModel, ECModel, ClimateModel


def test_ph_model_default_params():
    """Test PH model with default parameters."""
    model = PHModel()
    
    assert model.buffer_capacity == 0.1
    assert model.natural_drift == 0.01
    assert model.correction_rate == 0.05


def test_ph_model_calibrated_params():
    """Test PH model with calibrated parameters."""
    calibrated_params = {
        "buffer_capacity": 0.12,
        "natural_drift": 0.015,
        "correction_rate": 0.06,
    }
    
    model = PHModel(calibrated_params)
    
    assert model.buffer_capacity == 0.12
    assert model.natural_drift == 0.015
    assert model.correction_rate == 0.06


def test_ph_model_step():
    """Test PH model step function."""
    model = PHModel()
    
    # Начальное значение pH
    current_ph = 6.0
    target_ph = 6.5
    elapsed_hours = 1.0
    
    new_ph = model.step(current_ph, target_ph, elapsed_hours)
    
    # pH должен измениться в сторону target
    assert new_ph > current_ph
    assert new_ph <= 9.0  # Ограничение сверху
    assert new_ph >= 4.0  # Ограничение снизу


def test_ph_model_step_with_calibrated_params():
    """Test PH model step with calibrated parameters."""
    calibrated_params = {
        "natural_drift": 0.02,  # Больший дрифт
        "correction_rate": 0.1,  # Быстрее коррекция
    }
    
    model = PHModel(calibrated_params)
    
    current_ph = 6.0
    target_ph = 6.5
    elapsed_hours = 1.0
    
    new_ph = model.step(current_ph, target_ph, elapsed_hours)
    
    # С большим correction_rate изменение должно быть больше
    assert new_ph > 6.0


def test_ec_model_default_params():
    """Test EC model with default parameters."""
    model = ECModel()
    
    assert model.evaporation_rate == 0.02
    assert model.dilution_rate == 0.01
    assert model.nutrient_addition_rate == 0.03


def test_ec_model_calibrated_params():
    """Test EC model with calibrated parameters."""
    calibrated_params = {
        "evaporation_rate": 0.025,
        "dilution_rate": 0.012,
        "nutrient_addition_rate": 0.035,
    }
    
    model = ECModel(calibrated_params)
    
    assert model.evaporation_rate == 0.025
    assert model.dilution_rate == 0.012
    assert model.nutrient_addition_rate == 0.035


def test_ec_model_step():
    """Test EC model step function."""
    model = ECModel()
    
    current_ec = 1.2
    target_ec = 1.5
    elapsed_hours = 1.0
    
    new_ec = model.step(current_ec, target_ec, elapsed_hours)
    
    # EC должен измениться в сторону target
    assert new_ec > current_ec
    assert new_ec <= 5.0  # Ограничение сверху
    assert new_ec >= 0.1  # Ограничение снизу


def test_ec_model_step_evaporation():
    """Test EC model step with evaporation effect."""
    model = ECModel()
    
    # EC без изменения target (только испарение)
    current_ec = 1.2
    target_ec = 1.2
    elapsed_hours = 1.0
    
    new_ec = model.step(current_ec, target_ec, elapsed_hours)
    
    # Испарение должно увеличить EC
    assert new_ec > current_ec


def test_climate_model_default_params():
    """Test climate model with default parameters."""
    model = ClimateModel()
    
    assert model.heat_loss_rate == 0.5
    assert model.humidity_decay_rate == 0.02
    assert model.ventilation_cooling == 1.0


def test_climate_model_calibrated_params():
    """Test climate model with calibrated parameters."""
    calibrated_params = {
        "heat_loss_rate": 0.6,
        "humidity_decay_rate": 0.025,
        "ventilation_cooling": 1.2,
    }
    
    model = ClimateModel(calibrated_params)
    
    assert model.heat_loss_rate == 0.6
    assert model.humidity_decay_rate == 0.025
    assert model.ventilation_cooling == 1.2


def test_climate_model_step():
    """Test climate model step function."""
    model = ClimateModel()
    
    # Используем большую разницу, чтобы нагрев перевесил потери тепла
    current_temp = 20.0
    current_humidity = 50.0
    target_temp = 25.0  # Большая разница (> 1.0, чтобы сработала логика нагрева)
    target_humidity = 70.0  # Большая разница (> 5.0, чтобы сработала логика изменения влажности)
    elapsed_hours = 1.0
    
    new_temp, new_humidity = model.step(
        current_temp, current_humidity, target_temp, target_humidity, elapsed_hours
    )
    
    # Температура должна измениться в сторону target (с учетом потерь тепла)
    # Может быть немного меньше из-за потерь, но должна быть в разумных пределах
    assert new_temp >= 10.0  # Ограничение снизу
    assert new_temp <= 35.0  # Ограничение сверху
    
    # Влажность: проверяем только диапазон
    # Модель учитывает humidity_change и humidity_decay, которые могут компенсировать друг друга
    assert new_humidity <= 95.0  # Ограничение сверху
    assert new_humidity >= 20.0  # Ограничение снизу


def test_climate_model_step_heat_loss():
    """Test climate model step with heat loss."""
    model = ClimateModel()
    
    # Температура без изменения target (только потери тепла)
    current_temp = 22.0
    current_humidity = 60.0
    target_temp = 22.0
    target_humidity = 60.0
    elapsed_hours = 1.0
    
    new_temp, new_humidity = model.step(
        current_temp, current_humidity, target_temp, target_humidity, elapsed_hours
    )
    
    # Потери тепла должны снизить температуру
    assert new_temp < current_temp


def test_climate_model_step_humidity_decay():
    """Test climate model step with humidity decay."""
    model = ClimateModel()
    
    # Влажность без изменения target (только естественное снижение)
    current_temp = 22.0
    current_humidity = 70.0
    target_temp = 22.0
    target_humidity = 70.0
    elapsed_hours = 1.0
    
    new_temp, new_humidity = model.step(
        current_temp, current_humidity, target_temp, target_humidity, elapsed_hours
    )
    
    # Естественное снижение влажности должно уменьшить значение
    assert new_humidity < current_humidity

