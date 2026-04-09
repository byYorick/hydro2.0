"""Каноническая семантика уровневых датчиков для AE3."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from ae3lite.infrastructure.read_models.active_grow_cycle_order_sql import SQL_ACTIVE_GROW_CYCLE_ORDER_BY


DEFAULT_LEVEL_SWITCH_ON_THRESHOLD = 0.5
DEFAULT_TELEMETRY_MAX_AGE_SEC = 60

DEFAULT_CLEAN_MAX_LABELS: tuple[str, ...] = (
    "level_clean_max",
    "clean_level_max",
    "clean_max",
)
DEFAULT_CLEAN_MIN_LABELS: tuple[str, ...] = (
    "level_clean_min",
    "clean_level_min",
    "clean_min",
)
DEFAULT_SOLUTION_MAX_LABELS: tuple[str, ...] = (
    "level_solution_max",
    "solution_level_max",
    "solution_max",
)
DEFAULT_SOLUTION_MIN_LABELS: tuple[str, ...] = (
    "level_solution_min",
    "solution_level_min",
    "solution_min",
)

_PH_LABELS = frozenset({"ph_sensor", "ph"})
_EC_LABELS = frozenset({"ec_sensor", "ec"})


def normalize_level_labels(*values: Any, defaults: Sequence[str] = ()) -> tuple[str, ...]:
    for value in values:
        if isinstance(value, str) and value.strip() != "":
            return (value.strip(),)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            labels = [str(item).strip() for item in value if str(item).strip() != ""]
            if labels:
                return tuple(labels)
    return tuple(str(item).strip() for item in defaults if str(item).strip() != "")


def level_snapshot_aliases(label: str) -> tuple[str, ...]:
    normalized = str(label or "").strip().lower()
    aliases = {normalized}
    if normalized.startswith("level_"):
        suffix = normalized[len("level_"):]
        parts = suffix.split("_")
        if len(parts) >= 2:
            aliases.add("_".join((parts[0], "level", *parts[1:])))
    parts = normalized.split("_")
    if len(parts) >= 3 and parts[1] == "level":
        aliases.add("_".join(("level", parts[0], *parts[2:])))
    return tuple(alias for alias in aliases if alias)


def level_switch_is_triggered(value: Any, *, threshold: float) -> bool | None:
    try:
        normalized = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if normalized is None:
        return None
    return normalized >= float(threshold)


def solution_tank_has_solution(level_state: Mapping[str, Any]) -> bool:
    return bool(level_state.get("is_triggered"))


def solution_tank_is_depleted(level_state: Mapping[str, Any]) -> bool:
    return not solution_tank_has_solution(level_state)


def coarse_clean_tank_level_percent(*, clean_max_triggered: bool | None) -> int | None:
    if clean_max_triggered is None:
        return None
    return 100 if clean_max_triggered else 0


def coarse_solution_tank_level_percent(
    *,
    solution_max_triggered: bool | None,
    solution_min_triggered: bool | None,
) -> int | None:
    if solution_max_triggered is True:
        return 100
    if solution_min_triggered is True:
        return 50
    if solution_max_triggered is False or solution_min_triggered is False:
        return 0
    return None


def default_level_monitor_config() -> dict[str, Any]:
    return {
        "level_switch_on_threshold": DEFAULT_LEVEL_SWITCH_ON_THRESHOLD,
        "telemetry_max_age_sec": DEFAULT_TELEMETRY_MAX_AGE_SEC,
        "clean_max_sensor_labels": DEFAULT_CLEAN_MAX_LABELS,
        "clean_min_sensor_labels": DEFAULT_CLEAN_MIN_LABELS,
        "solution_max_sensor_labels": DEFAULT_SOLUTION_MAX_LABELS,
        "solution_min_sensor_labels": DEFAULT_SOLUTION_MIN_LABELS,
    }


def build_level_monitor_config_from_bundle(config: Any) -> dict[str, Any]:
    defaults = default_level_monitor_config()
    zone_bundle = config.get("zone") if isinstance(config, Mapping) else None
    logic_profile = zone_bundle.get("logic_profile") if isinstance(zone_bundle, Mapping) else None
    active_profile = logic_profile.get("active_profile") if isinstance(logic_profile, Mapping) else None
    subsystems = active_profile.get("subsystems") if isinstance(active_profile, Mapping) else None
    diagnostics = _mapping_get(subsystems, "diagnostics")
    execution = _mapping_get(diagnostics, "execution")
    startup = _mapping_get(execution, "startup")
    return {
        "level_switch_on_threshold": _coerce_float(
            startup.get("level_switch_on_threshold"),
            default=defaults["level_switch_on_threshold"],
        ),
        "telemetry_max_age_sec": _coerce_int(
            startup.get("telemetry_max_age_sec"),
            default=defaults["telemetry_max_age_sec"],
        ),
        "clean_max_sensor_labels": normalize_level_labels(
            startup.get("clean_max_sensor_labels"),
            startup.get("clean_max_sensor_label"),
            defaults=defaults["clean_max_sensor_labels"],
        ),
        "clean_min_sensor_labels": normalize_level_labels(
            startup.get("clean_min_sensor_labels"),
            startup.get("clean_min_sensor_label"),
            defaults=defaults["clean_min_sensor_labels"],
        ),
        "solution_max_sensor_labels": normalize_level_labels(
            startup.get("solution_max_sensor_labels"),
            startup.get("solution_max_sensor_label"),
            defaults=defaults["solution_max_sensor_labels"],
        ),
        "solution_min_sensor_labels": normalize_level_labels(
            startup.get("solution_min_sensor_labels"),
            startup.get("solution_min_sensor_label"),
            defaults=defaults["solution_min_sensor_labels"],
        ),
    }


async def load_zone_level_monitor_config(*, zone_id: int, fetch_fn: Callable[..., Any]) -> dict[str, Any]:
    rows = await fetch_fn(
        f"""
        SELECT aeb.config
        FROM grow_cycles gc
        JOIN automation_effective_bundles aeb
          ON aeb.scope_type = 'grow_cycle'
         AND aeb.scope_id = gc.id
        WHERE gc.zone_id = $1
          AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
        {SQL_ACTIVE_GROW_CYCLE_ORDER_BY.strip()}
        LIMIT 1
        """,
        zone_id,
    )
    config = rows[0].get("config") if rows else None
    return build_level_monitor_config_from_bundle(config)


def summarize_zone_telemetry_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = dict(default_level_monitor_config())
    if isinstance(config, Mapping):
        cfg.update(config)
    threshold = _coerce_float(cfg.get("level_switch_on_threshold"), default=DEFAULT_LEVEL_SWITCH_ON_THRESHOLD)

    clean_max_triggered: bool | None = None
    solution_max_triggered: bool | None = None
    solution_min_triggered: bool | None = None
    result: dict[str, Any] = {}

    for row in rows:
        label = str(row.get("label") or "").strip().lower()
        value = row.get("last_value")
        if label in _PH_LABELS:
            result["ph"] = _to_float(value)
            continue
        if label in _EC_LABELS:
            result["ec"] = _to_float(value)
            continue

        role = resolve_level_role(label=label, config=cfg)
        if role is None:
            continue

        triggered = level_switch_is_triggered(value, threshold=threshold)
        if role == "clean_max":
            clean_max_triggered = triggered
        elif role == "solution_max":
            solution_max_triggered = triggered
        elif role == "solution_min":
            solution_min_triggered = triggered

    clean_percent = coarse_clean_tank_level_percent(clean_max_triggered=clean_max_triggered)
    if clean_percent is not None:
        result["clean_tank_level_percent"] = clean_percent

    nutrient_percent = coarse_solution_tank_level_percent(
        solution_max_triggered=solution_max_triggered,
        solution_min_triggered=solution_min_triggered,
    )
    if nutrient_percent is not None:
        result["nutrient_tank_level_percent"] = nutrient_percent

    return result


def resolve_level_role(*, label: str, config: Mapping[str, Any] | None = None) -> str | None:
    cfg = dict(default_level_monitor_config())
    if isinstance(config, Mapping):
        cfg.update(config)
    normalized = str(label or "").strip().lower()
    role_labels = {
        "clean_max": cfg["clean_max_sensor_labels"],
        "clean_min": cfg["clean_min_sensor_labels"],
        "solution_max": cfg["solution_max_sensor_labels"],
        "solution_min": cfg["solution_min_sensor_labels"],
    }
    for role, labels in role_labels.items():
        normalized_labels = {
            alias
            for item in labels
            for alias in level_snapshot_aliases(str(item or "").strip().lower())
        }
        if normalized in normalized_labels:
            return role
    return None


def _mapping_get(value: Any, key: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    nested = value.get(key)
    return nested if isinstance(nested, Mapping) else {}


def _coerce_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _coerce_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
