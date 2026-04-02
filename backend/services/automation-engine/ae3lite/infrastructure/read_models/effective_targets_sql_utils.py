"""Utilities for effective-target assembly used by AE3-Lite snapshot read-model."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


def to_positive_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        normalized = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def merge_recursive(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_recursive(merged[key], value)
        else:
            merged[key] = value
    return merged


def clean_null_values(payload: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            nested = clean_null_values(value)
            if nested:
                cleaned[key] = nested
            continue
        if value is not None:
            cleaned[key] = value
    return cleaned


def extract_subsystem_enabled(subsystems: Dict[str, Any], subsystem: str) -> Optional[bool]:
    section = subsystems.get(subsystem)
    if not isinstance(section, dict):
        return None
    return to_bool(section.get("enabled"))


def extract_subsystem_targets(subsystems: Dict[str, Any], subsystem: str) -> Optional[Dict[str, Any]]:
    section = subsystems.get(subsystem)
    if not isinstance(section, dict):
        return None
    execution = section.get("execution")
    if not isinstance(execution, dict):
        return None
    return dict(execution)


def merge_task_execution(task_config: Dict[str, Any], execution_patch: Dict[str, Any]) -> Dict[str, Any]:
    config = dict(task_config)
    existing_execution = config.get("execution")
    existing_execution = existing_execution if isinstance(existing_execution, dict) else {}
    config["execution"] = merge_recursive(existing_execution, execution_patch)
    return config


def resolve_interval_seconds(payload: Dict[str, Any]) -> Optional[int]:
    interval_sec = to_positive_int(payload.get("interval_sec") or payload.get("every_sec"))
    if interval_sec is not None:
        return interval_sec
    interval_minutes = to_positive_int(payload.get("interval_minutes"))
    if interval_minutes is not None:
        return interval_minutes * 60
    return None


def resolve_duration_seconds(payload: Dict[str, Any]) -> Optional[int]:
    duration_sec = to_positive_int(payload.get("duration_sec"))
    if duration_sec is not None:
        return duration_sec
    return to_positive_int(payload.get("duration_seconds"))


def normalize_time_string(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


def resolve_schedule_start_time(raw_schedule: Any) -> Optional[str]:
    if not isinstance(raw_schedule, list) or not raw_schedule:
        return None
    first = raw_schedule[0]
    if not isinstance(first, dict):
        return None
    return normalize_time_string(first.get("start"))


def _merge_irrigation(targets: Dict[str, Any], subsystems: Dict[str, Any]) -> Dict[str, Any]:
    enabled = extract_subsystem_enabled(subsystems, "irrigation")
    sub_targets = extract_subsystem_targets(subsystems, "irrigation")
    if enabled is None and not isinstance(sub_targets, dict):
        return targets
    irrigation = targets.get("irrigation") if isinstance(targets.get("irrigation"), dict) else {}
    if isinstance(sub_targets, dict):
        interval_sec = resolve_interval_seconds(sub_targets)
        duration_sec = resolve_duration_seconds(sub_targets)
        if interval_sec is not None:
            irrigation["interval_sec"] = interval_sec
        if duration_sec is not None:
            irrigation["duration_sec"] = duration_sec
        system_type = sub_targets.get("system_type")
        if isinstance(system_type, str) and system_type.strip():
            irrigation["system_type"] = system_type.strip()
        irrigation = merge_task_execution(irrigation, sub_targets)
    if enabled is False:
        irrigation = merge_task_execution(irrigation, {"force_skip": True})
    elif enabled is True:
        irrigation = merge_task_execution(irrigation, {"force_skip": False})
    if irrigation:
        targets["irrigation"] = irrigation
    return targets


def _merge_lighting(targets: Dict[str, Any], subsystems: Dict[str, Any]) -> Dict[str, Any]:
    enabled = extract_subsystem_enabled(subsystems, "lighting")
    sub_targets = extract_subsystem_targets(subsystems, "lighting")
    if enabled is None and not isinstance(sub_targets, dict):
        return targets
    lighting = targets.get("lighting") if isinstance(targets.get("lighting"), dict) else {}
    if isinstance(sub_targets, dict):
        photoperiod = to_float(sub_targets.get("photoperiod_hours"))
        if photoperiod is None and isinstance(sub_targets.get("photoperiod"), dict):
            photoperiod = to_float(sub_targets["photoperiod"].get("hours_on"))
        if photoperiod is not None:
            lighting["photoperiod_hours"] = photoperiod
        start_time = resolve_schedule_start_time(sub_targets.get("schedule"))
        if start_time is None:
            start_time = normalize_time_string(sub_targets.get("start_time"))
        if start_time is not None:
            lighting["start_time"] = start_time
        interval_sec = resolve_interval_seconds(sub_targets)
        if interval_sec is not None:
            lighting["interval_sec"] = interval_sec
        lighting = merge_task_execution(lighting, sub_targets)
    if enabled is False:
        lighting = merge_task_execution(lighting, {"force_skip": True})
    elif enabled is True:
        lighting = merge_task_execution(lighting, {"force_skip": False})
    if lighting:
        targets["lighting"] = lighting
    return targets


def _merge_climate(targets: Dict[str, Any], subsystems: Dict[str, Any]) -> Dict[str, Any]:
    enabled = extract_subsystem_enabled(subsystems, "climate")
    sub_targets = extract_subsystem_targets(subsystems, "climate")
    if enabled is None and not isinstance(sub_targets, dict):
        return targets
    if isinstance(sub_targets, dict):
        climate_request = targets.get("climate_request") if isinstance(targets.get("climate_request"), dict) else {}
        day_temp = to_float(((sub_targets.get("temperature") or {}) if isinstance(sub_targets.get("temperature"), dict) else {}).get("day"))
        day_humidity = to_float(((sub_targets.get("humidity") or {}) if isinstance(sub_targets.get("humidity"), dict) else {}).get("day"))
        if day_temp is not None:
            climate_request["temp_air_target"] = day_temp
        if day_humidity is not None:
            climate_request["humidity_target"] = day_humidity
        if climate_request:
            targets["climate_request"] = climate_request
    ventilation = targets.get("ventilation") if isinstance(targets.get("ventilation"), dict) else {}
    if isinstance(sub_targets, dict):
        interval_sec = resolve_interval_seconds(sub_targets)
        if interval_sec is not None:
            ventilation["interval_sec"] = interval_sec
        ventilation = merge_task_execution(ventilation, sub_targets)
    if enabled is False:
        ventilation = merge_task_execution(ventilation, {"force_skip": True})
    elif enabled is True:
        ventilation = merge_task_execution(ventilation, {"force_skip": False})
    if ventilation:
        targets["ventilation"] = ventilation
    return targets


def merge_runtime_profile(targets: Dict[str, Any], runtime_profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(runtime_profile, dict):
        return targets
    subsystems = runtime_profile.get("subsystems")
    if not isinstance(subsystems, dict):
        return targets

    merged = dict(targets)
    merged = _merge_irrigation(merged, subsystems)
    merged = _merge_lighting(merged, subsystems)
    merged = _merge_climate(merged, subsystems)

    extensions = merged.get("extensions") if isinstance(merged.get("extensions"), dict) else {}
    existing_subsystems = extensions.get("subsystems") if isinstance(extensions.get("subsystems"), dict) else {}
    extensions["subsystems"] = merge_recursive(existing_subsystems, subsystems)
    extensions["automation_logic"] = {
        "source": "zone_automation_logic_profile",
        "mode": runtime_profile.get("mode"),
        "updated_at": to_iso(runtime_profile.get("updated_at")),
    }
    merged["extensions"] = extensions
    return merged


def build_base_targets(phase: Dict[str, Any]) -> Dict[str, Any]:
    targets: Dict[str, Any] = {}
    if phase.get("ph_target") is not None:
        targets["ph"] = {
            "target": float(phase["ph_target"]),
            "min": to_float(phase.get("ph_min")),
            "max": to_float(phase.get("ph_max")),
        }
    if phase.get("ec_target") is not None:
        targets["ec"] = {
            "target": float(phase["ec_target"]),
            "min": to_float(phase.get("ec_min")),
            "max": to_float(phase.get("ec_max")),
        }
    if phase.get("irrigation_mode") is not None:
        targets["irrigation"] = {
            "mode": phase.get("irrigation_mode"),
            "interval_sec": phase.get("irrigation_interval_sec"),
            "duration_sec": phase.get("irrigation_duration_sec"),
        }
    if phase.get("lighting_photoperiod_hours") is not None:
        targets["lighting"] = {
            "photoperiod_hours": to_float(phase.get("lighting_photoperiod_hours")),
            "start_time": normalize_time_string(phase.get("lighting_start_time")),
        }
    climate_request: Dict[str, Any] = {}
    if phase.get("temp_air_target") is not None:
        climate_request["temp_air_target"] = float(phase["temp_air_target"])
    if phase.get("humidity_target") is not None:
        climate_request["humidity_target"] = float(phase["humidity_target"])
    if phase.get("co2_target") is not None:
        climate_request["co2_target"] = phase["co2_target"]
    if climate_request:
        targets["climate_request"] = climate_request
    if phase.get("mist_interval_sec") is not None or phase.get("mist_duration_sec") is not None:
        targets["mist"] = {
            "interval_sec": phase.get("mist_interval_sec"),
            "duration_sec": phase.get("mist_duration_sec"),
            "mode": phase.get("mist_mode"),
        }
    if isinstance(phase.get("extensions"), dict):
        targets["extensions"] = dict(phase["extensions"])
    return targets


__all__ = [
    "build_base_targets",
    "clean_null_values",
    "merge_recursive",
    "merge_runtime_profile",
]
