"""
Тесты для проверки обработки неправильных типов данных в PID конфигах
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.pid_config_service import get_config, _json_to_pid_config
from utils.adaptive_pid import AdaptivePidConfig, PidZone, PidZoneCoeffs
from config.settings import get_settings


def test_json_to_pid_config_handles_invalid_zone_coeffs_type():
    """Тест: обработка неправильного типа zone_coeffs"""
    config_json = {
        'target': 6.0,
        'dead_zone': 0.2,
        'close_zone': 0.5,
        'far_zone': 1.0,
        'zone_coeffs': 'invalid_string',  # Неправильный тип
        'max_output': 50.0,
        'min_interval_ms': 60000,
        'enable_autotune': False,
        'adaptation_rate': 0.05,
    }
    
    # Должен использовать дефолтные значения вместо падения
    config = _json_to_pid_config(config_json, 6.0, 'ph')
    
    assert config is not None
    assert config.setpoint == 6.0
    # Должны использоваться дефолтные коэффициенты из settings
    settings = get_settings()
    assert config.zone_coeffs[PidZone.CLOSE].kp == settings.PH_PID_KP_CLOSE


def test_json_to_pid_config_handles_missing_close_coeffs():
    """Тест: обработка отсутствующих коэффициентов close"""
    config_json = {
        'target': 6.0,
        'dead_zone': 0.2,
        'close_zone': 0.5,
        'far_zone': 1.0,
        'zone_coeffs': {
            # close отсутствует
            'far': {'kp': 12.0, 'ki': 0.0, 'kd': 0.0},
        },
        'max_output': 50.0,
        'min_interval_ms': 60000,
        'enable_autotune': False,
        'adaptation_rate': 0.05,
    }
    
    config = _json_to_pid_config(config_json, 6.0, 'ph')
    
    assert config is not None
    # Должны использоваться дефолтные коэффициенты для close
    settings = get_settings()
    assert config.zone_coeffs[PidZone.CLOSE].kp == settings.PH_PID_KP_CLOSE
    assert config.zone_coeffs[PidZone.FAR].kp == 12.0


def test_json_to_pid_config_handles_invalid_close_coeffs_type():
    """Тест: обработка неправильного типа коэффициентов close"""
    config_json = {
        'target': 6.0,
        'dead_zone': 0.2,
        'close_zone': 0.5,
        'far_zone': 1.0,
        'zone_coeffs': {
            'close': 'invalid_string',  # Неправильный тип
            'far': {'kp': 12.0, 'ki': 0.0, 'kd': 0.0},
        },
        'max_output': 50.0,
        'min_interval_ms': 60000,
        'enable_autotune': False,
        'adaptation_rate': 0.05,
    }
    
    config = _json_to_pid_config(config_json, 6.0, 'ph')
    
    assert config is not None
    # Должны использоваться дефолтные коэффициенты для close
    settings = get_settings()
    assert config.zone_coeffs[PidZone.CLOSE].kp == settings.PH_PID_KP_CLOSE


def test_json_to_pid_config_handles_missing_zone_coeffs():
    """Тест: обработка полного отсутствия zone_coeffs"""
    config_json = {
        'target': 6.0,
        'dead_zone': 0.2,
        'close_zone': 0.5,
        'far_zone': 1.0,
        # zone_coeffs отсутствует
        'max_output': 50.0,
        'min_interval_ms': 60000,
        'enable_autotune': False,
        'adaptation_rate': 0.05,
    }
    
    config = _json_to_pid_config(config_json, 6.0, 'ph')
    
    assert config is not None
    # Должны использоваться дефолтные коэффициенты
    settings = get_settings()
    assert config.zone_coeffs[PidZone.CLOSE].kp == settings.PH_PID_KP_CLOSE
    assert config.zone_coeffs[PidZone.FAR].kp == settings.PH_PID_KP_FAR
    # Dead zone всегда имеет нулевые коэффициенты
    assert config.zone_coeffs[PidZone.DEAD].kp == 0.0

