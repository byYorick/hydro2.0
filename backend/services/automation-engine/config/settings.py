"""
Configuration settings for automation engine.
Вынесены все магические числа и константы.
"""
from typing import Dict, Any
from dataclasses import dataclass
import os
from common.env import get_settings as get_common_settings


@dataclass
class AutomationSettings:
    """Настройки автоматизации."""
    
    # Интервалы обработки
    MAIN_LOOP_SLEEP_SECONDS: int = 15
    CONFIG_FETCH_RETRY_SLEEP_SECONDS: int = 15
    CONFIG_FETCH_MIN_INTERVAL_SECONDS: int = int(os.getenv("CONFIG_FETCH_MIN_INTERVAL_SECONDS", "30"))
    
    # Параллельная обработка зон
    MAX_CONCURRENT_ZONES: int = int(os.getenv("MAX_CONCURRENT_ZONES", "50"))  # Максимум для масштабирования
    TARGET_CYCLE_TIME_SEC: int = int(os.getenv("TARGET_CYCLE_TIME_SEC", "15"))  # Целевое время цикла
    ADAPTIVE_CONCURRENCY: bool = os.getenv("ADAPTIVE_CONCURRENCY", "true").lower() == "true"  # Включить адаптивную конкурентность
    
    # Пороги для корректировки pH/EC
    PH_CORRECTION_THRESHOLD: float = 0.2  # Минимальная разница для корректировки
    EC_CORRECTION_THRESHOLD: float = 0.2
    PH_DOSING_MULTIPLIER: float = 10.0  # diff * 10 для pH
    EC_DOSING_MULTIPLIER: float = 100.0  # diff * 100 для EC

    # PID настройки pH
    PH_PID_DEAD_ZONE: float = 0.2
    PH_PID_CLOSE_ZONE: float = 0.5
    PH_PID_FAR_ZONE: float = 1.0
    PH_PID_KP_CLOSE: float = 10.0
    PH_PID_KI_CLOSE: float = 0.0
    PH_PID_KD_CLOSE: float = 0.0
    PH_PID_KP_FAR: float = 12.0
    PH_PID_KI_FAR: float = 0.0
    PH_PID_KD_FAR: float = 0.0
    PH_PID_MAX_OUTPUT: float = 50.0
    PH_PID_MIN_INTERVAL_MS: int = 60000
    PH_PID_ENABLE_AUTOTUNE: bool = False
    PH_PID_ADAPTATION_RATE: float = 0.05

    # PID настройки EC
    EC_PID_DEAD_ZONE: float = 0.2
    EC_PID_CLOSE_ZONE: float = 0.5
    EC_PID_FAR_ZONE: float = 1.0
    EC_PID_KP_CLOSE: float = 100.0
    EC_PID_KI_CLOSE: float = 0.0
    EC_PID_KD_CLOSE: float = 0.0
    EC_PID_KP_FAR: float = 120.0
    EC_PID_KI_FAR: float = 0.0
    EC_PID_KD_FAR: float = 0.0
    EC_PID_MAX_OUTPUT: float = 200.0
    EC_PID_MIN_INTERVAL_MS: int = 60000
    EC_PID_ENABLE_AUTOTUNE: bool = False
    EC_PID_ADAPTATION_RATE: float = 0.05
    # Поэтапное дозирование 4-компонентного питания (NPK/Ca/Mg/Micro)
    EC_COMPONENT_DOSE_DELAY_SEC: float = float(os.getenv("EC_COMPONENT_DOSE_DELAY_SEC", "8"))
    EC_COMPONENT_RECHECK_TOLERANCE: float = float(os.getenv("EC_COMPONENT_RECHECK_TOLERANCE", "0.05"))
    # Подтверждение команд дозирования (ACK/DONE) и повторы
    CORRECTION_COMMAND_TIMEOUT_SEC: float = float(os.getenv("CORRECTION_COMMAND_TIMEOUT_SEC", "5"))
    CORRECTION_COMMAND_TIMEOUT_BUFFER_SEC: float = float(os.getenv("CORRECTION_COMMAND_TIMEOUT_BUFFER_SEC", "2.5"))
    CORRECTION_COMMAND_MIN_TIMEOUT_SEC: float = float(os.getenv("CORRECTION_COMMAND_MIN_TIMEOUT_SEC", "3"))
    CORRECTION_COMMAND_MAX_ATTEMPTS: int = int(os.getenv("CORRECTION_COMMAND_MAX_ATTEMPTS", "2"))
    CORRECTION_COMMAND_RETRY_DELAY_SEC: float = float(os.getenv("CORRECTION_COMMAND_RETRY_DELAY_SEC", "0.5"))

    # PID расширенные guards/стабилизация
    PID_ANTI_WINDUP_MODE: str = os.getenv("PID_ANTI_WINDUP_MODE", "conditional")
    PID_BACK_CALCULATION_GAIN: float = float(os.getenv("PID_BACK_CALCULATION_GAIN", "0.2"))
    PID_DERIVATIVE_FILTER_ALPHA: float = float(os.getenv("PID_DERIVATIVE_FILTER_ALPHA", "0.35"))
    PID_AUTOTUNE_MODE: str = os.getenv("PID_AUTOTUNE_MODE", "disabled")
    
    # Максимальный возраст данных телеметрии для корректировки (в минутах)
    TELEMETRY_MAX_AGE_MINUTES: int = int(os.getenv("TELEMETRY_MAX_AGE_MINUTES", "30"))  # Не корректировать если данные старше 30 минут
    # Максимальный возраст correction flags для fail-closed gating (секунды)
    AE_CORRECTION_FLAGS_MAX_AGE_SEC: int = int(os.getenv("AE_CORRECTION_FLAGS_MAX_AGE_SEC", "300"))
    # Троттлинг zone-events при пропуске коррекций (секунды)
    AE_CORRECTION_SKIP_EVENT_THROTTLE_SEC: int = int(os.getenv("AE_CORRECTION_SKIP_EVENT_THROTTLE_SEC", "120"))
    # Троттлинг infra-alerts для stale correction flags (секунды)
    AE_CORRECTION_FLAGS_STALE_ALERT_THROTTLE_SEC: int = int(os.getenv("AE_CORRECTION_FLAGS_STALE_ALERT_THROTTLE_SEC", "120"))
    # Требовать timestamps для correction flags (1/0)
    AE_CORRECTION_FLAGS_REQUIRE_TS: bool = os.getenv("AE_CORRECTION_FLAGS_REQUIRE_TS", "1").strip().lower() in {"1", "true", "yes", "on"}
    # Safety bounds guard (S3): enabled by default, with emergency kill-switch
    AE_SAFETY_BOUNDS_ENABLED: bool = os.getenv("AE_SAFETY_BOUNDS_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
    AE_SAFETY_BOUNDS_KILL_SWITCH: bool = os.getenv("AE_SAFETY_BOUNDS_KILL_SWITCH", "0").strip().lower() in {"1", "true", "yes", "on"}
    # pH safety defaults
    AE_SAFETY_PH_HARD_PCT: float = float(os.getenv("AE_SAFETY_PH_HARD_PCT", "20"))
    AE_SAFETY_PH_ABS_MIN: float = float(os.getenv("AE_SAFETY_PH_ABS_MIN", "5.2"))
    AE_SAFETY_PH_ABS_MAX: float = float(os.getenv("AE_SAFETY_PH_ABS_MAX", "6.8"))
    AE_SAFETY_PH_MAX_DELTA_PER_MIN: float = float(os.getenv("AE_SAFETY_PH_MAX_DELTA_PER_MIN", "0.15"))
    # EC safety defaults
    AE_SAFETY_EC_HARD_PCT: float = float(os.getenv("AE_SAFETY_EC_HARD_PCT", "20"))
    AE_SAFETY_EC_ABS_MIN: float = float(os.getenv("AE_SAFETY_EC_ABS_MIN", "0.6"))
    AE_SAFETY_EC_ABS_MAX: float = float(os.getenv("AE_SAFETY_EC_ABS_MAX", "2.8"))
    AE_SAFETY_EC_MAX_DELTA_PER_MIN: float = float(os.getenv("AE_SAFETY_EC_MAX_DELTA_PER_MIN", "0.2"))
    # S9 proactive correction (EWMA/slope)
    AE_PROACTIVE_CORRECTION_ENABLED: bool = os.getenv("AE_PROACTIVE_CORRECTION_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
    AE_PROACTIVE_EWMA_ALPHA: float = float(os.getenv("AE_PROACTIVE_EWMA_ALPHA", "0.35"))
    AE_PROACTIVE_WINDOW_MINUTES: int = int(os.getenv("AE_PROACTIVE_WINDOW_MINUTES", "45"))
    AE_PROACTIVE_HORIZON_MINUTES: int = int(os.getenv("AE_PROACTIVE_HORIZON_MINUTES", "20"))
    AE_PROACTIVE_MIN_POINTS: int = int(os.getenv("AE_PROACTIVE_MIN_POINTS", "4"))
    AE_PROACTIVE_PH_MIN_SLOPE_PER_MIN: float = float(os.getenv("AE_PROACTIVE_PH_MIN_SLOPE_PER_MIN", "0.003"))
    AE_PROACTIVE_EC_MIN_SLOPE_PER_MIN: float = float(os.getenv("AE_PROACTIVE_EC_MIN_SLOPE_PER_MIN", "0.005"))
    # S9 equipment anomaly guard: dose -> no_effect xN windows
    AE_EQUIPMENT_ANOMALY_GUARD_ENABLED: bool = os.getenv("AE_EQUIPMENT_ANOMALY_GUARD_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
    AE_EQUIPMENT_ANOMALY_NO_EFFECT_WINDOW_SEC: int = int(os.getenv("AE_EQUIPMENT_ANOMALY_NO_EFFECT_WINDOW_SEC", "180"))
    AE_EQUIPMENT_ANOMALY_STREAK_THRESHOLD: int = int(os.getenv("AE_EQUIPMENT_ANOMALY_STREAK_THRESHOLD", "3"))
    AE_EQUIPMENT_ANOMALY_BLOCK_MINUTES: int = int(os.getenv("AE_EQUIPMENT_ANOMALY_BLOCK_MINUTES", "30"))
    AE_EQUIPMENT_ANOMALY_PH_MIN_DELTA: float = float(os.getenv("AE_EQUIPMENT_ANOMALY_PH_MIN_DELTA", "0.03"))
    AE_EQUIPMENT_ANOMALY_EC_MIN_DELTA: float = float(os.getenv("AE_EQUIPMENT_ANOMALY_EC_MIN_DELTA", "0.03"))
    # S10 runtime-state snapshot persistence (crash-recovery)
    AE_RUNTIME_STATE_PERSIST_ENABLED: bool = os.getenv("AE_RUNTIME_STATE_PERSIST_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
    AE_RUNTIME_STATE_SNAPSHOT_PATH: str = os.getenv(
        "AE_RUNTIME_STATE_SNAPSHOT_PATH",
        "/tmp/ae_runtime_state_snapshot.json",
    )
    
    # Порог для алерта о подряд пропусках проверки свежести
    FRESHNESS_CHECK_FAILED_ALERT_THRESHOLD: int = 5  # Количество подряд пропусков перед alert
    
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
