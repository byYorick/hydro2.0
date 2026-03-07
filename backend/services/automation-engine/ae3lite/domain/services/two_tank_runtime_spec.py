"""Native AE3-Lite runtime spec resolver for two-tank cycle_start."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

from ae3lite.domain.errors import PlannerConfigurationError


def default_two_tank_command_plan(plan_name: str) -> list[dict[str, Any]]:
    defaults: dict[str, list[dict[str, Any]]] = {
        "clean_fill_start": [{"channel": "valve_clean_fill", "cmd": "set_relay", "params": {"state": True}}],
        "clean_fill_stop": [{"channel": "valve_clean_fill", "cmd": "set_relay", "params": {"state": False}}],
        "solution_fill_start": [
            {"channel": "valve_clean_supply", "cmd": "set_relay", "params": {"state": True}},
            {"channel": "valve_solution_fill", "cmd": "set_relay", "params": {"state": True}},
            {"channel": "pump_main", "cmd": "set_relay", "params": {"state": True}},
        ],
        "solution_fill_stop": [
            {"channel": "pump_main", "cmd": "set_relay", "params": {"state": False}},
            {"channel": "valve_solution_fill", "cmd": "set_relay", "params": {"state": False}},
            {"channel": "valve_clean_supply", "cmd": "set_relay", "params": {"state": False}},
        ],
        "prepare_recirculation_start": [
            {"channel": "valve_solution_supply", "cmd": "set_relay", "params": {"state": True}},
            {"channel": "valve_solution_fill", "cmd": "set_relay", "params": {"state": True}},
            {"channel": "pump_main", "cmd": "set_relay", "params": {"state": True}},
        ],
        "prepare_recirculation_stop": [
            {"channel": "pump_main", "cmd": "set_relay", "params": {"state": False}},
            {"channel": "valve_solution_fill", "cmd": "set_relay", "params": {"state": False}},
            {"channel": "valve_solution_supply", "cmd": "set_relay", "params": {"state": False}},
        ],
    }
    return [dict(item) for item in defaults.get(plan_name, ())]


def resolve_two_tank_runtime(snapshot: Any) -> dict[str, Any]:
    execution = snapshot.diagnostics_execution if isinstance(snapshot.diagnostics_execution, Mapping) else {}
    startup = execution.get("startup") if isinstance(execution.get("startup"), Mapping) else {}
    commands_cfg = execution.get("two_tank_commands") if isinstance(execution.get("two_tank_commands"), Mapping) else {}
    prepare_tolerance = (
        execution.get("prepare_tolerance") if isinstance(execution.get("prepare_tolerance"), Mapping) else {}
    )
    correction_cfg = (
        execution.get("correction") if isinstance(execution.get("correction"), Mapping) else {}
    )
    runtime: dict[str, Any] = {
        "required_node_types": _normalize_node_types(startup.get("required_node_types") or execution.get("required_node_types")),
        "clean_fill_timeout_sec": _resolve_int(startup.get("clean_fill_timeout_sec"), 1200, 30),
        "solution_fill_timeout_sec": _resolve_int(startup.get("solution_fill_timeout_sec"), 1800, 30),
        "prepare_recirculation_timeout_sec": _resolve_int(startup.get("prepare_recirculation_timeout_sec"), 1200, 30),
        "level_poll_interval_sec": _resolve_int(startup.get("level_poll_interval_sec"), 60, 5),
        "clean_fill_retry_cycles": _resolve_int(startup.get("clean_fill_retry_cycles"), 1, 0),
        "level_switch_on_threshold": _resolve_float(startup.get("level_switch_on_threshold"), 0.5, 0.0, 1.0),
        "telemetry_max_age_sec": _resolve_int(startup.get("telemetry_max_age_sec"), 300, 5),
        "irr_state_max_age_sec": _resolve_int(startup.get("irr_state_max_age_sec"), 30, 5),
        "sensor_mode_stabilization_time_sec": _resolve_int(startup.get("sensor_mode_stabilization_time_sec"), 60, 0),
        "clean_max_sensor_labels": _normalize_labels(startup.get("clean_max_sensor_labels"), ("level_clean_max",)),
        "clean_min_sensor_labels": _normalize_labels(startup.get("clean_min_sensor_labels"), ("level_clean_min",)),
        "solution_max_sensor_labels": _normalize_labels(startup.get("solution_max_sensor_labels"), ("level_solution_max",)),
        "solution_min_sensor_labels": _normalize_labels(startup.get("solution_min_sensor_labels"), ("level_solution_min",)),
        "target_ph": _resolve_target(snapshot.targets, execution, "ph"),
        "target_ec": _resolve_target(snapshot.targets, execution, "ec"),
        "prepare_tolerance": {
            "ph_pct": _resolve_float(prepare_tolerance.get("ph_pct"), 15.0, 0.1, 100.0),
            "ec_pct": _resolve_float(prepare_tolerance.get("ec_pct"), 25.0, 0.1, 100.0),
        },
        # Correction config: dose channels, timing, dosing sensitivity.
        # "actuators" key is populated later by CycleStartPlanner after actuator resolution.
        "correction": {
            "dose_ec_channel": str(correction_cfg.get("dose_ec_channel") or "dose_ec_a").strip().lower(),
            "dose_ph_up_channel": str(correction_cfg.get("dose_ph_up_channel") or "dose_ph_up").strip().lower(),
            "dose_ph_down_channel": str(correction_cfg.get("dose_ph_down_channel") or "dose_ph_down").strip().lower(),
            # ml of EC concentrate per 1 mS/cm of EC error per 1 L of solution
            "ec_dose_ml_per_mS_L": _resolve_float(correction_cfg.get("ec_dose_ml_per_mS_L"), 1.0, 0.001, 100.0),
            # ml of pH adjuster per 1 pH unit of error per 1 L of solution
            "ph_dose_ml_per_unit_L": _resolve_float(correction_cfg.get("ph_dose_ml_per_unit_L"), 0.5, 0.001, 50.0),
            "max_ec_dose_ml": _resolve_float(correction_cfg.get("max_ec_dose_ml"), 50.0, 1.0, 500.0),
            "max_ph_dose_ml": _resolve_float(correction_cfg.get("max_ph_dose_ml"), 20.0, 0.5, 200.0),
            "ec_mix_wait_sec": _resolve_int(correction_cfg.get("ec_mix_wait_sec"), 120, 10),
            "ph_mix_wait_sec": _resolve_int(correction_cfg.get("ph_mix_wait_sec"), 60, 10),
            "stabilization_sec": _resolve_int(correction_cfg.get("stabilization_sec"), 60, 0),
            "max_correction_attempts": _resolve_int(correction_cfg.get("max_correction_attempts"), 5, 1),
            # Total volume of solution in tank (litres) — used for dose scaling
            "solution_volume_l": _resolve_float(correction_cfg.get("solution_volume_l"), 100.0, 1.0, 10000.0),
            # actuators: dict populated by CycleStartPlanner — do not hardcode here
            "actuators": {},
        },
        "command_specs": {},
    }
    if not runtime["required_node_types"]:
        runtime["required_node_types"] = ["irrig"]

    for plan_name in (
        "clean_fill_start",
        "clean_fill_stop",
        "solution_fill_start",
        "solution_fill_stop",
        "prepare_recirculation_start",
        "prepare_recirculation_stop",
    ):
        runtime["command_specs"][plan_name] = _normalize_command_plan(
            commands_cfg.get(plan_name),
            default_plan=default_two_tank_command_plan(plan_name),
            default_node_types=runtime["required_node_types"],
        )
    return runtime


def _normalize_node_types(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes, bytearray)):
        return []
    result: list[str] = []
    for item in raw_value:
        normalized = str(item or "").strip().lower()
        if normalized:
            result.append(normalized)
    return result


def _normalize_labels(raw_value: Any, default_labels: Sequence[str]) -> list[str]:
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes, bytearray)):
        raw_value = default_labels
    result: list[str] = []
    for item in raw_value:
        normalized = str(item or "").strip().lower()
        if normalized:
            result.append(normalized)
    return result


def _resolve_int(raw_value: Any, default: int, minimum: int) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
    return max(int(minimum), value)


def _resolve_float(raw_value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = default
    return max(float(minimum), min(float(maximum), value))


def _resolve_target(targets: Mapping[str, Any], execution: Mapping[str, Any], key: str) -> float:
    upper = 20.0 if key == "ec" else 14.0
    direct = execution.get(f"target_{key}")
    if direct is not None:
        try:
            return max(0.0, min(upper, float(direct)))
        except (TypeError, ValueError):
            raise PlannerConfigurationError(f"target_{key} in execution config is not numeric: {direct!r}")
    section = targets.get(key) if isinstance(targets.get(key), Mapping) else {}
    candidate = section.get("target")
    if candidate is None:
        candidate = targets.get(f"target_{key}")
    if candidate is None:
        raise PlannerConfigurationError(
            f"No target_{key} configured for zone; hardcoded defaults are forbidden (spec §5.3.4)"
        )
    try:
        return max(0.0, min(upper, float(candidate)))
    except (TypeError, ValueError):
        raise PlannerConfigurationError(f"target_{key} value is not numeric: {candidate!r}")


def _normalize_command_plan(
    raw_value: Any,
    *,
    default_plan: Sequence[Mapping[str, Any]],
    default_node_types: Sequence[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes, bytearray)):
        raw_value = default_plan
    normalized: list[dict[str, Any]] = []
    for entry in raw_value:
        if not isinstance(entry, Mapping):
            continue
        channel = str(entry.get("channel") or "").strip().lower()
        cmd = str(entry.get("cmd") or "").strip()
        params = entry.get("params")
        if not channel or not cmd or not isinstance(params, Mapping):
            continue
        normalized.append(
            {
                "channel": channel,
                "cmd": cmd,
                "params": dict(params),
                "node_types": _normalize_node_types(entry.get("node_types")) or list(default_node_types),
            }
        )
    return normalized
