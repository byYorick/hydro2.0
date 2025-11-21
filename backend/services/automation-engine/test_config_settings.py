"""Tests for config/settings module."""
import pytest
from config.settings import (
    AutomationSettings,
    get_settings,
    reload_settings,
)


def test_automation_settings_defaults():
    """Test default values in AutomationSettings."""
    settings = AutomationSettings()
    
    assert settings.MAIN_LOOP_SLEEP_SECONDS == 15
    assert settings.MAX_CONCURRENT_ZONES == 5
    assert settings.PH_CORRECTION_THRESHOLD == 0.2
    assert settings.EC_CORRECTION_THRESHOLD == 0.2
    assert settings.PH_DOSING_MULTIPLIER == 10.0
    assert settings.EC_DOSING_MULTIPLIER == 100.0


def test_automation_settings_post_init():
    """Test __post_init__ sets default dicts."""
    settings = AutomationSettings()
    
    assert settings.PH_STABILITY_STD_DEV_THRESHOLDS is not None
    assert 0.1 in settings.PH_STABILITY_STD_DEV_THRESHOLDS
    assert settings.PH_STABILITY_STD_DEV_THRESHOLDS[0.1] == 100.0
    
    assert settings.EC_STABILITY_STD_DEV_THRESHOLDS is not None
    assert 0.05 in settings.EC_STABILITY_STD_DEV_THRESHOLDS
    
    assert settings.HEALTH_WEIGHTS is not None
    assert 'ph_stability' in settings.HEALTH_WEIGHTS
    assert settings.HEALTH_WEIGHTS['ph_stability'] == 0.20


def test_get_settings_singleton():
    """Test get_settings returns singleton."""
    settings1 = get_settings()
    settings2 = get_settings()
    
    assert settings1 is settings2


def test_reload_settings():
    """Test reload_settings creates new instance."""
    settings1 = get_settings()
    settings2 = reload_settings()
    
    assert settings1 is not settings2
    
    # После reload новый singleton
    settings3 = get_settings()
    assert settings3 is settings2


def test_custom_settings():
    """Test creating custom settings."""
    settings = AutomationSettings(
        MAIN_LOOP_SLEEP_SECONDS=30,
        MAX_CONCURRENT_ZONES=10,
        PH_CORRECTION_THRESHOLD=0.3
    )
    
    assert settings.MAIN_LOOP_SLEEP_SECONDS == 30
    assert settings.MAX_CONCURRENT_ZONES == 10
    assert settings.PH_CORRECTION_THRESHOLD == 0.3
    # Остальные значения по умолчанию
    assert settings.EC_CORRECTION_THRESHOLD == 0.2


def test_settings_thresholds():
    """Test threshold values."""
    settings = AutomationSettings()
    
    assert settings.PH_TOO_HIGH_THRESHOLD == 0.3
    assert settings.PH_TOO_LOW_THRESHOLD == -0.3
    assert settings.TEMP_HIGH_THRESHOLD == 2.0
    assert settings.HUMIDITY_HIGH_THRESHOLD == 15.0


def test_settings_climate():
    """Test climate-related settings."""
    settings = AutomationSettings()
    
    assert settings.TEMP_HYSTERESIS == 0.5
    assert settings.HUMIDITY_HYSTERESIS == 3.0
    assert settings.MAX_FAN_SPEED == 100


def test_settings_irrigation():
    """Test irrigation-related settings."""
    settings = AutomationSettings()
    
    assert settings.DEFAULT_IRRIGATION_DURATION_SEC == 60
    assert settings.DEFAULT_RECIRCULATION_DURATION_SEC == 300
    assert settings.DEFAULT_RECIRCULATION_INTERVAL_MIN == 60


def test_settings_health():
    """Test health monitoring settings."""
    settings = AutomationSettings()
    
    assert settings.PH_STABILITY_HOURS == 2
    assert settings.EC_STABILITY_HOURS == 2
    assert settings.HEALTH_ALERT_PENALTY == 15.0
    assert settings.HEALTH_WATER_LEVEL_PENALTY == 70.0

