"""Capabilities fallback resolver based on active automation profile subsystems."""

from __future__ import annotations

from typing import Any, Dict, Optional


CAPABILITY_KEYS = (
    "ph_control",
    "ec_control",
    "climate_control",
    "light_control",
    "irrigation_control",
    "recirculation",
    "flow_sensor",
)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_optional_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


def _has_any_enabled_capability(capabilities: Dict[str, Any]) -> bool:
    for key in CAPABILITY_KEYS:
        if bool(capabilities.get(key)):
            return True
    return False


def _subsystem_enabled(subsystems: Dict[str, Any], subsystem: str) -> bool:
    section = _as_dict(subsystems.get(subsystem))
    enabled = _to_optional_bool(section.get("enabled"))
    return bool(enabled)


def _derive_capabilities_from_subsystems(subsystems: Dict[str, Any]) -> Dict[str, bool]:
    irrigation_enabled = _subsystem_enabled(subsystems, "irrigation")
    irrigation_execution = _as_dict(_as_dict(subsystems.get("irrigation")).get("execution"))
    diagnostics_execution = _as_dict(_as_dict(subsystems.get("diagnostics")).get("execution"))

    tanks_count = 0
    try:
        tanks_count = int(irrigation_execution.get("tanks_count") or 0)
    except (TypeError, ValueError):
        tanks_count = 0

    topology = str(
        diagnostics_execution.get("topology")
        or irrigation_execution.get("topology")
        or ""
    ).strip().lower()
    recirculation_flag = _to_optional_bool(irrigation_execution.get("recirculation"))
    has_recirculation_topology = topology.startswith("two_tank") or topology.startswith("three_tank")

    return {
        "ph_control": _subsystem_enabled(subsystems, "ph"),
        "ec_control": _subsystem_enabled(subsystems, "ec"),
        "climate_control": _subsystem_enabled(subsystems, "climate"),
        "light_control": _subsystem_enabled(subsystems, "lighting"),
        "irrigation_control": irrigation_enabled,
        "recirculation": irrigation_enabled
        and bool(recirculation_flag or tanks_count >= 2 or has_recirculation_topology),
        "flow_sensor": bool(_to_optional_bool(irrigation_execution.get("flow_sensor"))),
    }


def resolve_zone_capabilities_with_profile_fallback(
    *,
    raw_capabilities: Any,
    profile_subsystems: Any,
    default_capabilities: Dict[str, bool],
) -> Dict[str, bool]:
    """Return capabilities with profile fallback for stale all-false zone payloads."""
    resolved = dict(default_capabilities)

    raw_cap_dict = _as_dict(raw_capabilities)
    for key in CAPABILITY_KEYS:
        value = _to_optional_bool(raw_cap_dict.get(key))
        if value is not None:
            resolved[key] = value

    if _has_any_enabled_capability(resolved):
        return resolved

    subsystems = _as_dict(profile_subsystems)
    if not subsystems:
        return resolved

    derived = _derive_capabilities_from_subsystems(subsystems)
    if not _has_any_enabled_capability(derived):
        return resolved

    for key in CAPABILITY_KEYS:
        resolved[key] = bool(derived.get(key, resolved.get(key, False)))
    return resolved


__all__ = ["resolve_zone_capabilities_with_profile_fallback"]
