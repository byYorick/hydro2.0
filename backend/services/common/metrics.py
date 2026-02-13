"""
Единый словарь типов метрик для системы hydro2.0.
Стандартизирует все типы метрик для использования в Python-сервисах и Laravel.
"""
from enum import Enum


class Metric(str, Enum):
    """Стандартизированные типы метрик."""
    PH = "PH"
    EC = "EC"
    TEMPERATURE = "TEMPERATURE"
    HUMIDITY = "HUMIDITY"
    CO2 = "CO2"
    LIGHT_INTENSITY = "LIGHT_INTENSITY"
    WATER_LEVEL = "WATER_LEVEL"
    WATER_LEVEL_SWITCH = "WATER_LEVEL_SWITCH"
    FLOW_RATE = "FLOW_RATE"
    PUMP_CURRENT = "PUMP_CURRENT"
    SOIL_MOISTURE = "SOIL_MOISTURE"
    SOIL_TEMP = "SOIL_TEMP"
    WIND_SPEED = "WIND_SPEED"
    OUTSIDE_TEMP = "OUTSIDE_TEMP"


# Словарь канонических метрик для быстрого поиска
CANONICAL_METRICS = {m.value: m for m in Metric}


class UnknownMetricError(Exception):
    """Ошибка при неизвестном типе метрики."""
    
    def __init__(self, metric_type: str):
        self.metric_type = metric_type
        super().__init__(f"Unknown metric type: {metric_type}")


def normalize_metric_type(raw: str) -> str:
    """
    Нормализовать тип метрики:
    - Убирает пробелы (strip)
    - Приводит к верхнему регистру (upper)
    - Проверяет, что метрика известна
    - Возвращает каноническое значение
    
    Args:
        raw: Сырое значение типа метрики (может быть с пробелами, разным регистром)
    
    Returns:
        Каноническое значение метрики (uppercase, без пробелов)
    
    Raises:
        UnknownMetricError: Если метрика не найдена в CANONICAL_METRICS
    """
    key = raw.strip().upper()
    if key in CANONICAL_METRICS:
        return CANONICAL_METRICS[key].value
    raise UnknownMetricError(raw)
