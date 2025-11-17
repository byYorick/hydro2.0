"""
Единый словарь типов метрик для системы hydro2.0.
Стандартизирует все типы метрик для использования в Python-сервисах и Laravel.
"""
from enum import Enum


class Metric(str, Enum):
    """Стандартизированные типы метрик."""
    PH = "ph"
    EC = "ec"
    TEMP_AIR = "temp_air"
    TEMP_WATER = "temp_water"
    HUMIDITY = "humidity"
    CO2 = "co2"
    LUX = "lux"
    WATER_LEVEL = "water_level"
    FLOW_RATE = "flow_rate"
    PUMP_CURRENT = "pump_current"


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
    - Приводит к нижнему регистру (lower)
    - Проверяет, что метрика известна
    - Возвращает каноническое значение
    
    Args:
        raw: Сырое значение типа метрики (может быть с пробелами, разным регистром)
    
    Returns:
        Каноническое значение метрики (lowercase, без пробелов)
    
    Raises:
        UnknownMetricError: Если метрика не найдена в CANONICAL_METRICS
    """
    key = raw.strip().lower()
    if key in CANONICAL_METRICS:
        return CANONICAL_METRICS[key].value
    raise UnknownMetricError(raw)

