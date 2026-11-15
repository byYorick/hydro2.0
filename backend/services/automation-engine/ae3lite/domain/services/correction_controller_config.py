"""Correction domain policy: controller config."""

from __future__ import annotations

from typing import Any, Mapping

from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services.correction_primitives import _non_negative_float


def _resolve_pid_controller_cfg(
    *,
    controller_cfg: Mapping[str, Any],
    pid_configs: Mapping[str, Any],
    pid_type: str,
    gap: float,
) -> tuple[Mapping[str, Any], str, Mapping[str, Any]]:
    entry = pid_configs.get(pid_type)
    pid_cfg = entry.get("config") if isinstance(entry, Mapping) else None
    if not isinstance(pid_cfg, Mapping):
        return controller_cfg, "", {}

    zone_coeffs = pid_cfg.get("zone_coeffs")
    if not isinstance(zone_coeffs, Mapping):
        return _merge_pid_deadband(controller_cfg=controller_cfg, pid_cfg=pid_cfg), "", {}

    close_zone = _non_negative_float(pid_cfg.get("close_zone"), 0.0)
    far_zone = _non_negative_float(pid_cfg.get("far_zone"), 0.0)
    if far_zone <= close_zone:
        raise PlannerConfigurationError(
            f"pid_configs.{pid_type}.far_zone ({far_zone}) должно быть > close_zone ({close_zone})"
        )
    zone_name = "close" if gap <= close_zone or far_zone <= close_zone else "far"
    coeffs = zone_coeffs.get(zone_name)
    if not isinstance(coeffs, Mapping):
        return _merge_pid_deadband(controller_cfg=controller_cfg, pid_cfg=pid_cfg), "", {}

    merged = dict(_merge_pid_deadband(controller_cfg=controller_cfg, pid_cfg=pid_cfg))
    selected_coeffs: dict[str, float] = {}
    for key in ("kp", "ki", "kd"):
        value = coeffs.get(key)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        merged[key] = numeric
        selected_coeffs[key] = numeric
    return merged, zone_name, selected_coeffs


def _merge_pid_deadband(*, controller_cfg: Mapping[str, Any], pid_cfg: Mapping[str, Any]) -> Mapping[str, Any]:
    merged = dict(controller_cfg)
    dead_zone = pid_cfg.get("dead_zone")
    try:
        deadband = float(dead_zone)
    except (TypeError, ValueError):
        return merged
    if deadband >= 0:
        merged["deadband"] = deadband
    return merged
