"""Момент кадра полива. Команды насосу здесь не публикуются."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Sequence
from zoneinfo import ZoneInfo

from ae4.domain.planting import (
    LightIntegralCursor,
    PhaseTargets,
    ShotMark,
    TelemetrySample,
)

_AIR_TEMP_CHANNELS = frozenset({"temperature", "air_temp_c"})
_AIR_HUM_CHANNELS = frozenset({"humidity", "air_rh"})
_ZONE_LIGHT_CHANNELS = frozenset({"light", "light_level"})
_OUTSIDE_LIGHT_CHANNELS = frozenset({"outside_light"})
_SOIL_MOISTURE_CHANNELS = frozenset({"soil_moisture"})
_SOLUTION_TEMP_CHANNELS = frozenset({"solution_temp_c"})


@dataclass(frozen=True)
class WaterDemandDecision:
    shoot: bool
    kind: str | None  # planned | extra | None
    reason_code: str
    human_message: str
    failed: bool
    integral: LightIntegralCursor
    vpd_kpa: float | None
    integral_status: str


@dataclass(frozen=True)
class LightWindow:
    start_local: datetime
    end_local: datetime


class WaterDemandConfigError(ValueError):
    """Ошибка конфигурации полива: кадра нет."""


def evaluate_water_demand(
    *,
    phase: PhaseTargets,
    now: datetime,
    timezone_name: str,
    telemetry_max_age_sec: int | None,
    last_shot: ShotMark | None,
    last_planned_shot_at: datetime | None,
    extra_used_in_half_interval: bool,
    successful_shots_in_window: int,
    integral: LightIntegralCursor,
    new_light_samples: tuple[TelemetrySample, ...],
    soil_moisture: TelemetrySample | None,
    temp_air: TelemetrySample | None,
    humidity_air: TelemetrySample | None,
    emergency_stop: bool,
    feed_empty: bool,
    ec_blocks_shot: bool = False,
) -> WaterDemandDecision:
    """
    Решение «кадр или нет» по §2.2.
    Метки кадров — аргументы (в рантайме из zone_events).
    """
    try:
        interval_sec, duration_sec = _require_interval_duration(phase=phase)
        tz = _require_timezone(timezone_name=timezone_name)
        window = resolve_light_window(phase=phase, now=now, tz=tz)
    except WaterDemandConfigError as exc:
        return WaterDemandDecision(
            shoot=False,
            kind=None,
            reason_code="irrigation_config_error",
            human_message=str(exc),
            failed=False,
            integral=integral,
            vpd_kpa=None,
            integral_status=integral.status,
        )

    advanced = advance_light_integral(
        cursor=integral,
        samples=new_light_samples,
        now=now,
        telemetry_max_age_sec=telemetry_max_age_sec,
        target_unit=phase.light_integral_unit,
        phase_started_at=phase.started_at,
    )

    if emergency_stop or feed_empty:
        return _pause(
            reason_code="estop_or_feed_empty",
            human_message="E-STOP или пустой feed — кадра нет",
            integral=advanced,
        )

    if ec_blocks_shot:
        return _pause(
            reason_code="ec_stale_blocks_shot",
            human_message="Протухший EC запрещает кадр",
            integral=advanced,
        )

    if last_shot is not None:
        pause_until = last_shot.at + timedelta(seconds=duration_sec)
        if now < pause_until:
            return _pause(
                reason_code="shot_pause",
                human_message="Пауза после кадра ещё не истекла",
                integral=advanced,
            )

    ceiling = daily_shot_ceiling(
        phase=phase,
        interval_sec=interval_sec,
        now=now,
        tz=tz,
        window=window,
    )
    if successful_shots_in_window >= ceiling:
        return _pause(
            reason_code="daily_ceiling",
            human_message="Суточный потолок успешных кадров исчерпан",
            integral=advanced,
        )

    planned_anchor = last_planned_shot_at if last_planned_shot_at is not None else phase.started_at
    half_start = planned_anchor
    half_end = planned_anchor + timedelta(seconds=interval_sec)
    extra_free = not extra_used_in_half_interval and half_start <= now < half_end

    moisture_outcome = _soil_moisture_outcome(
        phase=phase,
        sample=soil_moisture,
        now=now,
        telemetry_max_age_sec=telemetry_max_age_sec,
    )
    if moisture_outcome == "above":
        return _pause(
            reason_code="soil_moisture_above_max",
            human_message="Влажность выше нормы — кадра нет",
            integral=advanced,
        )

    drought = moisture_outcome == "below"
    if drought and extra_free:
        return _shoot(
            kind="extra",
            reason_code="soil_moisture_below_min",
            human_message="Сушь — внеочередной кадр",
            integral=advanced,
        )

    in_night = window is not None and not _now_in_window(now=now, window=window, tz=tz)
    if in_night and not drought:
        return _pause(
            reason_code="night_skip",
            human_message="Ночь: окно света задано и сейчас вне него — кадра нет",
            integral=advanced,
        )

    vpd_kpa, vpd_status = compute_vpd_kpa(
        phase=phase,
        temp_air=temp_air,
        humidity_air=humidity_air,
        now=now,
        telemetry_max_age_sec=telemetry_max_age_sec,
    )
    if (
        vpd_status == "ok"
        and phase.vpd_min is not None
        and vpd_kpa is not None
        and vpd_kpa < phase.vpd_min
        and not drought
    ):
        return WaterDemandDecision(
            shoot=False,
            kind=None,
            reason_code="vpd_below_min",
            human_message="VPD ниже нормы — кадра нет",
            failed=False,
            integral=advanced,
            vpd_kpa=vpd_kpa,
            integral_status=advanced.status,
        )

    if (
        vpd_status == "ok"
        and phase.vpd_max is not None
        and vpd_kpa is not None
        and vpd_kpa > phase.vpd_max
        and extra_free
    ):
        return WaterDemandDecision(
            shoot=True,
            kind="extra",
            reason_code="vpd_above_max",
            human_message="VPD выше нормы — внеочередной кадр",
            failed=False,
            integral=advanced,
            vpd_kpa=vpd_kpa,
            integral_status=advanced.status,
        )

    if (
        phase.light_integral_per_shot is not None
        and advanced.status == "ok"
        and advanced.accumulated >= phase.light_integral_per_shot
        and extra_free
    ):
        return WaterDemandDecision(
            shoot=True,
            kind="extra",
            reason_code="light_integral_reached",
            human_message="Интеграл света достиг цели кадра — внеочередной кадр",
            failed=False,
            integral=advanced,
            vpd_kpa=vpd_kpa,
            integral_status=advanced.status,
        )

    if now >= planned_anchor + timedelta(seconds=interval_sec):
        return WaterDemandDecision(
            shoot=True,
            kind="planned",
            reason_code="planned_interval",
            human_message="Плановый интервал вышел — плановый кадр",
            failed=False,
            integral=advanced,
            vpd_kpa=vpd_kpa,
            integral_status=advanced.status,
        )

    return WaterDemandDecision(
        shoot=False,
        kind=None,
        reason_code="waiting_interval",
        human_message="Интервал планового кадра ещё не вышел",
        failed=False,
        integral=advanced,
        vpd_kpa=vpd_kpa,
        integral_status=advanced.status,
    )


def daily_shot_ceiling(
    *,
    phase: PhaseTargets,
    interval_sec: int,
    now: datetime,
    tz: ZoneInfo,
    window: LightWindow | None,
) -> int:
    """
    Число успешных кадров, которое помещается шагом interval_sec от started_at.
    Не floor(длительность_окна / interval).
    """
    if window is not None:
        start = window.start_local
        end = window.end_local
    else:
        start, end = _local_calendar_day_bounds(now=now, tz=tz)

    count = _count_planned_moments_in_span(
        phase_started_at=_as_aware(phase.started_at, tz),
        interval_sec=interval_sec,
        span_start=start,
        span_end=end,
    )
    return count


def _count_planned_moments_in_span(
    *,
    phase_started_at: datetime,
    interval_sec: int,
    span_start: datetime,
    span_end: datetime,
) -> int:
    if interval_sec <= 0:
        raise WaterDemandConfigError("interval_sec должен быть > 0")
    count = 0
    moment = phase_started_at
    # Двигаемся шагом interval. Нельзя заменить на floor((end-start)/interval).
    guard = 0
    max_steps = 400_000
    while moment < span_end and guard < max_steps:
        if moment >= span_start:
            count += 1
        moment = moment + timedelta(seconds=interval_sec)
        guard += 1
    if guard >= max_steps:
        raise WaterDemandConfigError("слишком много шагов потолка кадров")
    # Не меньше 1, если в окно попадает хотя бы один плановый момент — count уже это.
    return count


def count_successful_shots_in_active_span(
    *,
    shot_times: Sequence[datetime],
    phase: PhaseTargets,
    now: datetime,
    timezone_name: str,
) -> int:
    """Успешные кадры, чей старт попал в текущее окно или локальные сутки.

    Кадр через полночь принадлежит окну старта. Кадры прошлых окон фазы
    в этот потолок не входят.
    """
    try:
        tz = _require_timezone(timezone_name=timezone_name)
        window = resolve_light_window(phase=phase, now=now, tz=tz)
    except WaterDemandConfigError:
        return 0
    if window is not None:
        span_start, span_end = window.start_local, window.end_local
    else:
        span_start, span_end = _local_calendar_day_bounds(now=now, tz=tz)
    count = 0
    for shot_at in shot_times:
        utc = _as_utc_naive(shot_at).replace(tzinfo=timezone.utc)
        local = utc.astimezone(tz)
        if span_start <= local < span_end:
            count += 1
    return count


def resolve_light_window(
    *,
    phase: PhaseTargets,
    now: datetime,
    tz: ZoneInfo,
) -> LightWindow | None:
    """Окно света: on_time/off_time или start+photoperiod. Новой колонки нет."""
    on_t = _normalize_time(phase.on_time)
    off_t = _normalize_time(phase.off_time)
    start_t = _normalize_time(phase.lighting_start_time)
    photo = phase.lighting_photoperiod_hours

    if on_t is None and off_t is None and start_t is None and photo is None:
        return None

    if on_t is not None or off_t is not None:
        if on_t is None or off_t is None:
            raise WaterDemandConfigError("окно света задано неполно: нужен on_time и off_time")
        if on_t == off_t:
            raise WaterDemandConfigError("начало окна света равно концу")
        return _window_from_clock_pair(now=now, tz=tz, start_clock=on_t, end_clock=off_t)

    if start_t is None or photo is None:
        raise WaterDemandConfigError(
            "окно света задано неполно: нужен lighting_start_time и lighting_photoperiod_hours"
        )
    if photo <= 0:
        raise WaterDemandConfigError("lighting_photoperiod_hours должен быть > 0")
    local_now = now.astimezone(tz)
    start_local = local_now.replace(
        hour=start_t[0], minute=start_t[1], second=start_t[2], microsecond=0
    )
    end_local = start_local + timedelta(seconds=float(photo) * 3600)
    if local_now < start_local:
        prev_start = start_local - timedelta(days=1)
        prev_end = prev_start + timedelta(seconds=float(photo) * 3600)
        if prev_start <= local_now < prev_end:
            return LightWindow(start_local=prev_start, end_local=prev_end)
    return LightWindow(start_local=start_local, end_local=end_local)


def _window_from_clock_pair(
    *,
    now: datetime,
    tz: ZoneInfo,
    start_clock: tuple[int, int, int],
    end_clock: tuple[int, int, int],
) -> LightWindow:
    local_now = now.astimezone(tz)
    start_local = local_now.replace(
        hour=start_clock[0], minute=start_clock[1], second=start_clock[2], microsecond=0
    )
    end_local = local_now.replace(
        hour=end_clock[0], minute=end_clock[1], second=end_clock[2], microsecond=0
    )
    if end_local <= start_local:
        end_local = end_local + timedelta(days=1)
    if local_now < start_local:
        prev_start = start_local - timedelta(days=1)
        prev_end = end_local - timedelta(days=1)
        if prev_start <= local_now < prev_end:
            return LightWindow(start_local=prev_start, end_local=prev_end)
    return LightWindow(start_local=start_local, end_local=end_local)


def _now_in_window(*, now: datetime, window: LightWindow, tz: ZoneInfo) -> bool:
    local = now.astimezone(tz)
    return window.start_local <= local < window.end_local


def _local_calendar_day_bounds(*, now: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Локальные сутки теплицы с учётом DST (23/24/25 ч)."""
    local = now.astimezone(tz)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    next_midnight = start + timedelta(days=1)
    return start, next_midnight


