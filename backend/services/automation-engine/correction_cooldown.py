"""
Correction Cooldown Manager - предотвращение лавины корректировок.
Согласно AI-24: cooldown 10 минут, анализ тренда.

Модуль отслеживает:
- Время последней корректировки для каждой зоны и типа (pH/EC)
- Тренд изменения параметра (улучшается/ухудшается)
- Cooldown период (10 минут по умолчанию)
"""
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from common.utils.time import utcnow
from common.db import fetch, execute
import logging

logger = logging.getLogger(__name__)

# Cooldown период в минутах
DEFAULT_COOLDOWN_MINUTES = 10

# Минимальное количество точек для анализа тренда
MIN_TREND_POINTS = 3

# Порог улучшения тренда (если значение приближается к цели, не корректируем)
TREND_IMPROVEMENT_THRESHOLD = 0.05  # 0.05 единицы улучшения за последние измерения


async def get_last_correction_time(zone_id: int, correction_type: str) -> Optional[datetime]:
    """
    Получить время последней корректировки для зоны и типа.
    
    Args:
        zone_id: ID зоны
        correction_type: 'ph' или 'ec'
    
    Returns:
        datetime последней корректировки или None
    """
    # Ищем события корректировки по типу
    if correction_type == "ph":
        event_types = ['PH_CORRECTED', 'DOSING']
        pattern = "%ph%"
    elif correction_type == "ec":
        event_types = ['EC_DOSING', 'EC_CORRECTED', 'DOSING']
        pattern = "%ec%"
    else:
        return None
    
    rows = await fetch(
        """
        SELECT created_at
        FROM zone_events
        WHERE zone_id = $1
          AND type = ANY($2::text[])
          AND (details->>'correction_type' LIKE $3 OR details->>'type' LIKE $3)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        zone_id,
        event_types,
        pattern,
    )
    
    if rows and len(rows) > 0:
        return rows[0]["created_at"]
    return None


async def is_in_cooldown(zone_id: int, correction_type: str, cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES) -> bool:
    """
    Проверить, находится ли зона в cooldown периоде.
    
    Args:
        zone_id: ID зоны
        correction_type: 'ph' или 'ec'
        cooldown_minutes: Период cooldown в минутах
    
    Returns:
        True если в cooldown, False если можно корректировать
    """
    last_correction = await get_last_correction_time(zone_id, correction_type)
    if last_correction is None:
        return False
    
    cooldown_end = last_correction + timedelta(minutes=cooldown_minutes)
    return utcnow() < cooldown_end


async def analyze_trend(
    zone_id: int,
    metric_type: str,
    current_value: float,
    target_value: float,
    hours: int = 2
) -> Tuple[bool, Optional[float]]:
    """
    Анализ тренда изменения параметра.
    
    Args:
        zone_id: ID зоны
        metric_type: 'PH' или 'EC'
        current_value: Текущее значение
        target_value: Целевое значение
        hours: Период анализа в часах
    
    Returns:
        Tuple[is_improving, trend_slope]
        - is_improving: True если значение приближается к цели
        - trend_slope: Наклон тренда (положительный = улучшение для pH/EC)
    """
    cutoff_time = utcnow() - timedelta(hours=hours)
    
    normalized_metric = (metric_type or "").upper()
    rows = await fetch(
        """
        SELECT ts.value, ts.ts
        FROM telemetry_samples ts
        JOIN sensors s ON s.id = ts.sensor_id
        WHERE ts.zone_id = $1
          AND s.type = $2
          AND ts.ts >= $3
        ORDER BY ts.ts ASC
        """,
        zone_id,
        normalized_metric,
        cutoff_time,
    )
    
    if not rows or len(rows) < MIN_TREND_POINTS:
        # Недостаточно данных для анализа тренда
        return False, None
    
    values = [float(row["value"]) for row in rows if row["value"] is not None]
    if len(values) < MIN_TREND_POINTS:
        return False, None
    
    # Добавляем текущее значение
    values.append(current_value)
    
    # Вычисляем отклонения от цели для каждого значения
    deviations = [abs(v - target_value) for v in values]
    
    # Проверяем тренд: уменьшается ли отклонение?
    # Берем последние MIN_TREND_POINTS значений
    recent_deviations = deviations[-MIN_TREND_POINTS:]
    
    # Вычисляем среднее отклонение для первой и второй половины
    mid_point = len(recent_deviations) // 2
    first_half_avg = sum(recent_deviations[:mid_point]) / len(recent_deviations[:mid_point])
    second_half_avg = sum(recent_deviations[mid_point:]) / len(recent_deviations[mid_point:])
    
    # Если отклонение уменьшается, значит значение улучшается
    is_improving = (first_half_avg - second_half_avg) > TREND_IMPROVEMENT_THRESHOLD
    
    # Вычисляем наклон тренда (линейная регрессия)
    n = len(recent_deviations)
    if n < 2:
        trend_slope = None
    else:
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(recent_deviations) / n
        
        numerator = sum((x[i] - x_mean) * (recent_deviations[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator != 0:
            trend_slope = numerator / denominator
        else:
            trend_slope = None
    
    return is_improving, trend_slope


async def should_apply_correction(
    zone_id: int,
    correction_type: str,
    current_value: float,
    target_value: float,
    diff: float,
    cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES
) -> Tuple[bool, str]:
    """
    Определить, нужно ли применять корректировку.
    
    Args:
        zone_id: ID зоны
        correction_type: 'ph' или 'ec'
        current_value: Текущее значение
        target_value: Целевое значение
        diff: Разница между текущим и целевым значением
        cooldown_minutes: Период cooldown в минутах
    
    Returns:
        Tuple[should_correct, reason]
        - should_correct: True если нужно корректировать
        - reason: Причина решения
    """
    # Проверяем cooldown
    if await is_in_cooldown(zone_id, correction_type, cooldown_minutes):
        last_correction = await get_last_correction_time(zone_id, correction_type)
        if last_correction:
            time_since = utcnow() - last_correction
            return False, f"В cooldown периоде (последняя корректировка {time_since.seconds // 60} минут назад)"
        return False, "В cooldown периоде"
    
    # Анализируем тренд
    metric_type = 'PH' if correction_type == 'ph' else 'EC'
    is_improving, trend_slope = await analyze_trend(zone_id, metric_type, current_value, target_value)
    
    if is_improving:
        return False, f"Тренд улучшается (наклон: {trend_slope:.3f}), корректировка не требуется"
    
    # Если отклонение очень большое (> 0.5), корректируем независимо от тренда
    if abs(diff) > 0.5:
        return True, f"Критическое отклонение ({abs(diff):.2f}), корректировка необходима"
    
    # Если отклонение среднее (0.2-0.5) и тренд не улучшается, корректируем
    if abs(diff) > 0.2:
        if trend_slope is not None and trend_slope > 0:
            # Тренд ухудшается (отклонение растет)
            return True, f"Отклонение {abs(diff):.2f}, тренд ухудшается (наклон: {trend_slope:.3f})"
        elif trend_slope is None:
            # Недостаточно данных для анализа тренда
            return True, f"Отклонение {abs(diff):.2f}, недостаточно данных для анализа тренда"
        else:
            # Тренд стабильный или слегка улучшается, но отклонение все еще значительное
            return True, f"Отклонение {abs(diff):.2f}, требуется корректировка"
    
    # Отклонение небольшое (< 0.2), не корректируем
    return False, f"Отклонение {abs(diff):.2f} в пределах допустимого диапазона"


async def record_correction(zone_id: int, correction_type: str, details: Dict) -> None:
    """
    Записать информацию о выполненной корректировке.
    Это делается автоматически через create_zone_event, но можно использовать для логирования.
    """
    logger.info(
        f"Correction recorded: zone_id={zone_id}, type={correction_type}, details={details}"
    )
