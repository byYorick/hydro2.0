"""runtime plan targets: one cohesive policy."""

from __future__ import annotations

from typing import Any, Mapping

from ae3lite.config.runtime_plan_values_policy import _optional_float, _to_mapping
from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError
from ae3lite.domain.services.greenhouse_clock import (
    InvalidGreenhouseTimezone,
    canonical_timezone_name,
)


def _compute_prepare_ec_share(
    solution_fill_cfg: Mapping[str, Any],
    base_cfg: Mapping[str, Any],
) -> float:
    """Deprecated: historically NPK share for prepare. Prefer calcium share / T_*."""
    ratios = _to_mapping(solution_fill_cfg.get("ec_component_ratios")) or _to_mapping(
        base_cfg.get("ec_component_ratios")
    )
    return _compute_component_share(ratios, component="calcium")


def _compute_component_share(ratios: Mapping[str, Any] | None, *, component: str) -> float:
    """Return component / sum(positive ratios); 1.0 if ratios empty."""
    if not isinstance(ratios, Mapping) or not ratios:
        return 1.0
    want = str(component).strip().lower()
    selected = 0.0
    total = 0.0
    for k, v in ratios.items():
        try:
            val = float(v)
        except (TypeError, ValueError):
            continue
        if val <= 0:
            continue
        total += val
        if str(k).strip().lower() == want:
            selected = val
    if total <= 0 or selected <= 0:
        return 1.0
    return selected / total


def _build_day_night_config(snapshot: Any) -> dict[str, Any]:
    """Собирает day/night конфиг из phase_targets для dynamic resolution в handler'ах.

    Возвращаемая структура:
        {
            "enabled": bool,
            "lighting": {"day_start_time": str | None, "day_hours": float | None},
            "ph":  {"day": float | None, "night": float | None,
                     "day_min": float | None, "day_max": float | None,
                     "night_min": float | None, "night_max": float | None},
            "ec":  {... то же самое ...},
        }
    Поля lighting fallback'ятся на фазу (`lighting.start_time` / `lighting.photoperiod_hours`),
    если `day_night.lighting.*` пусто.
    """
    phase_targets = _to_mapping(getattr(snapshot, "phase_targets", None))

    enabled = bool(phase_targets.get("day_night_enabled") or False)
    extensions = _to_mapping(phase_targets.get("extensions"))
    day_night = _to_mapping(extensions.get("day_night"))
    lighting_ext = _to_mapping(day_night.get("lighting"))

    # Fallback lighting на фазовые поля
    day_start_time = lighting_ext.get("day_start_time")
    if not day_start_time:
        lighting_base = _to_mapping(phase_targets.get("lighting"))
        day_start_time = lighting_base.get("start_time")
    day_hours = lighting_ext.get("day_hours")
    if day_hours is None:
        lighting_base = _to_mapping(phase_targets.get("lighting"))
        day_hours = lighting_base.get("photoperiod_hours")

    def _section(key: str) -> dict[str, Any]:
        section = _to_mapping(day_night.get(key))
        return {
            "day": _optional_float(section.get("day")),
            "night": _optional_float(section.get("night")),
            "day_min": _optional_float(section.get("day_min")),
            "day_max": _optional_float(section.get("day_max")),
            "night_min": _optional_float(section.get("night_min")),
            "night_max": _optional_float(section.get("night_max")),
        }

    timezone = _require_greenhouse_timezone(snapshot)

    return {
        "enabled": enabled,
        "lighting": {
            "day_start_time": str(day_start_time).strip()
            if isinstance(day_start_time, str) and day_start_time.strip()
            else None,
            "day_hours": _optional_float(day_hours),
            "timezone": timezone,
        },
        "ph": _section("ph"),
        "ec": _section("ec"),
    }