def _as_utc_naive(value: datetime) -> datetime:
    """Сравнение свежести не смешивает aware и naive: оба приводятся к UTC без tz."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def advance_light_integral(
    *,
    cursor: LightIntegralCursor,
    samples: tuple[TelemetrySample, ...],
    now: datetime,
    telemetry_max_age_sec: int | None,
    target_unit: str | None,
    phase_started_at: datetime,
) -> LightIntegralCursor:
    """Курсор: только пробы новее last_accounted_ts, прямоугольник value*Δt до следующей."""
    now = _as_utc_naive(now)
    phase_started_at = _as_utc_naive(phase_started_at)
    accounted_raw = (
        cursor.last_accounted_ts if cursor.last_accounted_ts is not None else phase_started_at
    )
    accounted = _as_utc_naive(accounted_raw)
    if telemetry_max_age_sec is None or telemetry_max_age_sec <= 0:
        return LightIntegralCursor(
            accumulated=0.0,
            last_accounted_ts=accounted,
            unit=target_unit,
            status="unseen",
            last_value=None,
        )

    lights: list[TelemetrySample] = []
    for sample in samples:
        picked = _pick_light_sample(sample)
        if picked is None or _as_utc_naive(picked.ts) <= accounted:
            continue
        if target_unit is not None and picked.unit is not None and picked.unit != target_unit:
            return LightIntegralCursor(
                accumulated=0.0,
                last_accounted_ts=accounted,
                unit=target_unit,
                status="unseen",
                last_value=None,
            )
        lights.append(picked)
    lights.sort(key=lambda s: s.ts)

    if not lights:
        if (now - accounted).total_seconds() > telemetry_max_age_sec:
            return replace(cursor, status="unseen")
        return cursor

    accumulated = cursor.accumulated if cursor.status == "ok" else 0.0
    prev_ts = accounted
    prev_value = cursor.last_value if cursor.status == "ok" else None
    last_unit = cursor.unit if cursor.status == "ok" else target_unit

    for light in lights:
        gap = (_as_utc_naive(light.ts) - prev_ts).total_seconds()
        if gap > telemetry_max_age_sec:
            return LightIntegralCursor(
                accumulated=0.0,
                last_accounted_ts=accounted,
                unit=target_unit,
                status="unseen",
                last_value=None,
            )
        if prev_value is not None:
            accumulated += prev_value * gap
        prev_ts = _as_utc_naive(light.ts)
        prev_value = light.value
        last_unit = light.unit if light.unit is not None else last_unit

    if (now - prev_ts).total_seconds() > telemetry_max_age_sec:
        return LightIntegralCursor(
            accumulated=0.0,
            last_accounted_ts=accounted,
            unit=target_unit,
            status="unseen",
            last_value=None,
        )
    return LightIntegralCursor(
        accumulated=accumulated,
        last_accounted_ts=prev_ts,
        unit=last_unit,
        status="ok",
        last_value=prev_value,
    )


def reset_integral_after_shot(
    *,
    phase: PhaseTargets,
    shot_at: datetime,
) -> LightIntegralCursor:
    """После успешного кадра курсор обнуляется с момента кадра."""
    return LightIntegralCursor(
        accumulated=0.0,
        last_accounted_ts=shot_at,
        unit=phase.light_integral_unit,
        status="ok",
        last_value=None,
    )


def compute_vpd_kpa(
    *,
    phase: PhaseTargets,
    temp_air: TelemetrySample | None,
    humidity_air: TelemetrySample | None,
    now: datetime,
    telemetry_max_age_sec: int | None,
) -> tuple[float | None, str]:
    """VPD только при свежих воздухе и влажности и живых vpd_min/vpd_max."""
    if phase.vpd_min is None or phase.vpd_max is None:
        return None, "silent"
    if not _is_air_temp(temp_air) or not _is_air_humidity(humidity_air):
        return None, "unseen"
    if not _fresh(sample=temp_air, now=now, telemetry_max_age_sec=telemetry_max_age_sec):
        return None, "unseen"
    if not _fresh(sample=humidity_air, now=now, telemetry_max_age_sec=telemetry_max_age_sec):
        return None, "unseen"
    assert temp_air is not None and humidity_air is not None
    temp_c = temp_air.value
    humidity_pct = humidity_air.value
    if temp_c < -40 or temp_c > 60 or humidity_pct < 0 or humidity_pct > 100:
        return None, "unseen"
    svp_kpa = 0.6108 * math.exp(17.27 * temp_c / (temp_c + 237.3))
    vpd_kpa = svp_kpa * (1.0 - humidity_pct / 100.0)
    return vpd_kpa, "ok"


def _soil_moisture_outcome(
    *,
    phase: PhaseTargets,
    sample: TelemetrySample | None,
    now: datetime,
    telemetry_max_age_sec: int | None,
) -> str | None:
    if phase.soil_moisture_min is None and phase.soil_moisture_max is None:
        return None
    if sample is None or sample.metric_type != "SOIL_MOISTURE":
        return None
    if sample.channel not in _SOIL_MOISTURE_CHANNELS:
        return None
    if phase.soil_moisture_unit is not None and sample.unit is not None:
        if phase.soil_moisture_unit != sample.unit:
            return None
    if not _fresh(sample=sample, now=now, telemetry_max_age_sec=telemetry_max_age_sec):
        return None
    if phase.soil_moisture_max is not None and sample.value > phase.soil_moisture_max:
        return "above"
    if phase.soil_moisture_min is not None and sample.value < phase.soil_moisture_min:
        return "below"
    return "in_band"


def _pick_light_sample(sample: TelemetrySample) -> TelemetrySample | None:
    if sample.metric_type == "LIGHT_INTENSITY" and sample.channel in _ZONE_LIGHT_CHANNELS:
        return sample
    if sample.metric_type == "OUTSIDE_LIGHT" and sample.channel in _OUTSIDE_LIGHT_CHANNELS:
        return sample
    return None


def _is_air_temp(sample: TelemetrySample | None) -> bool:
    if sample is None or sample.metric_type != "TEMPERATURE":
        return False
    return sample.channel in _AIR_TEMP_CHANNELS


def _is_air_humidity(sample: TelemetrySample | None) -> bool:
    if sample is None or sample.metric_type != "HUMIDITY":
        return False
    return sample.channel in _AIR_HUM_CHANNELS


def is_solution_temp(sample: TelemetrySample | None) -> bool:
    if sample is None or sample.metric_type != "TEMPERATURE":
        return False
    return sample.channel in _SOLUTION_TEMP_CHANNELS


def _require_interval_duration(*, phase: PhaseTargets) -> tuple[int, int]:
    if phase.interval_sec is None or phase.interval_sec <= 0:
        raise WaterDemandConfigError("interval_sec отсутствует или <= 0 — полива нет")
    if phase.duration_sec is None or phase.duration_sec <= 0:
        raise WaterDemandConfigError("duration_sec отсутствует или <= 0 — полива нет")
    return phase.interval_sec, phase.duration_sec


def _require_timezone(*, timezone_name: str) -> ZoneInfo:
    if not timezone_name or not timezone_name.strip():
        raise WaterDemandConfigError("timezone теплицы пуст — ошибка конфигурации")
    try:
        return ZoneInfo(timezone_name)
    except Exception as exc:
        raise WaterDemandConfigError(f"некорректный timezone теплицы: {timezone_name}") from exc


def _normalize_time(value: str | None) -> tuple[int, int, int] | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) < 2:
        raise WaterDemandConfigError(f"некорректное время окна: {value}")
    hour = int(parts[0])
    minute = int(parts[1])
    second = int(parts[2]) if len(parts) > 2 else 0
    return hour, minute, second


def _as_aware(dt: datetime, tz: ZoneInfo) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _fresh(
    *,
    sample: TelemetrySample | None,
    now: datetime,
    telemetry_max_age_sec: int | None,
) -> bool:
    if sample is None or telemetry_max_age_sec is None or telemetry_max_age_sec <= 0:
        return False
    age = _as_utc_naive(now) - _as_utc_naive(sample.ts)
    return age.total_seconds() <= telemetry_max_age_sec


def _pause(
    *,
    reason_code: str,
    human_message: str,
    integral: LightIntegralCursor,
) -> WaterDemandDecision:
    return WaterDemandDecision(
        shoot=False,
        kind=None,
        reason_code=reason_code,
        human_message=human_message,
        failed=False,
        integral=integral,
        vpd_kpa=None,
        integral_status=integral.status,
    )


def _shoot(
    *,
    kind: str,
    reason_code: str,
    human_message: str,
    integral: LightIntegralCursor,
) -> WaterDemandDecision:
    return WaterDemandDecision(
        shoot=True,
        kind=kind,
        reason_code=reason_code,
        human_message=human_message,
        failed=False,
        integral=integral,
        vpd_kpa=None,
        integral_status=integral.status,
    )


__all__ = [
    "WaterDemandDecision",
    "LightWindow",
    "WaterDemandConfigError",
    "evaluate_water_demand",
    "count_successful_shots_in_active_span",
    "daily_shot_ceiling",
    "resolve_light_window",
    "advance_light_integral",
    "reset_integral_after_shot",
    "compute_vpd_kpa",
    "is_solution_temp",
]
