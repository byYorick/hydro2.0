"""
Helpers for reading targets with support for structured and legacy formats.
Centralizes schema mismatch warnings to avoid silent no-ops.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Optional, Tuple
import logging

from prometheus_client import Counter

logger = logging.getLogger(__name__)

TARGETS_SCHEMA_ERRORS = Counter(
    "targets_schema_errors_total",
    "Targets schema mismatch errors",
    ["controller"],
)

_WARNED_SCHEMA_KEYS: set[tuple[int, str, str]] = set()


def _warn_schema_mismatch(controller: str, zone_id: Optional[int], detail: str) -> None:
    zone_key = zone_id if zone_id is not None else -1
    key = (zone_key, controller, detail)
    if key in _WARNED_SCHEMA_KEYS:
        return
    _WARNED_SCHEMA_KEYS.add(key)
    TARGETS_SCHEMA_ERRORS.labels(controller=controller).inc()
    if zone_id is not None:
        logger.warning(
            "Zone %s: targets schema mismatch (%s)",
            zone_id,
            detail,
            extra={"zone_id": zone_id, "controller": controller},
        )
    else:
        logger.warning(
            "Targets schema mismatch (%s)",
            detail,
            extra={"controller": controller},
        )


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_photoperiod(light_hours: Any) -> Optional[tuple[time, time]]:
    """
    Парсинг фотопериода из targets.

    Поддерживает форматы:
    - "06:00-22:00" (строка)
    - 16 (число часов, начиная с 06:00)
    - {"start": "06:00", "end": "22:00"} (dict)

    Returns:
        (start_time, end_time) или None
    """
    if light_hours is None:
        return None

    if isinstance(light_hours, (int, float)):
        # Число часов, по умолчанию начинаем с 06:00
        hours = int(light_hours)
        start = time(6, 0)
        end_hour = (6 + hours) % 24
        end = time(end_hour, 0)
        return (start, end)

    if isinstance(light_hours, str):
        # Формат "06:00-22:00"
        if "-" in light_hours:
            parts = light_hours.split("-")
            if len(parts) == 2:
                try:
                    start_parts = parts[0].strip().split(":")
                    end_parts = parts[1].strip().split(":")
                    start = time(int(start_parts[0]), int(start_parts[1]) if len(start_parts) > 1 else 0)
                    end = time(int(end_parts[0]), int(end_parts[1]) if len(end_parts) > 1 else 0)
                    return (start, end)
                except (ValueError, IndexError):
                    pass

    if isinstance(light_hours, dict):
        # Формат {"start": "06:00", "end": "22:00"}
        start_str = light_hours.get("start")
        end_str = light_hours.get("end")
        if start_str and end_str:
            try:
                start_parts = start_str.split(":")
                end_parts = end_str.split(":")
                start = time(int(start_parts[0]), int(start_parts[1]) if len(start_parts) > 1 else 0)
                end = time(int(end_parts[0]), int(end_parts[1]) if len(end_parts) > 1 else 0)
                return (start, end)
            except (ValueError, IndexError):
                pass

    return None


def _parse_time_str(value: Any) -> Optional[time]:
    if value is None:
        return None
    if isinstance(value, time):
        return value
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    return None


def get_ph_target(
    targets: Dict[str, Any],
    zone_id: Optional[int] = None,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    value = targets.get("ph")
    if isinstance(value, dict):
        target = _coerce_float(value.get("target"))
        min_val = _coerce_float(value.get("min"))
        max_val = _coerce_float(value.get("max"))
        if target is None and (min_val is not None or max_val is not None):
            _warn_schema_mismatch("ph", zone_id, "ph target missing 'target'")
        return target, min_val, max_val
    if value is None:
        return None, None, None
    _warn_schema_mismatch("ph", zone_id, "ph target uses legacy format")
    return _coerce_float(value), None, None


def get_ec_target(
    targets: Dict[str, Any],
    zone_id: Optional[int] = None,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    value = targets.get("ec")
    if isinstance(value, dict):
        target = _coerce_float(value.get("target"))
        min_val = _coerce_float(value.get("min"))
        max_val = _coerce_float(value.get("max"))
        if target is None and (min_val is not None or max_val is not None):
            _warn_schema_mismatch("ec", zone_id, "ec target missing 'target'")
        return target, min_val, max_val
    if value is None:
        return None, None, None
    _warn_schema_mismatch("ec", zone_id, "ec target uses legacy format")
    return _coerce_float(value), None, None


def get_irrigation_params(
    targets: Dict[str, Any],
    zone_id: Optional[int] = None,
) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    irrigation = targets.get("irrigation")
    if isinstance(irrigation, dict):
        interval = _coerce_int(irrigation.get("interval_sec"))
        duration = _coerce_int(irrigation.get("duration_sec"))
        mode = irrigation.get("mode")
        if interval is None:
            legacy_interval = _coerce_int(targets.get("irrigation_interval_sec"))
            legacy_duration = _coerce_int(targets.get("irrigation_duration_sec"))
            if legacy_interval is not None or legacy_duration is not None:
                _warn_schema_mismatch(
                    "irrigation",
                    zone_id,
                    "irrigation target missing interval_sec; using legacy keys",
                )
                interval = legacy_interval
                duration = duration or legacy_duration
        return interval, duration, mode

    legacy_interval = _coerce_int(targets.get("irrigation_interval_sec"))
    legacy_duration = _coerce_int(targets.get("irrigation_duration_sec"))
    if legacy_interval is not None or legacy_duration is not None:
        _warn_schema_mismatch("irrigation", zone_id, "irrigation target uses legacy format")
    return legacy_interval, legacy_duration, None


def get_lighting_window(
    targets: Dict[str, Any],
    zone_id: Optional[int] = None,
) -> Optional[tuple[time, time]]:
    lighting = targets.get("lighting")
    if isinstance(lighting, dict):
        photoperiod_hours = _coerce_float(lighting.get("photoperiod_hours"))
        start_time = _parse_time_str(lighting.get("start_time"))
        if photoperiod_hours is not None and start_time is not None:
            end_time = (
                datetime.combine(date.today(), start_time) + timedelta(hours=photoperiod_hours)
            ).time()
            return start_time, end_time
        if photoperiod_hours is not None or lighting.get("start_time") is not None:
            _warn_schema_mismatch(
                "light",
                zone_id,
                "lighting target missing photoperiod_hours/start_time",
            )

    legacy_value = targets.get("light_hours") or targets.get("photoperiod")
    if legacy_value is not None:
        _warn_schema_mismatch("light", zone_id, "lighting target uses legacy format")
    return parse_photoperiod(legacy_value)


def get_light_intensity(
    targets: Dict[str, Any],
) -> Optional[int]:
    lighting = targets.get("lighting")
    if isinstance(lighting, dict):
        intensity = lighting.get("intensity") or lighting.get("ppfd")
        value = _coerce_int(intensity)
        if value is not None:
            return value

    intensity = targets.get("light_intensity") or targets.get("ppfd")
    return _coerce_int(intensity)


def get_climate_request(
    targets: Dict[str, Any],
    zone_id: Optional[int] = None,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    climate_request = targets.get("climate_request")
    if isinstance(climate_request, dict):
        temp = _coerce_float(climate_request.get("temp_air_target"))
        humidity = _coerce_float(climate_request.get("humidity_target"))
        co2 = _coerce_float(climate_request.get("co2_target"))
        if temp is None and humidity is None and co2 is None:
            legacy_temp = _coerce_float(targets.get("temp_air"))
            legacy_humidity = _coerce_float(targets.get("humidity_air"))
            legacy_co2 = _coerce_float(targets.get("co2_target"))
            if legacy_temp is not None or legacy_humidity is not None or legacy_co2 is not None:
                _warn_schema_mismatch("climate", zone_id, "climate target uses legacy format")
            return legacy_temp, legacy_humidity, legacy_co2
        return temp, humidity, co2

    legacy_temp = _coerce_float(targets.get("temp_air"))
    legacy_humidity = _coerce_float(targets.get("humidity_air"))
    legacy_co2 = _coerce_float(targets.get("co2_target"))
    if legacy_temp is not None or legacy_humidity is not None or legacy_co2 is not None:
        _warn_schema_mismatch("climate", zone_id, "climate target uses legacy format")
    return legacy_temp, legacy_humidity, legacy_co2
