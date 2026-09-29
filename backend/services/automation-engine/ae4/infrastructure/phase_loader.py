"""Загрузка целей текущей фазы посадки для AE4."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ae4.domain.planting import PhaseTargets, PlantingState
from common.db import fetch


class PhaseLoadError(RuntimeError):
    def __init__(self, *, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def _as_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc)
        return value.replace(tzinfo=timezone.utc)
    return None


def _opt_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _opt_int(value: Any) -> int | None:
    number = _opt_float(value)
    if number is None:
        return None
    return int(number)


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extensions(raw: Any) -> Mapping[str, Any]:
    if isinstance(raw, Mapping):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, Mapping) else {}
    return {}


async def load_planting_state(*, zone_id: int) -> PlantingState:
    rows = await fetch(
        """
        SELECT
            zones.id AS zone_id,
            gc.id AS grow_cycle_id,
            gcp.id AS phase_id,
            gcp.started_at AS phase_started_at,
            gcp.irrigation_interval_sec,
            gcp.irrigation_duration_sec,
            gcp.soil_moisture_min,
            gcp.soil_moisture_max,
            gcp.vpd_min,
            gcp.vpd_max,
            gcp.light_integral_per_shot,
            gcp.ec_target,
            gcp.ec_min,
            gcp.ec_max,
            gcp.ph_target,
            gcp.ph_min,
            gcp.ph_max,
            gcp.temp_air_target,
            gcp.humidity_target,
            gcp.solution_temp_min,
            gcp.solution_temp_max,
            gcp.co2_target,
            gcp.mist_interval_sec,
            gcp.mist_duration_sec,
            gcp.mist_mode,
            gcp.lighting_start_time,
            gcp.lighting_photoperiod_hours,
            gcp.extensions
        FROM zones
        JOIN grow_cycles AS gc
            ON gc.zone_id = zones.id
           AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
        JOIN grow_cycle_phases AS gcp
            ON gcp.id = gc.current_phase_id
        WHERE zones.id = $1
        ORDER BY
            CASE gc.status
                WHEN 'RUNNING' THEN 1
                WHEN 'PAUSED' THEN 2
                WHEN 'PLANNED' THEN 3
                ELSE 4
            END,
            gc.id DESC
        LIMIT 1
        """,
        zone_id,
    )
    if not rows:
        raise PhaseLoadError(
            reason_code="planting_missing",
            message="Нет активной посадки или фазы у зоны",
        )
    row = rows[0]
    started = _as_utc(row.get("phase_started_at"))
    if started is None:
        raise PhaseLoadError(
            reason_code="phase_started_at_missing",
            message="У фазы нет started_at",
        )
    ext = _extensions(row.get("extensions"))
    on_time = _opt_str(ext.get("on_time"))
    off_time = _opt_str(ext.get("off_time"))
    light_unit = _opt_str(ext.get("light_integral_unit"))
    soil_unit = _opt_str(ext.get("soil_moisture_unit"))
    ec_unit = _opt_str(ext.get("ec_unit"))

    lighting_start = row.get("lighting_start_time")
    if hasattr(lighting_start, "strftime"):
        lighting_start = lighting_start.strftime("%H:%M:%S")
    else:
        lighting_start = _opt_str(lighting_start)

    phase = PhaseTargets(
        phase_id=int(row["phase_id"]),
        started_at=started,
        interval_sec=_opt_int(row.get("irrigation_interval_sec")),
        duration_sec=_opt_int(row.get("irrigation_duration_sec")),
        soil_moisture_min=_opt_float(row.get("soil_moisture_min")),
        soil_moisture_max=_opt_float(row.get("soil_moisture_max")),
        soil_moisture_unit=soil_unit,
        vpd_min=_opt_float(row.get("vpd_min")),
        vpd_max=_opt_float(row.get("vpd_max")),
        light_integral_per_shot=_opt_float(row.get("light_integral_per_shot")),
        light_integral_unit=light_unit,
        ec_target=_opt_float(row.get("ec_target")),
        ec_min=_opt_float(row.get("ec_min")),
        ec_max=_opt_float(row.get("ec_max")),
        ec_unit=ec_unit,
        ph_target=_opt_float(row.get("ph_target")),
        ph_min=_opt_float(row.get("ph_min")),
        ph_max=_opt_float(row.get("ph_max")),
        temp_air_target=_opt_float(row.get("temp_air_target")),
        humidity_target=_opt_float(row.get("humidity_target")),
        solution_temp_min=_opt_float(row.get("solution_temp_min")),
        solution_temp_max=_opt_float(row.get("solution_temp_max")),
        co2_target=_opt_float(row.get("co2_target")),
        mist_interval_sec=_opt_int(row.get("mist_interval_sec")),
        mist_duration_sec=_opt_int(row.get("mist_duration_sec")),
        mist_mode=_opt_str(row.get("mist_mode")),
        on_time=on_time,
        off_time=off_time,
        lighting_start_time=lighting_start,
        lighting_photoperiod_hours=_opt_float(row.get("lighting_photoperiod_hours")),
    )
    return PlantingState(
        zone_id=int(row["zone_id"]),
        grow_cycle_id=int(row["grow_cycle_id"]),
        phase=phase,
    )


__all__ = ["PhaseLoadError", "load_planting_state"]
