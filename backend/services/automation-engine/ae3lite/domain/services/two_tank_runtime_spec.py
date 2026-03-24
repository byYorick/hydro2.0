"""Native AE3-Lite runtime spec resolver for two-tank cycle_start."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError
from ae3lite.domain.services.phase_utils import normalize_phase_key as _normalize_phase_key

# ── Defaults for retry/attempt limits ────────────────────────────────────────

#: Maximum correction attempts during prepare_recirculation before escalating.
_DEFAULT_PREPARE_RECIRC_MAX_CORRECTION_ATTEMPTS: int = 20
_MAX_CORRECTION_ATTEMPTS: int = 500


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
    commands_cfg = execution.get("two_tank_commands") if isinstance(execution.get("two_tank_commands"), Mapping) else {}
    zone_id = int(getattr(snapshot, "zone_id", 0) or 0)
    resolved_cfg = getattr(snapshot, "correction_config", None)
    if not isinstance(resolved_cfg, Mapping) or not resolved_cfg:
        raise PlannerConfigurationError(
            f"Zone {zone_id} has no correction_config; fail-closed for critical dosing parameters",
            code=ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
        )
    resolved_base_cfg = _to_mapping(resolved_cfg.get("base"))
    resolved_phases_cfg = _to_mapping(resolved_cfg.get("phases"))
    if not resolved_base_cfg and not resolved_phases_cfg:
        raise PlannerConfigurationError(
            f"Zone {zone_id} has empty correction_config(base/phases); fail-closed for critical dosing parameters",
            code=ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
        )
    _require_pid_configs(snapshot=snapshot, zone_id=zone_id)
    resolved_meta_cfg = _to_mapping(resolved_cfg.get("meta"))
    resolved_pump_calibration_cfg = _to_mapping(resolved_cfg.get("pump_calibration"))
    solution_fill_cfg = _merge_recursive(resolved_base_cfg, _to_mapping(resolved_phases_cfg.get("solution_fill")))
    tank_recirc_cfg = _merge_recursive(resolved_base_cfg, _to_mapping(resolved_phases_cfg.get("tank_recirc")))
    irrigation_cfg = _merge_recursive(resolved_base_cfg, _to_mapping(resolved_phases_cfg.get("irrigation")))
    _require_zone_correction_contract(zone_id=zone_id, config=resolved_base_cfg, config_name="base")
    _require_zone_correction_contract(zone_id=zone_id, config=solution_fill_cfg, config_name="phases.solution_fill")
    _require_zone_correction_contract(zone_id=zone_id, config=tank_recirc_cfg, config_name="phases.tank_recirc")
    _require_zone_correction_contract(zone_id=zone_id, config=irrigation_cfg, config_name="phases.irrigation")
    active_phase_key = _normalize_phase_key(getattr(snapshot, "workflow_phase", None))
    active_phase_cfg = {
        "solution_fill": solution_fill_cfg,
        "tank_recirc": tank_recirc_cfg,
        "irrigation": irrigation_cfg,
    }.get(active_phase_key, solution_fill_cfg if solution_fill_cfg else resolved_base_cfg)

    base_runtime_cfg = _to_mapping(resolved_base_cfg.get("runtime"))
    base_timing_cfg = _to_mapping(resolved_base_cfg.get("timing"))
    base_retry_cfg = _to_mapping(resolved_base_cfg.get("retry"))
    fill_runtime_cfg = _to_mapping(solution_fill_cfg.get("runtime"))
    fill_timing_cfg = _to_mapping(solution_fill_cfg.get("timing"))
    recirc_retry_cfg = _to_mapping(tank_recirc_cfg.get("retry"))

    correction_by_phase = {
        "solution_fill": _build_correction_cfg(solution_fill_cfg, resolved_pump_calibration_cfg),
        "tank_recirc": _build_correction_cfg(tank_recirc_cfg, resolved_pump_calibration_cfg),
        "irrigation": _build_correction_cfg(irrigation_cfg, resolved_pump_calibration_cfg),
        "generic": _build_correction_cfg(
            active_phase_cfg,
            resolved_pump_calibration_cfg,
        ),
    }
    prepare_tolerance_by_phase = {
        "solution_fill": _build_prepare_tolerance_cfg(solution_fill_cfg),
        "tank_recirc": _build_prepare_tolerance_cfg(tank_recirc_cfg),
        "irrigation": _build_prepare_tolerance_cfg(irrigation_cfg),
        "generic": _build_prepare_tolerance_cfg(active_phase_cfg),
    }

    default_correction_cfg = (
        correction_by_phase.get("solution_fill")
        or correction_by_phase.get(active_phase_key)
        or correction_by_phase["generic"]
    )
    default_prepare_tolerance = (
        prepare_tolerance_by_phase.get("solution_fill")
        or prepare_tolerance_by_phase.get(active_phase_key)
        or prepare_tolerance_by_phase["generic"]
    )

    required_node_types = _normalize_required_node_types(
        _first_non_null(
            fill_runtime_cfg.get("required_node_types"),
            fill_runtime_cfg.get("required_node_type"),
        )
    )
    if not required_node_types:
        raise PlannerConfigurationError(
            f"Zone {zone_id} correction_config.base/phases.solution_fill.runtime.required_node_type is required"
        )
    target_ph = _resolve_target(snapshot.targets, execution, "ph")
    target_ec = _resolve_target(snapshot.targets, execution, "ec")
    runtime: dict[str, Any] = {
        "required_node_types": required_node_types,
        "clean_fill_timeout_sec": _require_int(
            fill_runtime_cfg.get("clean_fill_timeout_sec"),
            path="correction_config.base/phases.solution_fill.runtime.clean_fill_timeout_sec",
            minimum=30,
        ),
        "solution_fill_timeout_sec": _require_int(
            fill_runtime_cfg.get("solution_fill_timeout_sec"),
            path="correction_config.base/phases.solution_fill.runtime.solution_fill_timeout_sec",
            minimum=30,
        ),
        "prepare_recirculation_timeout_sec": _require_int(
            recirc_retry_cfg.get("prepare_recirculation_timeout_sec"),
            path="correction_config.base/phases.tank_recirc.retry.prepare_recirculation_timeout_sec",
            minimum=30,
        ),
        "level_poll_interval_sec": _require_int(
            fill_timing_cfg.get("level_poll_interval_sec"),
            path="correction_config.base/phases.solution_fill.timing.level_poll_interval_sec",
            minimum=5,
        ),
        "clean_fill_retry_cycles": _require_int(
            fill_runtime_cfg.get("clean_fill_retry_cycles"),
            path="correction_config.base/phases.solution_fill.runtime.clean_fill_retry_cycles",
            minimum=0,
        ),
        "level_switch_on_threshold": _require_float(
            fill_runtime_cfg.get("level_switch_on_threshold"),
            path="correction_config.base/phases.solution_fill.runtime.level_switch_on_threshold",
            minimum=0.0,
            maximum=1.0,
        ),
        "telemetry_max_age_sec": _require_int(
            fill_timing_cfg.get("telemetry_max_age_sec"),
            path="correction_config.base/phases.solution_fill.timing.telemetry_max_age_sec",
            minimum=5,
        ),
        "irr_state_max_age_sec": _require_int(
            fill_timing_cfg.get("irr_state_max_age_sec"),
            path="correction_config.base/phases.solution_fill.timing.irr_state_max_age_sec",
            minimum=5,
        ),
        "irr_state_wait_timeout_sec": _resolve_float(execution.get("startup", {}).get("irr_state_wait_timeout_sec"), 5.0, 0.0, 30.0),
        "sensor_mode_stabilization_time_sec": _require_int(
            fill_timing_cfg.get("sensor_mode_stabilization_time_sec"),
            path="correction_config.base/phases.solution_fill.timing.sensor_mode_stabilization_time_sec",
            minimum=0,
        ),
        "clean_max_sensor_labels": _require_labels(
            _first_non_null(
                fill_runtime_cfg.get("clean_max_sensor_labels"),
                fill_runtime_cfg.get("clean_max_sensor_label"),
            ),
            path="correction_config.base/phases.solution_fill.runtime.clean_max_sensor_label",
        ),
        "clean_min_sensor_labels": _require_labels(
            _first_non_null(
                fill_runtime_cfg.get("clean_min_sensor_labels"),
                fill_runtime_cfg.get("clean_min_sensor_label"),
            ),
            path="correction_config.base/phases.solution_fill.runtime.clean_min_sensor_label",
        ),
        "solution_max_sensor_labels": _require_labels(
            _first_non_null(
                fill_runtime_cfg.get("solution_max_sensor_labels"),
                fill_runtime_cfg.get("solution_max_sensor_label"),
            ),
            path="correction_config.base/phases.solution_fill.runtime.solution_max_sensor_label",
        ),
        "solution_min_sensor_labels": _require_labels(
            _first_non_null(
                fill_runtime_cfg.get("solution_min_sensor_labels"),
                fill_runtime_cfg.get("solution_min_sensor_label"),
            ),
            path="correction_config.base/phases.solution_fill.runtime.solution_min_sensor_label",
        ),
        "target_ph": target_ph,
        "target_ec": target_ec,
        "target_ph_min": _resolve_target_bound(snapshot.targets, execution, "ph", "min", fallback=target_ph),
        "target_ph_max": _resolve_target_bound(snapshot.targets, execution, "ph", "max", fallback=target_ph),
        "target_ec_min": _resolve_target_bound(snapshot.targets, execution, "ec", "min", fallback=target_ec),
        "target_ec_max": _resolve_target_bound(snapshot.targets, execution, "ec", "max", fallback=target_ec),
        "prepare_tolerance": dict(default_prepare_tolerance),
        "prepare_tolerance_by_phase": prepare_tolerance_by_phase,
        "pid_state": dict(snapshot.pid_state) if isinstance(getattr(snapshot, "pid_state", None), Mapping) else {},
        "pid_configs": dict(snapshot.pid_configs) if isinstance(getattr(snapshot, "pid_configs", None), Mapping) else {},
        "process_calibrations": (
            dict(snapshot.process_calibrations)
            if isinstance(getattr(snapshot, "process_calibrations", None), Mapping)
            else {}
        ),
        # Correction config: dose channels, timing, dosing sensitivity.
        # "actuators" key is populated later by CycleStartPlanner after actuator resolution.
        "correction": dict(default_correction_cfg),
        "correction_by_phase": correction_by_phase,
        "command_specs": {},
    }
    _validate_prepare_recirculation_timing(runtime)

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


def _require_pid_configs(*, snapshot: Any, zone_id: int) -> None:
    pid_configs = getattr(snapshot, "pid_configs", None)
    if not isinstance(pid_configs, Mapping):
        raise PlannerConfigurationError(
            f"Zone {zone_id} has no pid authority mapping; fail-closed for critical correction parameters",
            code=ErrorCodes.ZONE_PID_CONFIG_MISSING_CRITICAL,
        )

    missing_types: list[str] = []
    for pid_type in ("ph", "ec"):
        entry = pid_configs.get(pid_type)
        config = entry.get("config") if isinstance(entry, Mapping) else None
        if not isinstance(config, Mapping) or not config:
            missing_types.append(pid_type)

    if missing_types:
        raise PlannerConfigurationError(
            f"Zone {zone_id} missing required pid authority documents for pid_type={', '.join(sorted(missing_types))}; "
            "fail-closed for critical correction parameters",
            code=ErrorCodes.ZONE_PID_CONFIG_MISSING_CRITICAL,
        )


_REQUIRED_ZONE_CORRECTION_TEMPLATE: dict[str, Any] = {
    "runtime": {
        "required_node_type": "",
        "clean_fill_timeout_sec": 0,
        "solution_fill_timeout_sec": 0,
        "clean_fill_retry_cycles": 0,
        "level_switch_on_threshold": 0.0,
        "clean_max_sensor_label": "",
        "clean_min_sensor_label": "",
        "solution_max_sensor_label": "",
        "solution_min_sensor_label": "",
    },
    "timing": {
        "sensor_mode_stabilization_time_sec": 0,
        "stabilization_sec": 0,
        "telemetry_max_age_sec": 0,
        "irr_state_max_age_sec": 0,
        "level_poll_interval_sec": 0,
    },
    "dosing": {
        "solution_volume_l": 0.0,
        "dose_ec_channel": "",
        "dose_ph_up_channel": "",
        "dose_ph_down_channel": "",
        "max_ec_dose_ml": 0.0,
        "max_ph_dose_ml": 0.0,
    },
    "retry": {
        "max_ec_correction_attempts": 0,
        "max_ph_correction_attempts": 0,
        "prepare_recirculation_timeout_sec": 0,
        "prepare_recirculation_max_attempts": 0,
        "prepare_recirculation_max_correction_attempts": 0,
        "telemetry_stale_retry_sec": 0,
        "decision_window_retry_sec": 0,
        "low_water_retry_sec": 0,
    },
    "tolerance": {
        "prepare_tolerance": {
            "ph_pct": 0.0,
            "ec_pct": 0.0,
        },
    },
    "controllers": {
        "ph": {
            "mode": "",
            "kp": 0.0,
            "ki": 0.0,
            "kd": 0.0,
            "derivative_filter_alpha": 0.0,
            "deadband": 0.0,
            "max_dose_ml": 0.0,
            "min_interval_sec": 0,
            "max_integral": 0.0,
            "anti_windup": {"enabled": False},
            "overshoot_guard": {"enabled": False, "hard_min": 0.0, "hard_max": 0.0},
            "no_effect": {"enabled": False, "max_count": 0},
            "observe": {
                "telemetry_period_sec": 0,
                "window_min_samples": 0,
                "decision_window_sec": 0,
                "observe_poll_sec": 0,
                "min_effect_fraction": 0.0,
                "stability_max_slope": 0.0,
                "no_effect_consecutive_limit": 0,
            },
        },
        "ec": {
            "mode": "",
            "kp": 0.0,
            "ki": 0.0,
            "kd": 0.0,
            "derivative_filter_alpha": 0.0,
            "deadband": 0.0,
            "max_dose_ml": 0.0,
            "min_interval_sec": 0,
            "max_integral": 0.0,
            "anti_windup": {"enabled": False},
            "overshoot_guard": {"enabled": False, "hard_min": 0.0, "hard_max": 0.0},
            "no_effect": {"enabled": False, "max_count": 0},
            "observe": {
                "telemetry_period_sec": 0,
                "window_min_samples": 0,
                "decision_window_sec": 0,
                "observe_poll_sec": 0,
                "min_effect_fraction": 0.0,
                "stability_max_slope": 0.0,
                "no_effect_consecutive_limit": 0,
            },
        },
    },
    "safety": {
        "safe_mode_on_no_effect": False,
        "block_on_active_no_effect_alert": False,
    },
}


def _require_zone_correction_contract(*, zone_id: int, config: Mapping[str, Any], config_name: str) -> None:
    missing_paths = _collect_missing_paths(config=config, template=_REQUIRED_ZONE_CORRECTION_TEMPLATE)
    if missing_paths:
        raise PlannerConfigurationError(
            f"Zone {zone_id} correction_config.{config_name} missing required fields: {', '.join(missing_paths)}; "
            "fail-closed for critical correction parameters",
            code=ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
        )


def _collect_missing_paths(*, config: Mapping[str, Any], template: Mapping[str, Any], prefix: str = "") -> list[str]:
    missing: list[str] = []
    for key, expected in template.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if key not in config:
            missing.append(path)
            continue
        actual = config.get(key)
        if isinstance(expected, Mapping):
            if not isinstance(actual, Mapping):
                missing.append(path)
                continue
            missing.extend(_collect_missing_paths(config=actual, template=expected, prefix=path))
    return missing

    missing_types: list[str] = []
    for pid_type in ("ph", "ec"):
        entry = pid_configs.get(pid_type)
        config = entry.get("config") if isinstance(entry, Mapping) else None
        if not isinstance(config, Mapping) or not config:
            missing_types.append(pid_type)

    if missing_types:
        raise PlannerConfigurationError(
            f"Zone {zone_id} missing required pid authority documents for pid_type={', '.join(sorted(missing_types))}; "
            "fail-closed for critical correction parameters",
            code=ErrorCodes.ZONE_PID_CONFIG_MISSING_CRITICAL,
        )


def _validate_prepare_recirculation_timing(runtime: dict[str, Any]) -> None:
    """Raise PlannerConfigurationError if prepare_recirculation window is too short to run one correction cycle."""
    timeout_sec = runtime["prepare_recirculation_timeout_sec"]
    correction_by_phase = runtime.get("correction_by_phase")
    correction = correction_by_phase.get("tank_recirc") if isinstance(correction_by_phase, Mapping) else None
    if not isinstance(correction, Mapping):
        correction = runtime.get("correction", {})
    stabilization_sec = correction.get("stabilization_sec", 0)
    process_calibrations = runtime.get("process_calibrations")
    tank_recirc_process_cfg = (
        process_calibrations.get("tank_recirc")
        if isinstance(process_calibrations, Mapping) and isinstance(process_calibrations.get("tank_recirc"), Mapping)
        else {}
    )
    observe_window_sec = _tank_recirc_observe_window_sec(correction=correction, process_cfg=tank_recirc_process_cfg)
    minimum_needed = stabilization_sec + observe_window_sec
    if timeout_sec < minimum_needed:
        raise PlannerConfigurationError(
            f"prepare_recirculation_timeout_sec={timeout_sec}s is less than "
            f"stabilization_sec + observe_window_sec = {stabilization_sec} + {observe_window_sec} = {minimum_needed}s; "
            "correction window is too short to complete one observation-driven correction cycle"
        )


def _tank_recirc_observe_window_sec(*, correction: Mapping[str, Any], process_cfg: Mapping[str, Any]) -> int:
    transport_delay_sec = _resolve_int(process_cfg.get("transport_delay_sec"), 0, 0)
    settle_sec = _resolve_int(process_cfg.get("settle_sec"), 0, 0)
    if transport_delay_sec > 0 and settle_sec > 0:
        return transport_delay_sec + settle_sec
    raise PlannerConfigurationError(
        "tank_recirc process calibration must provide transport_delay_sec and settle_sec"
    )


def _normalize_node_types(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes, bytearray)):
        return []
    result: list[str] = []
    for item in raw_value:
        normalized = str(item or "").strip().lower()
        if normalized:
            result.append(normalized)
    return result


def _normalize_required_node_types(raw_value: Any) -> list[str]:
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        return [normalized] if normalized else []
    return _normalize_node_types(raw_value)


def _normalize_labels(raw_value: Any, default_labels: Sequence[str]) -> list[str]:
    if isinstance(raw_value, str):
        raw_value = (raw_value,)
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes, bytearray)):
        raw_value = default_labels
    result: list[str] = []
    for item in raw_value:
        normalized = str(item or "").strip().lower()
        if normalized:
            result.append(normalized)
    return result


def _require_labels(raw_value: Any, *, path: str) -> list[str]:
    labels = _normalize_labels(raw_value, ())
    if labels:
        return labels
    raise PlannerConfigurationError(f"Missing required correction_config field: {path}")


def _resolve_int(raw_value: Any, default: int, minimum: int) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
    return max(int(minimum), value)


def _resolve_bounded_int(raw_value: Any, default: int, minimum: int, maximum: int) -> int:
    return min(int(maximum), _resolve_int(raw_value, default, minimum))


def _resolve_float(raw_value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = default
    return max(float(minimum), min(float(maximum), value))


def _require_int(raw_value: Any, *, path: str, minimum: int, maximum: int | None = None) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        raise PlannerConfigurationError(f"Missing or invalid correction_config field: {path}") from None
    if value < minimum:
        raise PlannerConfigurationError(f"correction_config field {path} must be >= {minimum}, got {value}")
    if maximum is not None and value > maximum:
        raise PlannerConfigurationError(f"correction_config field {path} must be <= {maximum}, got {value}")
    return int(value)


def _require_float(raw_value: Any, *, path: str, minimum: float, maximum: float | None = None) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        raise PlannerConfigurationError(f"Missing or invalid correction_config field: {path}") from None
    if value < minimum:
        raise PlannerConfigurationError(f"correction_config field {path} must be >= {minimum}, got {value}")
    if maximum is not None and value > maximum:
        raise PlannerConfigurationError(f"correction_config field {path} must be <= {maximum}, got {value}")
    return value


def _require_str(raw_value: Any, *, path: str) -> str:
    value = str(raw_value or "").strip().lower()
    if value:
        return value
    raise PlannerConfigurationError(f"Missing required correction_config field: {path}")


def _resolve_prepare_recirculation_max_correction_attempts(raw_value: Any) -> int:
    return _resolve_bounded_int(
        raw_value,
        _DEFAULT_PREPARE_RECIRC_MAX_CORRECTION_ATTEMPTS,
        1,
        _MAX_CORRECTION_ATTEMPTS,
    )


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


def _resolve_target_bound(
    targets: Mapping[str, Any],
    execution: Mapping[str, Any],
    key: str,
    bound: str,
    *,
    fallback: float,
) -> float:
    upper = 20.0 if key == "ec" else 14.0
    direct = execution.get(f"{key}_{bound}")
    if direct is None:
        direct = execution.get(f"target_{key}_{bound}")
    section = targets.get(key) if isinstance(targets.get(key), Mapping) else {}
    candidate = direct if direct is not None else section.get(bound)
    if candidate is None:
        return float(fallback)
    try:
        return max(0.0, min(upper, float(candidate)))
    except (TypeError, ValueError):
        raise PlannerConfigurationError(f"{key}_{bound} value is not numeric: {candidate!r}")


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


def _normalize_controllers(raw_value: Any) -> dict[str, Any]:
    if not isinstance(raw_value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for kind in ("ec", "ph"):
        controller = raw_value.get(kind)
        if isinstance(controller, Mapping):
            result[kind] = dict(controller)
    return result


def _normalize_component_policy(raw_value: Any) -> dict[str, Any]:
    if not isinstance(raw_value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for phase, policy in raw_value.items():
        if isinstance(policy, Mapping):
            result[str(phase).strip().lower()] = dict(policy)
    return result


def _to_mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, Mapping) else {}


def _merge_recursive(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = _merge_recursive(current, value)
            continue
        merged[key] = value
    return merged


def _first_non_null(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _build_correction_cfg(
    phase_cfg: Mapping[str, Any],
    pump_calibration_cfg: Mapping[str, Any],
) -> dict[str, Any]:
    timing_cfg = _to_mapping(phase_cfg.get("timing"))
    dosing_cfg = _to_mapping(phase_cfg.get("dosing"))
    retry_cfg = _to_mapping(phase_cfg.get("retry"))
    controllers_cfg = _normalize_controllers(phase_cfg.get("controllers"))

    return {
        "dose_ec_channel": _require_str(dosing_cfg.get("dose_ec_channel"), path="dosing.dose_ec_channel"),
        "dose_ph_up_channel": _require_str(dosing_cfg.get("dose_ph_up_channel"), path="dosing.dose_ph_up_channel"),
        "dose_ph_down_channel": _require_str(
            dosing_cfg.get("dose_ph_down_channel"), path="dosing.dose_ph_down_channel"
        ),
        "max_ec_dose_ml": _require_float(
            dosing_cfg.get("max_ec_dose_ml"),
            path="dosing.max_ec_dose_ml",
            minimum=1.0,
            maximum=500.0,
        ),
        "max_ph_dose_ml": _require_float(
            dosing_cfg.get("max_ph_dose_ml"),
            path="dosing.max_ph_dose_ml",
            minimum=0.5,
            maximum=200.0,
        ),
        "stabilization_sec": _require_int(
            timing_cfg.get("stabilization_sec"),
            path="timing.stabilization_sec",
            minimum=0,
        ),
        "max_ec_correction_attempts": _require_int(
            retry_cfg.get("max_ec_correction_attempts"),
            path="retry.max_ec_correction_attempts",
            minimum=1,
            maximum=_MAX_CORRECTION_ATTEMPTS,
        ),
        "max_ph_correction_attempts": _require_int(
            retry_cfg.get("max_ph_correction_attempts"),
            path="retry.max_ph_correction_attempts",
            minimum=1,
            maximum=_MAX_CORRECTION_ATTEMPTS,
        ),
        "prepare_recirculation_max_attempts": _require_int(
            retry_cfg.get("prepare_recirculation_max_attempts"),
            path="retry.prepare_recirculation_max_attempts",
            minimum=1,
        ),
        "prepare_recirculation_max_correction_attempts": _require_int(
            retry_cfg.get("prepare_recirculation_max_correction_attempts"),
            path="retry.prepare_recirculation_max_correction_attempts",
            minimum=1,
            maximum=_MAX_CORRECTION_ATTEMPTS,
        ),
        "telemetry_stale_retry_sec": _require_int(
            retry_cfg.get("telemetry_stale_retry_sec"),
            path="retry.telemetry_stale_retry_sec",
            minimum=1,
            maximum=3600,
        ),
        "decision_window_retry_sec": _require_int(
            retry_cfg.get("decision_window_retry_sec"),
            path="retry.decision_window_retry_sec",
            minimum=1,
            maximum=3600,
        ),
        "low_water_retry_sec": _require_int(
            retry_cfg.get("low_water_retry_sec"),
            path="retry.low_water_retry_sec",
            minimum=1,
            maximum=3600,
        ),
        "solution_volume_l": _require_float(
            dosing_cfg.get("solution_volume_l"),
            path="dosing.solution_volume_l",
            minimum=1.0,
            maximum=10000.0,
        ),
        "controllers": controllers_cfg,
        "pump_calibration": dict(pump_calibration_cfg),
        "ec_component_policy": _normalize_component_policy(phase_cfg.get("ec_component_policy")),
        "actuators": {},
    }


def _build_prepare_tolerance_cfg(
    phase_cfg: Mapping[str, Any],
) -> dict[str, Any]:
    phase_tolerance = _to_mapping(_to_mapping(phase_cfg.get("tolerance")).get("prepare_tolerance"))
    return {
        "ph_pct": _require_float(
            phase_tolerance.get("ph_pct"),
            path="tolerance.prepare_tolerance.ph_pct",
            minimum=0.1,
            maximum=100.0,
        ),
        "ec_pct": _require_float(
            phase_tolerance.get("ec_pct"),
            path="tolerance.prepare_tolerance.ec_pct",
            minimum=0.1,
            maximum=100.0,
        ),
    }
