"""Utilities for EC component batch correction flow."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from common.db import fetch
from config.settings import get_settings

logger = logging.getLogger(__name__)


def resolve_nutrition_mode(nutrition: Dict[str, Any]) -> str:
    mode = str(nutrition.get("mode", "")).strip().lower()
    if mode in {"ratio_ec_pid", "delta_ec_by_k", "dose_ml_l_only"}:
        return mode
    return ""


def resolve_solution_volume_l(nutrition: Dict[str, Any]) -> Optional[float]:
    raw = nutrition.get("solution_volume_l")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


def extract_nutrition_control(targets: Dict[str, Any]) -> Dict[str, Any]:
    nutrition = targets.get("nutrition")
    if not isinstance(nutrition, dict):
        return {}

    result: Dict[str, Any] = {}
    mode_raw = nutrition.get("mode")
    if isinstance(mode_raw, str):
        mode = mode_raw.strip().lower()
        if mode in {"ratio_ec_pid", "delta_ec_by_k", "dose_ml_l_only"}:
            result["mode"] = mode

    solution_volume_raw = nutrition.get("solution_volume_l")
    if solution_volume_raw is not None:
        try:
            solution_volume = float(solution_volume_raw)
            if solution_volume > 0:
                result["solution_volume_l"] = solution_volume
        except (TypeError, ValueError):
            pass

    delay_raw = nutrition.get("dose_delay_sec")
    if delay_raw is not None:
        try:
            delay = float(delay_raw)
            if delay >= 0:
                result["dose_delay_sec"] = delay
        except (TypeError, ValueError):
            pass

    tolerance_raw = nutrition.get("ec_stop_tolerance")
    if tolerance_raw is not None:
        try:
            tolerance = float(tolerance_raw)
            if tolerance >= 0:
                result["ec_stop_tolerance"] = tolerance
        except (TypeError, ValueError):
            pass

    return result


def resolve_batch_dose_control(command: Dict[str, Any]) -> tuple[float, float]:
    settings = get_settings()
    control = command.get("nutrition_control")
    if not isinstance(control, dict):
        control = {}

    delay_raw = control.get("dose_delay_sec", settings.EC_COMPONENT_DOSE_DELAY_SEC)
    tolerance_raw = control.get("ec_stop_tolerance", settings.EC_COMPONENT_RECHECK_TOLERANCE)

    try:
        dose_delay_sec = max(0.0, float(delay_raw))
    except (TypeError, ValueError):
        dose_delay_sec = float(settings.EC_COMPONENT_DOSE_DELAY_SEC)

    try:
        ec_stop_tolerance = max(0.0, float(tolerance_raw))
    except (TypeError, ValueError):
        ec_stop_tolerance = float(settings.EC_COMPONENT_RECHECK_TOLERANCE)

    return dose_delay_sec, ec_stop_tolerance


async def get_latest_ec_value(zone_id: int, *, fetch_fn=fetch) -> Optional[float]:
    try:
        rows = await fetch_fn(
            """
            SELECT tl.last_value
            FROM telemetry_last tl
            JOIN sensors s ON s.id = tl.sensor_id
            WHERE s.zone_id = $1
              AND s.type = 'EC'
            ORDER BY tl.updated_at DESC
            LIMIT 1
            """,
            zone_id,
        )
    except Exception as exc:
        logger.warning(
            "Zone %s: failed to fetch EC after component dose: %s",
            zone_id,
            exc,
            extra={"zone_id": zone_id},
        )
        return None

    if not rows:
        return None
    value = rows[0].get("last_value")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "extract_nutrition_control",
    "get_latest_ec_value",
    "resolve_batch_dose_control",
    "resolve_nutrition_mode",
    "resolve_solution_volume_l",
]
