"""Rule-based V1 decision engine для roof vents (pure functions, unit-tested)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _linear_map(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    if x1 <= x0:
        return y1
    t = (x - x0) / (x1 - x0)
    t = _clamp(t, 0.0, 1.0)
    return y0 + t * (y1 - y0)


def _f(x: Any) -> float | None:
    if x is None:
        return None
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    return None


@dataclass(frozen=True)
class ClimateDecision:
    left_target_pct: int
    right_target_pct: int
    requested_symmetric_pct: int
    decision_reason: str
    factors: dict[str, Any]
    suppress_commands: bool
    emergency_overheat: bool
    command_sides: tuple[str, ...]


def compute_climate_decision(
    *,
    execution: Mapping[str, Any],
    control_mode: str,
    manual_override: Mapping[str, Any] | None,
    inside_temp_median: float | None,
    inside_temp_max: float | None,
    inside_rh_max: float | None,
    outside_temp: float | None,
    outside_humidity: float | None,
    wind_speed: float | None,
    wind_direction_deg: float | None,
    rain_detected: bool,
    outside_light_lux: float | None,
    schedule_day: bool,
    weather_fresh: bool,
    inside_fresh: bool,
    current_left_pct: int,
    current_right_pct: int,
    now_ts: float,
    last_command_ts: float | None,
) -> ClimateDecision:
    """Возвращает целевые проценты открытия левой/правой форточки (0..100)."""
    ex = dict(execution)
    mode = str(control_mode or "auto").strip().lower()

    gt_raw = ex.get("greenhouse_targets")
    gt: dict[str, Any] = gt_raw if isinstance(gt_raw, dict) else {}
    temp_min_v = _f(gt.get("temp_min_c"))
    temp_max_v = _f(gt.get("temp_max_c"))
    rh_max_v_cfg = _f(gt.get("humidity_max_pct"))
    if temp_min_v is None or temp_max_v is None or rh_max_v_cfg is None:
        raise ValueError("greenhouse_targets temp_min_c, temp_max_c and humidity_max_pct are required")
    temp_max = float(temp_max_v)
    temp_min = float(temp_min_v)
    rh_max = float(rh_max_v_cfg)

    _decision_interval = int(_f(ex.get("decision_interval_sec")) or 900)
    min_command_interval = int(_f(ex.get("min_command_interval_sec")) or 300)
    max_step = int(_f(ex.get("max_step_pct")) or 25)
    deadband = int(_f(ex.get("position_deadband_pct")) or 5)
    sensor_freshness = int(_f(ex.get("sensor_freshness_sec")) or 1200)

    day_min = int(_f(ex.get("day_min_open_pct")) or 0)
    day_max = int(_f(ex.get("day_max_open_pct")) or 100)
    night_min = int(_f(ex.get("night_min_open_pct")) or 0)
    night_max = int(_f(ex.get("night_max_open_pct")) or 20)
    daylight_lux = float(_f(ex.get("daylight_lux_threshold")) or 15000.0)

    temp_full_delta = float(_f(ex.get("temp_full_open_delta_c")) or 6.0)
    rh_full_delta = float(_f(ex.get("rh_full_open_delta_pct")) or 20.0)
    cold_margin = float(_f(ex.get("cold_guard_margin_c")) or 1.0)
    cold_max_open = int(_f(ex.get("cold_guard_max_open_pct")) or 10)
    outside_hotter_gain = float(_f(ex.get("outside_hotter_gain")) or 1.0)
    outside_wetter_gain = float(_f(ex.get("outside_wetter_gain")) or 1.0)

    wind_reduce = float(_f(ex.get("wind_reduce_threshold_ms")) or 8.0)
    wind_close = float(_f(ex.get("wind_close_threshold_ms")) or 12.0)
    if wind_close < wind_reduce:
        wind_close = wind_reduce

    wr_wind = int(_f(ex.get("wind_reduce_windward_max_pct")) or 25)
    wr_lee = int(_f(ex.get("wind_reduce_leeward_max_pct")) or 50)
    st_wind = int(_f(ex.get("wind_storm_windward_max_pct")) or 0)
    st_lee = int(_f(ex.get("wind_storm_leeward_max_pct")) or 10)
    rain_wind = int(_f(ex.get("rain_windward_position_pct")) or 0)
    rain_lee = int(_f(ex.get("rain_leeward_position_pct")) or 10)
    rain_unknown = int(_f(ex.get("rain_unknown_direction_max_pct")) or 5)

    overheat_temp = float(_f(ex.get("overheat_emergency_temp_c")) or 38.0)
    emergency_open = int(_f(ex.get("emergency_open_pct")) or 100)
    fallback_open = int(_f(ex.get("fallback_open_pct")) or 5)
    weather_stale_max_open = int(_f(ex.get("weather_stale_max_open_pct")) or 20)

    left_n = _f(ex.get("left_roof_normal_deg"))
    right_n = _f(ex.get("right_roof_normal_deg"))
    direction_known = left_n is not None and right_n is not None and wind_direction_deg is not None

    factors: dict[str, Any] = {
        "control_mode": mode,
        "weather_fresh": weather_fresh,
        "inside_fresh": inside_fresh,
        "direction_known": direction_known,
        "decision_interval_sec": _decision_interval,
        "sensor_freshness_sec": sensor_freshness,
    }

    if manual_override is not None and isinstance(manual_override, dict) and "left_position_pct" in manual_override:
        # caller guarantees override active window
        lo = int(manual_override.get("left_position_pct") or 0)
        ro = int(manual_override.get("right_position_pct") or 0)
        return ClimateDecision(
            left_target_pct=int(_clamp(lo, 0, 100)),
            right_target_pct=int(_clamp(ro, 0, 100)),
            requested_symmetric_pct=int(_clamp((lo + ro) / 2, 0, 100)),
            decision_reason="manual_override_active",
            factors={**factors, "override": dict(manual_override)},
            suppress_commands=False,
            emergency_overheat=False,
            command_sides=("left", "right"),
        )

    daylight = bool(schedule_day) or (
        outside_light_lux is not None and outside_light_lux >= daylight_lux and weather_fresh
    )
    if daylight:
        min_open, max_open = day_min, day_max
        base_open = int(_f(ex.get("day_base_open_pct")) or min_open)
    else:
        min_open, max_open = night_min, night_max
        base_open = int(_f(ex.get("night_base_open_pct")) or min_open)

    if not weather_fresh:
        max_open = min(max_open, weather_stale_max_open)
        if min_open > max_open:
            min_open = max_open

    base_open = int(_clamp(base_open, min_open, max_open))

    it_med = inside_temp_median if inside_fresh else None
    it_max = inside_temp_max if inside_fresh else None
    rh_max_v = inside_rh_max if inside_fresh else None

    emergency_overheat = bool(it_max is not None and it_max >= overheat_temp)

    temp_open = 0.0
    if it_med is not None:
        temp_delta = it_med - temp_max
        if temp_delta > 0:
            temp_open = _linear_map(temp_delta, 0.0, temp_full_delta, 0.0, 100.0)
        if outside_temp is not None and it_med is not None and outside_temp > it_med:
            temp_open *= outside_hotter_gain

    humidity_open = 0.0
    if rh_max_v is not None:
        rh_delta = rh_max_v - rh_max
        if rh_delta > 0:
            humidity_open = _linear_map(rh_delta, 0.0, rh_full_delta, 0.0, 100.0)
        if outside_humidity is not None and rh_max_v is not None and outside_humidity > rh_max_v:
            humidity_open *= outside_wetter_gain

    requested = float(fallback_open if not inside_fresh else max(base_open, temp_open, humidity_open))
    requested = _clamp(requested, float(min_open), float(max_open))

    if it_med is not None and not emergency_overheat and it_med <= temp_min + cold_margin:
        requested = min(requested, float(cold_max_open))

    if emergency_overheat:
        requested = max(requested, float(emergency_open))

    if not inside_fresh:
        requested = _clamp(float(fallback_open), float(min_open), float(max_open))

    windward_max = 100
    leeward_max = 100
    if weather_fresh and wind_speed is not None:
        if wind_speed >= wind_close:
            windward_max, leeward_max = st_wind, st_lee
        elif wind_speed >= wind_reduce:
            windward_max, leeward_max = wr_wind, wr_lee

    if weather_fresh and rain_detected:
        if direction_known:
            windward_max = min(windward_max, rain_wind)
            leeward_max = min(leeward_max, rain_lee)
        else:
            windward_max = min(windward_max, rain_unknown)
            leeward_max = min(leeward_max, rain_unknown)

    left_max = min(windward_max, leeward_max)
    right_max = min(windward_max, leeward_max)
    if direction_known and left_n is not None and right_n is not None and wind_direction_deg is not None:
        def _ang_dist(a: float, b: float) -> float:
            d = abs(a - b) % 360.0
            return min(d, 360.0 - d)

        d_left = _ang_dist(wind_direction_deg, left_n)
        d_right = _ang_dist(wind_direction_deg, right_n)
        if d_left <= d_right:
            left_max, right_max = windward_max, leeward_max
        else:
            left_max, right_max = leeward_max, windward_max

    left_raw = int(round(requested))
    right_raw = int(round(requested))
    left_t = int(_clamp(left_raw, 0, left_max))
    right_t = int(_clamp(right_raw, 0, right_max))

    def _limit_step(cur: int, target: int) -> int:
        delta = target - cur
        if abs(delta) <= max_step:
            return target
        return cur + (max_step if delta > 0 else -max_step)

    left_next = _limit_step(current_left_pct, left_t)
    right_next = _limit_step(current_right_pct, right_t)

    manual_emergency_enabled = ex.get("manual_emergency_override_enabled") is True
    allow_send = mode == "auto" or (
        mode == "manual" and emergency_overheat and bool(manual_emergency_enabled)
    )
    suppress = not allow_send
    if mode == "semi":
        suppress = True
    if (
        last_command_ts is not None
        and (now_ts - last_command_ts) < float(min_command_interval)
        and not emergency_overheat
    ):
        suppress = True
    command_sides: list[str] = []
    if abs(left_next - current_left_pct) >= deadband:
        command_sides.append("left")
    if abs(right_next - current_right_pct) >= deadband:
        command_sides.append("right")
    if not command_sides:
        suppress = True

    reason_parts = []
    if emergency_overheat:
        reason_parts.append("emergency_overheat")
    elif daylight:
        reason_parts.append("daylight")
    else:
        reason_parts.append("night")
    if temp_open > base_open:
        reason_parts.append("temp_high")
    if humidity_open > base_open:
        reason_parts.append("humidity_high")
    if weather_fresh and wind_speed is not None and wind_speed >= wind_reduce:
        reason_parts.append("wind_clamp")
    if weather_fresh and rain_detected:
        reason_parts.append("rain_clamp")

    return ClimateDecision(
        left_target_pct=left_next,
        right_target_pct=right_next,
        requested_symmetric_pct=int(round(requested)),
        decision_reason="+".join(reason_parts) if reason_parts else "schedule",
        factors=factors,
        suppress_commands=suppress,
        emergency_overheat=emergency_overheat,
        command_sides=tuple(command_sides),
    )
