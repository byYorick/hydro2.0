"""
Configuration settings for automation engine.
Вынесены все магические числа и константы.
"""
from typing import Dict, Any
from dataclasses import dataclass
from common.env import get_settings as get_common_settings


@dataclass
class AutomationSettings:
    """Настройки автоматизации."""
    
    # Интервалы обработки
    MAIN_LOOP_SLEEP_SECONDS: int = 15
    CONFIG_FETCH_RETRY_SLEEP_SECONDS: int = 15
    
    # Параллельная обработка зон
    MAX_CONCURRENT_ZONES: int = 5
    
    # Пороги для корректировки pH/EC
    PH_CORRECTION_THRESHOLD: float = 0.2  # Минимальная разница для корректировки
    EC_CORRECTION_THRESHOLD: float = 0.2
    PH_DOSING_MULTIPLIER: float = 10.0  # diff * 10 для pH
    EC_DOSING_MULTIPLIER: float = 100.0  # diff * 100 для EC
    
    # Пороги для критических отклонений
    PH_TOO_HIGH_THRESHOLD: float = 0.3
    PH_TOO_LOW_THRESHOLD: float = -0.3
    
    # Климат
    TEMP_HIGH_THRESHOLD: float = 2.0  # °C выше цели
    TEMP_LOW_THRESHOLD: float = 2.0  # °C ниже цели
    HUMIDITY_HIGH_THRESHOLD: float = 15.0  # % выше цели
    HUMIDITY_LOW_THRESHOLD: float = 15.0  # % ниже цели
    CO2_LOW_THRESHOLD: float = 400.0  # ppm
    TEMP_HYSTERESIS: float = 0.5  # °C
    HUMIDITY_HYSTERESIS: float = 3.0  # %
    MAX_FAN_SPEED: int = 100  # Максимальная скорость вентиляции
    
    # Освещение
    LIGHT_SENSOR_NIGHT_LEVEL: float = 10.0  # lux
    LIGHT_FAILURE_THRESHOLD: float = 20.0  # lux
    LIGHT_INTENSITY_MIN: int = 0
    LIGHT_INTENSITY_MAX: int = 100
    DEFAULT_LIGHT_START_HOUR: int = 6
    
    # Полив
    DEFAULT_IRRIGATION_DURATION_SEC: int = 60
    DEFAULT_RECIRCULATION_DURATION_SEC: int = 300  # 5 минут
    DEFAULT_RECIRCULATION_INTERVAL_MIN: int = 60  # 1 час
    
    # Health monitoring
    PH_STABILITY_HOURS: int = 2
    EC_STABILITY_HOURS: int = 2
    PH_STABILITY_STD_DEV_THRESHOLDS: Dict[float, float] = None  # Пороги для оценки стабильности
    EC_STABILITY_STD_DEV_THRESHOLDS: Dict[float, float] = None
    HEALTH_ALERT_PENALTY: float = 15.0  # Штраф за каждый активный алерт
    HEALTH_WATER_LEVEL_PENALTY: float = 70.0  # Штраф за низкий уровень воды
    HEALTH_FLOW_PENALTY: float = 50.0  # Штраф за отсутствие потока
    
    # Health score weights
    HEALTH_WEIGHTS: Dict[str, float] = None
    
    # Prometheus metrics
    PROMETHEUS_PORT: int = 9401
    
    def __post_init__(self):
        """Инициализация значений по умолчанию."""
        if self.PH_STABILITY_STD_DEV_THRESHOLDS is None:
            self.PH_STABILITY_STD_DEV_THRESHOLDS = {
                0.1: 100.0,
                0.2: 80.0,
                0.3: 60.0,
                0.5: 40.0,
            }
        
        if self.EC_STABILITY_STD_DEV_THRESHOLDS is None:
            self.EC_STABILITY_STD_DEV_THRESHOLDS = {
                0.05: 100.0,
                0.1: 80.0,
                0.15: 60.0,
                0.3: 40.0,
            }
        
        if self.HEALTH_WEIGHTS is None:
            self.HEALTH_WEIGHTS = {
                'ph_stability': 0.20,
                'ec_stability': 0.20,
                'climate_quality': 0.15,
                'node_uptime': 0.15,
                'alerts': 0.15,
                'water_level': 0.10,
                'flow': 0.05,
            }


# Глобальный экземпляр настроек
_settings: AutomationSettings = None


def get_settings() -> AutomationSettings:
    """Получить настройки автоматизации (singleton)."""
    global _settings
    if _settings is None:
        _settings = AutomationSettings()
    return _settings


def reload_settings() -> AutomationSettings:
    """Перезагрузить настройки (для тестирования)."""
    global _settings
    _settings = AutomationSettings()
    return _settings

