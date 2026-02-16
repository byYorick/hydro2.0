"""Command mapping helpers for scheduler task execution."""

from __future__ import annotations

from typing import Any, Dict, Optional


def terminal_status_to_error_code(status: str, *, error_codes: Dict[str, str]) -> str:
    normalized = str(status or "").strip().upper()
    if normalized == "DONE":
        return ""
    return error_codes.get(normalized, error_codes.get("__default__", "command_effect_not_confirmed"))


def extract_duration_sec(payload: Dict[str, Any], mapping: Any) -> Optional[float]:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    targets = payload.get("targets") if isinstance(payload.get("targets"), dict) else {}

    duration_raw = config.get("duration_sec")
    if duration_raw is None:
        execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
        duration_raw = execution.get("duration_sec")

    if duration_raw is None:
        for section, field in mapping.duration_target_paths:
            section_payload = targets.get(section)
            if isinstance(section_payload, dict) and field in section_payload:
                duration_raw = section_payload.get(field)
                break

    if duration_raw is None:
        duration_raw = mapping.default_duration_sec

    try:
        duration_sec = float(duration_raw) if duration_raw is not None else None
    except (TypeError, ValueError):
        duration_sec = mapping.default_duration_sec

    if duration_sec is None or duration_sec <= 0:
        return None
    return duration_sec


def resolve_command_name(payload: Dict[str, Any], mapping: Any) -> Optional[str]:
    if mapping.state_key and (mapping.cmd_true or mapping.cmd_false):
        state_value = payload.get(mapping.state_key, mapping.default_state)
        state_bool = bool(state_value) if state_value is not None else bool(mapping.default_state)
        if state_bool and mapping.cmd_true:
            return mapping.cmd_true
        if not state_bool and mapping.cmd_false:
            return mapping.cmd_false
    return mapping.cmd


def resolve_command_params(payload: Dict[str, Any], mapping: Any) -> Dict[str, Any]:
    params = dict(mapping.default_params)
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    if isinstance(execution.get("params"), dict):
        params.update(execution.get("params") or {})

    duration_sec = extract_duration_sec(payload, mapping)
    if duration_sec is not None and "duration_ms" not in params:
        params["duration_ms"] = max(100, int(duration_sec * 1000))

    if mapping.state_key and "state" not in params:
        state_value = payload.get(mapping.state_key, mapping.default_state)
        if state_value is not None:
            params["state"] = bool(state_value)

    return params


__all__ = [
    "extract_duration_sec",
    "resolve_command_name",
    "resolve_command_params",
    "terminal_status_to_error_code",
]
