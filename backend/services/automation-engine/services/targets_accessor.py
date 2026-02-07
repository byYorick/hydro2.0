"""
Helpers for reading targets with structured formats from effective targets.
Legacy keys trigger warnings but are ignored.
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
    return None, None, None


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
    return None, None, None


def get_nutrition_components(
    targets: Dict[str, Any],
    zone_id: Optional[int] = None,
) -> Dict[str, Dict[str, Optional[float]]]:
    nutrition = targets.get("nutrition")
    if not isinstance(nutrition, dict):
        return {}

    components = nutrition.get("components")
    if not isinstance(components, dict):
        _warn_schema_mismatch("ec", zone_id, "nutrition target missing components")
        return {}

    result: Dict[str, Dict[str, Optional[float]]] = {}
    for key in ("npk", "calcium", "micro"):
        component = components.get(key)
        if not isinstance(component, dict):
            continue
        result[key] = {
            "ratio_pct": _coerce_float(component.get("ratio_pct")),
            "dose_ml_per_l": _coerce_float(component.get("dose_ml_per_l")),
        }

    return result


def get_irrigation_params(
    targets: Dict[str, Any],
    zone_id: Optional[int] = None,
) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    irrigation = targets.get("irrigation")
    if isinstance(irrigation, dict):
        interval = _coerce_int(irrigation.get("interval_sec"))
        duration = _coerce_int(irrigation.get("duration_sec"))
        mode = irrigation.get("mode")
        if interval is None and (duration is not None or mode is not None):
            _warn_schema_mismatch(
                "irrigation",
                zone_id,
                "irrigation target missing interval_sec",
            )
        return interval, duration, mode
    if targets.get("irrigation_interval_sec") is not None or targets.get("irrigation_duration_sec") is not None:
        _warn_schema_mismatch("irrigation", zone_id, "irrigation target uses legacy format")
    return None, None, None


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
    if targets.get("light_hours") is not None or targets.get("photoperiod") is not None:
        _warn_schema_mismatch("light", zone_id, "lighting target uses legacy format")
    return None


def get_light_intensity(
    targets: Dict[str, Any],
) -> Optional[int]:
    lighting = targets.get("lighting")
    if isinstance(lighting, dict):
        intensity = lighting.get("intensity") or lighting.get("ppfd")
        value = _coerce_int(intensity)
        if value is not None:
            return value
    return None


def get_climate_request(
    targets: Dict[str, Any],
    zone_id: Optional[int] = None,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    climate_request = targets.get("climate_request")
    if isinstance(climate_request, dict):
        temp = _coerce_float(climate_request.get("temp_air_target"))
        humidity = _coerce_float(climate_request.get("humidity_target"))
        co2 = _coerce_float(climate_request.get("co2_target"))
        return temp, humidity, co2
    if targets.get("temp_air") is not None or targets.get("humidity_air") is not None or targets.get("co2_target") is not None:
        _warn_schema_mismatch("climate", zone_id, "climate target uses legacy format")
    return None, None, None
