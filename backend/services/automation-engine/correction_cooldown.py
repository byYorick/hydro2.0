"""Cooldown/trend policies for correction controllers."""
from typing import Any, Dict, Optional, Tuple
from datetime import datetime, timedelta, timezone
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


def _resolve_correction_event_filters(correction_type: str) -> Optional[Tuple[list[str], list[str]]]:
    """Возвращает event types и точные payload-маркеры для pH/EC cooldown."""
    correction_key = str(correction_type or "").strip().lower()
    if correction_key == "ph":
        return (
            ["PH_CORRECTED", "DOSING"],
            ["add_acid", "add_base", "ph_correction", "ph"],
        )
    if correction_key == "ec":
        return (
            ["EC_DOSING", "EC_CORRECTED", "DOSING"],
            ["add_nutrients", "dilute", "ec_correction", "ec"],
        )
    return None


def _to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Нормализует datetime к UTC без tzinfo для операций с БД (timestamp без TZ)."""
    if value is None:
        return None
    if getattr(value, "tzinfo", None):
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _now_naive_utc() -> datetime:
    """Текущее время в UTC без tzinfo для сравнения с timestamp без TZ."""
    now = _to_naive_utc(utcnow())
    return now if now is not None else utcnow().replace(tzinfo=None)


async def get_last_correction_time(zone_id: int, correction_type: str) -> Optional[datetime]:
    """Возвращает timestamp последней корректировки pH/EC для зоны."""
    filters = _resolve_correction_event_filters(correction_type)
    if filters is None:
        return None

    event_types, payload_markers = filters
    rows = await fetch(
        """
        SELECT created_at
        FROM zone_events
        WHERE zone_id = $1
          AND type = ANY($2::text[])
          AND (
            LOWER(COALESCE(payload_json->>'correction_type', '')) = ANY($3::text[])
            OR LOWER(COALESCE(payload_json->>'type', '')) = ANY($3::text[])
          )
        ORDER BY created_at DESC
        LIMIT 1
        """,
        zone_id,
        event_types,
        payload_markers,
    )

    if rows and len(rows) > 0:
        return _to_naive_utc(rows[0]["created_at"])
    return None


async def is_in_cooldown(zone_id: int, correction_type: str, cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES) -> bool:
    """Проверяет cooldown для коррекции pH/EC."""
    last_correction = await get_last_correction_time(zone_id, correction_type)
    if last_correction is None:
        return False
    
    last_correction = _to_naive_utc(last_correction)
    if last_correction is None:
        return False
    cooldown_end = last_correction + timedelta(minutes=cooldown_minutes)
    return _now_naive_utc() < cooldown_end


async def analyze_trend(
    zone_id: int,
    metric_type: str,
    current_value: float,
    target_value: float,
    hours: int = 2
) -> Tuple[bool, Optional[float]]:
    """Возвращает `(is_improving, trend_slope)` по истории метрики."""
    analysis_now = _now_naive_utc()
    cutoff_time = analysis_now - timedelta(hours=hours)
    
    normalized_metric = (metric_type or "").upper()
    rows = await fetch(
        """
        SELECT ts.value, ts.ts
        FROM telemetry_samples ts
        JOIN sensors s ON s.id = ts.sensor_id
        WHERE ts.zone_id = $1
          AND s.type = $2
          AND ts.ts >= $3
          AND ts.ts <= $4
        ORDER BY ts.ts ASC
        """,
        zone_id,
        normalized_metric,
        cutoff_time,
        analysis_now,
    )
    
    if not rows or len(rows) < MIN_TREND_POINTS:
        # Недостаточно данных для анализа тренда
        return False, None
    
    values = []
    for row in rows:
        sample_ts = _to_naive_utc(row["ts"])
        if sample_ts is None or sample_ts > analysis_now:
            continue
        if row["value"] is not None:
            values.append(float(row["value"]))

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
    """Политика решения по корректировке с учётом cooldown и тренда."""
    # Проверяем cooldown
    if await is_in_cooldown(zone_id, correction_type, cooldown_minutes):
        last_correction = await get_last_correction_time(zone_id, correction_type)
        if last_correction:
            last_correction = _to_naive_utc(last_correction)
            time_since = _now_naive_utc() - last_correction
            return False, f"В cooldown периоде (последняя корректировка {int(time_since.total_seconds()) // 60} минут назад)"
        return False, "В cooldown периоде"
    
    # Если отклонение очень большое (> 0.5), корректируем независимо от тренда
    if abs(diff) > 0.5:
        return True, f"Критическое отклонение ({abs(diff):.2f}), корректировка необходима"

    # Анализируем тренд только для некритичных отклонений.
    metric_type = 'PH' if correction_type == 'ph' else 'EC'
    is_improving, trend_slope = await analyze_trend(zone_id, metric_type, current_value, target_value)
    
    if is_improving:
        return False, f"Тренд улучшается (наклон: {trend_slope:.3f}), корректировка не требуется"
    
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


def _resolve_min_slope_per_min(metric_type: str, settings: Any) -> float:
    metric = str(metric_type or "").upper()
    if metric == "PH":
        return float(getattr(settings, "AE_PROACTIVE_PH_MIN_SLOPE_PER_MIN", 0.003))
    return float(getattr(settings, "AE_PROACTIVE_EC_MIN_SLOPE_PER_MIN", 0.005))


def _build_ewma(values: list[float], alpha: float) -> list[float]:
    alpha = max(0.01, min(0.99, float(alpha)))
    ewma: list[float] = []
    for value in values:
        if not ewma:
            ewma.append(value)
            continue
        ewma.append(alpha * value + (1.0 - alpha) * ewma[-1])
    return ewma


def _linear_slope_per_min(series: list[float], points_ts: list[datetime]) -> Optional[float]:
    if len(series) < 2 or len(series) != len(points_ts):
        return None
    first_ts = points_ts[0]
    x = [max(0.0, (_to_naive_utc(ts) - first_ts).total_seconds() / 60.0) for ts in points_ts]
    y = [float(v) for v in series]
    n = len(y)
    x_mean = sum(x) / n
    y_mean = sum(y) / n
    numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
    denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return None
    return numerator / denominator


async def analyze_proactive_correction_signal(
    zone_id: int,
    metric_type: str,
    current_value: float,
    target_value: float,
    dead_zone: float,
    settings: Any,
) -> Dict[str, Any]:
    """S9: EWMA+slope сигнал proactive-correction внутри dead-zone."""
    if not bool(getattr(settings, "AE_PROACTIVE_CORRECTION_ENABLED", True)):
        return {"should_correct": False, "reason_code": "proactive_disabled"}

    window_minutes = max(5, int(getattr(settings, "AE_PROACTIVE_WINDOW_MINUTES", 45)))
    horizon_minutes = max(1, int(getattr(settings, "AE_PROACTIVE_HORIZON_MINUTES", 20)))
    min_points = max(3, int(getattr(settings, "AE_PROACTIVE_MIN_POINTS", 4)))
    alpha = float(getattr(settings, "AE_PROACTIVE_EWMA_ALPHA", 0.35))
    slope_threshold = max(0.0, _resolve_min_slope_per_min(metric_type, settings))
    metric = str(metric_type or "").upper()

    analysis_now = _now_naive_utc()
    cutoff_time = analysis_now - timedelta(minutes=window_minutes)

    rows = await fetch(
        """
        SELECT ts.value, ts.ts
        FROM telemetry_samples ts
        JOIN sensors s ON s.id = ts.sensor_id
        WHERE ts.zone_id = $1
          AND s.type = $2
          AND ts.ts >= $3
          AND ts.ts <= $4
        ORDER BY ts.ts ASC
        """,
        zone_id,
        metric,
        cutoff_time,
        analysis_now,
    )

    points: list[tuple[datetime, float]] = []
    for row in rows or []:
        sample_ts = _to_naive_utc(row.get("ts"))
        sample_val = row.get("value")
        if sample_ts is None or sample_val is None or sample_ts > analysis_now:
            continue
        try:
            points.append((sample_ts, float(sample_val)))
        except (TypeError, ValueError):
            continue
    points.append((analysis_now, float(current_value)))

    if len(points) < min_points:
        return {
            "should_correct": False,
            "reason_code": "proactive_insufficient_data",
            "samples_count": len(points),
        }

    values = [value for _, value in points]
    points_ts = [ts for ts, _ in points]
    ewma_values = _build_ewma(values, alpha)
    slope_per_min = _linear_slope_per_min(ewma_values, points_ts)
    if slope_per_min is None:
        return {"should_correct": False, "reason_code": "proactive_slope_unavailable"}

    if abs(slope_per_min) < slope_threshold:
        return {
            "should_correct": False,
            "reason_code": "proactive_slope_below_threshold",
            "slope_per_min": slope_per_min,
            "slope_threshold": slope_threshold,
        }

    current_error = float(current_value) - float(target_value)
    predicted_value = float(current_value) + slope_per_min * float(horizon_minutes)
    predicted_error = predicted_value - float(target_value)
    current_deviation = abs(current_error)
    predicted_deviation = abs(predicted_error)

    if predicted_deviation <= max(0.0, float(dead_zone)):
        return {
            "should_correct": False,
            "reason_code": "proactive_predicted_in_dead_zone",
            "slope_per_min": slope_per_min,
            "predicted_deviation": predicted_deviation,
        }

    if predicted_deviation <= current_deviation:
        return {
            "should_correct": False,
            "reason_code": "proactive_trend_not_worsening",
            "slope_per_min": slope_per_min,
            "predicted_deviation": predicted_deviation,
            "current_deviation": current_deviation,
        }

    return {
        "should_correct": True,
        "reason_code": "proactive_predicted_target_escape",
        "slope_per_min": slope_per_min,
        "predicted_value": predicted_value,
        "predicted_diff": predicted_error,
        "predicted_deviation": predicted_deviation,
        "current_deviation": current_deviation,
        "horizon_minutes": horizon_minutes,
        "samples_count": len(points),
    }


async def should_apply_proactive_correction(
    zone_id: int,
    correction_type: str,
    projected_diff: float,
    cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
) -> Tuple[bool, str]:
    """Cooldown gate для proactive-correction внутри dead-zone."""
    if await is_in_cooldown(zone_id, correction_type, cooldown_minutes):
        return False, "Proactive correction blocked by cooldown"
    if abs(float(projected_diff)) <= 0.2:
        return False, "Proactive correction skipped: projected diff too small"
    return True, "Proactive correction allowed"


async def record_correction(zone_id: int, correction_type: str, details: Dict) -> None:
    """Логирует информацию о выполненной корректировке."""
    logger.info(
        f"Correction recorded: zone_id={zone_id}, type={correction_type}, details={details}"
    )