def _resolve_phase_target(*, snapshot: Any, zone_id: int, key: str) -> float:
    upper = 20.0 if key == "ec" else 14.0
    section = _to_mapping(_to_mapping(getattr(snapshot, "phase_targets", None)).get(key))
    candidate = section.get("target")
    if candidate is None:
        raise PlannerConfigurationError(
            f"У зоны {zone_id} в текущей recipe phase отсутствует target_{key}; "
            "automation требует recipe-phase pH/EC targets и запрещает defaults или runtime overrides",
            code=ErrorCodes.ZONE_RECIPE_PHASE_TARGETS_MISSING_CRITICAL,
        )
    try:
        return max(0.0, min(upper, float(candidate)))
    except (TypeError, ValueError):
        raise PlannerConfigurationError(
            f"У зоны {zone_id} в текущей recipe phase target_{key} не является числом: {candidate!r}",
            code=ErrorCodes.ZONE_RECIPE_PHASE_TARGETS_MISSING_CRITICAL,
        )


def _resolve_phase_target_bound(*, snapshot: Any, key: str, bound: str, fallback: float) -> float:
    upper = 20.0 if key == "ec" else 14.0
    section = _to_mapping(_to_mapping(getattr(snapshot, "phase_targets", None)).get(key))
    candidate = section.get(bound)
    if candidate is None:
        return float(fallback)
    try:
        return max(0.0, min(upper, float(candidate)))
    except (TypeError, ValueError):
        raise PlannerConfigurationError(f"Значение {key}_{bound} не является числом: {candidate!r}")


def _build_soil_moisture_target(snapshot: Any) -> dict[str, Any] | None:
    targets = _to_mapping(getattr(snapshot, "targets", None))
    extensions = _to_mapping(targets.get("extensions"))
    subsystems = _to_mapping(extensions.get("subsystems"))
    irrigation = _to_mapping(subsystems.get("irrigation"))
    target = _to_mapping(irrigation.get("targets"))
    soil = _to_mapping(target.get("soil_moisture"))
    if not soil:
        # Fallback: day/night-кривая хранится в recipe phase extensions.
        day_night = _to_mapping(extensions.get("day_night"))
        soil_curve = _to_mapping(day_night.get("soil_moisture"))
        day = _optional_float(soil_curve.get("day"))
        night = _optional_float(soil_curve.get("night"))
        if day is None and night is None:
            return None

        lighting = _to_mapping(day_night.get("lighting"))
        lighting_targets = _to_mapping(targets.get("lighting"))
        day_start_time = (
            str((lighting.get("day_start_time") or lighting_targets.get("start_time") or "")).strip() or None
        )
        day_hours = _optional_float(lighting.get("day_hours"))
        if day_hours is None:
            day_hours = _optional_float(lighting_targets.get("photoperiod_hours"))

        return {
            "unit": "pct",
            "day": day,
            "night": night,
            "day_start_time": day_start_time,
            "day_hours": day_hours,
            "timezone": _require_greenhouse_timezone(snapshot),
        }
    return {
        "unit": str(soil.get("unit") or "pct").strip().lower() or "pct",
        "min": _optional_float(soil.get("min")),
        "max": _optional_float(soil.get("max")),
        "target": _optional_float(soil.get("target")),
        "timezone": _require_greenhouse_timezone(snapshot),
    }


def _require_greenhouse_timezone(snapshot: Any) -> str:
    phase_targets = _to_mapping(getattr(snapshot, "phase_targets", None))
    targets = _to_mapping(getattr(snapshot, "targets", None))
    raw = phase_targets.get("greenhouse_timezone")
    if not isinstance(raw, str) or not raw.strip():
        raw = targets.get("greenhouse_timezone")
    try:
        return canonical_timezone_name(raw if isinstance(raw, str) else None)
    except InvalidGreenhouseTimezone as exc:
        raise PlannerConfigurationError(
            f"Некорректный timezone теплицы {raw!r}: конфиг отклонён, команды не публикуются"
        ) from exc
