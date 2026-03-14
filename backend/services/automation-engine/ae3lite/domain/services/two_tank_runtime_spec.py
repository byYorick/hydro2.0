"""Native AE3-Lite runtime spec resolver for two-tank cycle_start."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError
from ae3lite.domain.services.phase_utils import normalize_phase_key as _normalize_phase_key

# ── Defaults for retry/attempt limits ────────────────────────────────────────

#: Maximum correction attempts during prepare_recirculation before escalating.
#: Replaces the former magic number 32767 (effectively infinite).
_DEFAULT_PREPARE_RECIRC_MAX_CORRECTION_ATTEMPTS: int = 20
_LEGACY_PREPARE_RECIRC_MAX_CORRECTION_ATTEMPTS_SENTINEL: int = 32767


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
    execution_prepare_tolerance = (
        execution.get("prepare_tolerance") if isinstance(execution.get("prepare_tolerance"), Mapping) else {}
    )
    execution_correction_cfg = (
        execution.get("correction") if isinstance(execution.get("correction"), Mapping) else {}
    )
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
    resolved_meta_cfg = _to_mapping(resolved_cfg.get("meta"))
    resolved_pump_calibration_cfg = _to_mapping(resolved_cfg.get("pump_calibration"))
    phase_overrides_cfg = _to_mapping(resolved_meta_cfg.get("phase_overrides"))
    solution_fill_overrides = _to_mapping(phase_overrides_cfg.get("solution_fill"))
    tank_recirc_overrides = _to_mapping(phase_overrides_cfg.get("tank_recirc"))
    irrigation_overrides = _to_mapping(phase_overrides_cfg.get("irrigation"))

    solution_fill_cfg = _merge_recursive(resolved_base_cfg, _to_mapping(resolved_phases_cfg.get("solution_fill")))
    tank_recirc_cfg = _merge_recursive(resolved_base_cfg, _to_mapping(resolved_phases_cfg.get("tank_recirc")))
    irrigation_cfg = _merge_recursive(resolved_base_cfg, _to_mapping(resolved_phases_cfg.get("irrigation")))
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
        "solution_fill": _build_correction_cfg(solution_fill_cfg, execution_correction_cfg, solution_fill_overrides, resolved_pump_calibration_cfg),
        "tank_recirc": _build_correction_cfg(tank_recirc_cfg, execution_correction_cfg, tank_recirc_overrides, resolved_pump_calibration_cfg),
        "irrigation": _build_correction_cfg(irrigation_cfg, execution_correction_cfg, irrigation_overrides, resolved_pump_calibration_cfg),
        "generic": _build_correction_cfg(
            active_phase_cfg,
            execution_correction_cfg,
            _to_mapping(phase_overrides_cfg.get(active_phase_key)),
            resolved_pump_calibration_cfg,
        ),
    }
    prepare_tolerance_by_phase = {
        "solution_fill": _build_prepare_tolerance_cfg(
            solution_fill_cfg, execution_prepare_tolerance, solution_fill_overrides
        ),
        "tank_recirc": _build_prepare_tolerance_cfg(
            tank_recirc_cfg, execution_prepare_tolerance, tank_recirc_overrides
        ),
        "irrigation": _build_prepare_tolerance_cfg(
            irrigation_cfg, execution_prepare_tolerance, irrigation_overrides
        ),
        "generic": _build_prepare_tolerance_cfg(
            active_phase_cfg,
            execution_prepare_tolerance,
            _to_mapping(phase_overrides_cfg.get(active_phase_key)),
        ),
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
        startup.get("required_node_types") or execution.get("required_node_types")
    )
    if not required_node_types:
        required_node_types = _normalize_required_node_types(
            _first_non_null(
                fill_runtime_cfg.get("required_node_types"),
                fill_runtime_cfg.get("required_node_type"),
                base_runtime_cfg.get("required_node_types"),
                base_runtime_cfg.get("required_node_type"),
            )
        )
    target_ph = _resolve_target(snapshot.targets, execution, "ph")
    target_ec = _resolve_target(snapshot.targets, execution, "ec")
    runtime: dict[str, Any] = {
        "required_node_types": required_node_types,
        "clean_fill_timeout_sec": _resolve_int(
            _prefer_phase_runtime_value(
                startup_value=startup.get("clean_fill_timeout_sec"),
                phase_value=fill_runtime_cfg.get("clean_fill_timeout_sec"),
                base_value=base_runtime_cfg.get("clean_fill_timeout_sec"),
                prefer_phase=_has_nested_override(solution_fill_overrides, "runtime", "clean_fill_timeout_sec"),
            ),
            1200,
            30,
        ),
        "solution_fill_timeout_sec": _resolve_int(
            _prefer_phase_runtime_value(
                startup_value=startup.get("solution_fill_timeout_sec"),
                phase_value=fill_runtime_cfg.get("solution_fill_timeout_sec"),
                base_value=base_runtime_cfg.get("solution_fill_timeout_sec"),
                prefer_phase=_has_nested_override(solution_fill_overrides, "runtime", "solution_fill_timeout_sec"),
            ),
            1800,
            30,
        ),
        "prepare_recirculation_timeout_sec": _resolve_int(
            _prefer_phase_runtime_value(
                startup_value=startup.get("prepare_recirculation_timeout_sec"),
                phase_value=recirc_retry_cfg.get("prepare_recirculation_timeout_sec"),
                base_value=base_retry_cfg.get("prepare_recirculation_timeout_sec"),
                prefer_phase=_has_nested_override(
                    tank_recirc_overrides, "retry", "prepare_recirculation_timeout_sec"
                ),
            ),
            1200,
            30,
        ),
        "level_poll_interval_sec": _resolve_int(
            _prefer_phase_runtime_value(
                startup_value=startup.get("level_poll_interval_sec"),
                phase_value=fill_timing_cfg.get("level_poll_interval_sec"),
                base_value=base_timing_cfg.get("level_poll_interval_sec"),
                prefer_phase=_has_nested_override(solution_fill_overrides, "timing", "level_poll_interval_sec"),
            ),
            10,
            5,
        ),
        "clean_fill_retry_cycles": _resolve_int(
            _prefer_phase_runtime_value(
                startup_value=startup.get("clean_fill_retry_cycles"),
                phase_value=fill_runtime_cfg.get("clean_fill_retry_cycles"),
                base_value=base_runtime_cfg.get("clean_fill_retry_cycles"),
                prefer_phase=_has_nested_override(solution_fill_overrides, "runtime", "clean_fill_retry_cycles"),
            ),
            1,
            0,
        ),
        "level_switch_on_threshold": _resolve_float(
            _prefer_phase_runtime_value(
                startup_value=startup.get("level_switch_on_threshold"),
                phase_value=fill_runtime_cfg.get("level_switch_on_threshold"),
                base_value=base_runtime_cfg.get("level_switch_on_threshold"),
                prefer_phase=_has_nested_override(solution_fill_overrides, "runtime", "level_switch_on_threshold"),
            ),
            0.5,
            0.0,
            1.0,
        ),
        "telemetry_max_age_sec": _resolve_int(
            _prefer_phase_runtime_value(
                startup_value=startup.get("telemetry_max_age_sec"),
                phase_value=fill_timing_cfg.get("telemetry_max_age_sec"),
                base_value=base_timing_cfg.get("telemetry_max_age_sec"),
                prefer_phase=_has_nested_override(solution_fill_overrides, "timing", "telemetry_max_age_sec"),
            ),
            60,
            5,
        ),
        "irr_state_max_age_sec": _resolve_int(
            _prefer_phase_runtime_value(
                startup_value=startup.get("irr_state_max_age_sec"),
                phase_value=fill_timing_cfg.get("irr_state_max_age_sec"),
                base_value=base_timing_cfg.get("irr_state_max_age_sec"),
                prefer_phase=_has_nested_override(solution_fill_overrides, "timing", "irr_state_max_age_sec"),
            ),
            30,
            5,
        ),
        "irr_state_wait_timeout_sec": _resolve_float(startup.get("irr_state_wait_timeout_sec"), 5.0, 0.0, 30.0),
        "sensor_mode_stabilization_time_sec": _resolve_int(
            _prefer_phase_runtime_value(
                startup_value=startup.get("sensor_mode_stabilization_time_sec"),
                phase_value=fill_timing_cfg.get("sensor_mode_stabilization_time_sec"),
                base_value=base_timing_cfg.get("sensor_mode_stabilization_time_sec"),
                prefer_phase=_has_nested_override(
                    solution_fill_overrides, "timing", "sensor_mode_stabilization_time_sec"
                ),
            ),
            60,
            0,
        ),
        "clean_max_sensor_labels": _normalize_labels(
            _first_non_null(
                startup.get("clean_max_sensor_labels"),
                startup.get("clean_max_sensor_label"),
                fill_runtime_cfg.get("clean_max_sensor_labels"),
                fill_runtime_cfg.get("clean_max_sensor_label"),
                base_runtime_cfg.get("clean_max_sensor_labels"),
                base_runtime_cfg.get("clean_max_sensor_label"),
            ),
            ("level_clean_max",),
        ),
        "clean_min_sensor_labels": _normalize_labels(
            _first_non_null(
                startup.get("clean_min_sensor_labels"),
                startup.get("clean_min_sensor_label"),
                fill_runtime_cfg.get("clean_min_sensor_labels"),
                fill_runtime_cfg.get("clean_min_sensor_label"),
                base_runtime_cfg.get("clean_min_sensor_labels"),
                base_runtime_cfg.get("clean_min_sensor_label"),
            ),
            ("level_clean_min",),
        ),
        "solution_max_sensor_labels": _normalize_labels(
            _first_non_null(
                startup.get("solution_max_sensor_labels"),
                startup.get("solution_max_sensor_label"),
                fill_runtime_cfg.get("solution_max_sensor_labels"),
                fill_runtime_cfg.get("solution_max_sensor_label"),
                base_runtime_cfg.get("solution_max_sensor_labels"),
                base_runtime_cfg.get("solution_max_sensor_label"),
            ),
            ("level_solution_max",),
        ),
        "solution_min_sensor_labels": _normalize_labels(
            _first_non_null(
                startup.get("solution_min_sensor_labels"),
                startup.get("solution_min_sensor_label"),
                fill_runtime_cfg.get("solution_min_sensor_labels"),
                fill_runtime_cfg.get("solution_min_sensor_label"),
                base_runtime_cfg.get("solution_min_sensor_labels"),
                base_runtime_cfg.get("solution_min_sensor_label"),
            ),
            ("level_solution_min",),
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
        # Correction config: dose channels, timing, dosing sensitivity.
        # "actuators" key is populated later by CycleStartPlanner after actuator resolution.
        "correction": dict(default_correction_cfg),
        "correction_by_phase": correction_by_phase,
        "command_specs": {},
    }
    if not runtime["required_node_types"]:
        runtime["required_node_types"] = ["irrig"]

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


def _validate_prepare_recirculation_timing(runtime: dict[str, Any]) -> None:
    """Raise PlannerConfigurationError if prepare_recirculation window is too short to run one correction cycle."""
    timeout_sec = runtime["prepare_recirculation_timeout_sec"]
    correction_by_phase = runtime.get("correction_by_phase")
    correction = correction_by_phase.get("tank_recirc") if isinstance(correction_by_phase, Mapping) else None
    if not isinstance(correction, Mapping):
        correction = runtime.get("correction", {})
    ec_mix_wait_sec = correction.get("ec_mix_wait_sec", 0)
    stabilization_sec = correction.get("stabilization_sec", 0)
    minimum_needed = ec_mix_wait_sec + stabilization_sec
    if timeout_sec < minimum_needed:
        raise PlannerConfigurationError(
            f"prepare_recirculation_timeout_sec={timeout_sec}s is less than "
            f"ec_mix_wait_sec + stabilization_sec = {ec_mix_wait_sec} + {stabilization_sec} = {minimum_needed}s; "
            "correction window is too short to complete even one mixing cycle"
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


def _resolve_prepare_recirculation_max_correction_attempts(raw_value: Any) -> int:
    value = _resolve_int(raw_value, _DEFAULT_PREPARE_RECIRC_MAX_CORRECTION_ATTEMPTS, 1)
    if value >= _LEGACY_PREPARE_RECIRC_MAX_CORRECTION_ATTEMPTS_SENTINEL:
        return _DEFAULT_PREPARE_RECIRC_MAX_CORRECTION_ATTEMPTS
    return value


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


def _prefer_phase_runtime_value(
    *,
    startup_value: Any,
    phase_value: Any,
    base_value: Any,
    prefer_phase: bool = False,
) -> Any:
    if prefer_phase and phase_value is not None:
        return phase_value
    if startup_value is not None:
        return startup_value
    return _first_non_null(phase_value, base_value)


def _has_nested_override(raw_value: Mapping[str, Any], *path: str) -> bool:
    if not path:
        return False
    current: Any = raw_value
    for index, key in enumerate(path):
        if not isinstance(current, Mapping) or key not in current:
            return False
        if index == len(path) - 1:
            return True
        current = current.get(key)
    return False


def _choose_phase_or_execution(*, phase_value: Any, execution_value: Any, prefer_phase: bool) -> Any:
    if prefer_phase and phase_value is not None:
        return phase_value
    return _first_non_null(execution_value, phase_value)


def _build_correction_cfg(
    phase_cfg: Mapping[str, Any],
    execution_correction_cfg: Mapping[str, Any],
    phase_override_cfg: Mapping[str, Any],
    pump_calibration_cfg: Mapping[str, Any],
) -> dict[str, Any]:
    timing_cfg = _to_mapping(phase_cfg.get("timing"))
    dosing_cfg = _to_mapping(phase_cfg.get("dosing"))
    retry_cfg = _to_mapping(phase_cfg.get("retry"))
    phase_controllers = _normalize_controllers(phase_cfg.get("controllers"))
    execution_controllers = _normalize_controllers(execution_correction_cfg.get("controllers"))
    if _has_nested_override(phase_override_cfg, "controllers"):
        controllers_cfg = _merge_recursive(execution_controllers, phase_controllers)
    else:
        controllers_cfg = _merge_recursive(phase_controllers, execution_controllers)

    return {
        "dose_ec_channel": str(
            _first_non_null(
                _choose_phase_or_execution(
                    phase_value=dosing_cfg.get("dose_ec_channel"),
                    execution_value=execution_correction_cfg.get("dose_ec_channel"),
                    prefer_phase=_has_nested_override(phase_override_cfg, "dosing", "dose_ec_channel"),
                ),
                "ec_npk_pump",
            )
        ).strip().lower(),
        "dose_ph_up_channel": str(
            _first_non_null(
                _choose_phase_or_execution(
                    phase_value=dosing_cfg.get("dose_ph_up_channel"),
                    execution_value=execution_correction_cfg.get("dose_ph_up_channel"),
                    prefer_phase=_has_nested_override(phase_override_cfg, "dosing", "dose_ph_up_channel"),
                ),
                "ph_base_pump",
            )
        ).strip().lower(),
        "dose_ph_down_channel": str(
            _first_non_null(
                _choose_phase_or_execution(
                    phase_value=dosing_cfg.get("dose_ph_down_channel"),
                    execution_value=execution_correction_cfg.get("dose_ph_down_channel"),
                    prefer_phase=_has_nested_override(phase_override_cfg, "dosing", "dose_ph_down_channel"),
                ),
                "ph_acid_pump",
            )
        ).strip().lower(),
        "ec_dose_ml_per_mS_L": _resolve_float(
            _choose_phase_or_execution(
                phase_value=dosing_cfg.get("ec_dose_ml_per_mS_L"),
                execution_value=execution_correction_cfg.get("ec_dose_ml_per_mS_L"),
                prefer_phase=_has_nested_override(phase_override_cfg, "dosing", "ec_dose_ml_per_mS_L"),
            ),
            1.0,
            0.001,
            100.0,
        ),
        "ph_dose_ml_per_unit_L": _resolve_float(
            _choose_phase_or_execution(
                phase_value=dosing_cfg.get("ph_dose_ml_per_unit_L"),
                execution_value=execution_correction_cfg.get("ph_dose_ml_per_unit_L"),
                prefer_phase=_has_nested_override(phase_override_cfg, "dosing", "ph_dose_ml_per_unit_L"),
            ),
            0.5,
            0.001,
            50.0,
        ),
        "max_ec_dose_ml": _resolve_float(
            _choose_phase_or_execution(
                phase_value=dosing_cfg.get("max_ec_dose_ml"),
                execution_value=execution_correction_cfg.get("max_ec_dose_ml"),
                prefer_phase=_has_nested_override(phase_override_cfg, "dosing", "max_ec_dose_ml"),
            ),
            50.0,
            1.0,
            500.0,
        ),
        "max_ph_dose_ml": _resolve_float(
            _choose_phase_or_execution(
                phase_value=dosing_cfg.get("max_ph_dose_ml"),
                execution_value=execution_correction_cfg.get("max_ph_dose_ml"),
                prefer_phase=_has_nested_override(phase_override_cfg, "dosing", "max_ph_dose_ml"),
            ),
            20.0,
            0.5,
            200.0,
        ),
        "ec_mix_wait_sec": _resolve_int(
            _choose_phase_or_execution(
                phase_value=timing_cfg.get("ec_mix_wait_sec"),
                execution_value=execution_correction_cfg.get("ec_mix_wait_sec"),
                prefer_phase=_has_nested_override(phase_override_cfg, "timing", "ec_mix_wait_sec"),
            ),
            120,
            10,
        ),
        "ph_mix_wait_sec": _resolve_int(
            _choose_phase_or_execution(
                phase_value=timing_cfg.get("ph_mix_wait_sec"),
                execution_value=execution_correction_cfg.get("ph_mix_wait_sec"),
                prefer_phase=_has_nested_override(phase_override_cfg, "timing", "ph_mix_wait_sec"),
            ),
            60,
            10,
        ),
        "stabilization_sec": _resolve_int(
            _choose_phase_or_execution(
                phase_value=timing_cfg.get("stabilization_sec"),
                execution_value=execution_correction_cfg.get("stabilization_sec"),
                prefer_phase=_has_nested_override(phase_override_cfg, "timing", "stabilization_sec"),
            ),
            60,
            0,
        ),
        "max_ec_correction_attempts": _resolve_int(
            _choose_phase_or_execution(
                phase_value=retry_cfg.get("max_ec_correction_attempts"),
                execution_value=execution_correction_cfg.get("max_ec_correction_attempts"),
                prefer_phase=_has_nested_override(phase_override_cfg, "retry", "max_ec_correction_attempts"),
            ),
            5,
            1,
        ),
        "max_ph_correction_attempts": _resolve_int(
            _choose_phase_or_execution(
                phase_value=retry_cfg.get("max_ph_correction_attempts"),
                execution_value=execution_correction_cfg.get("max_ph_correction_attempts"),
                prefer_phase=_has_nested_override(phase_override_cfg, "retry", "max_ph_correction_attempts"),
            ),
            5,
            1,
        ),
        "prepare_recirculation_max_attempts": _resolve_int(
            _choose_phase_or_execution(
                phase_value=retry_cfg.get("prepare_recirculation_max_attempts"),
                execution_value=execution_correction_cfg.get("prepare_recirculation_max_attempts"),
                prefer_phase=_has_nested_override(phase_override_cfg, "retry", "prepare_recirculation_max_attempts"),
            ),
            3,
            1,
        ),
        "prepare_recirculation_max_correction_attempts": _resolve_prepare_recirculation_max_correction_attempts(
            _choose_phase_or_execution(
                phase_value=retry_cfg.get("prepare_recirculation_max_correction_attempts"),
                execution_value=execution_correction_cfg.get("prepare_recirculation_max_correction_attempts"),
                prefer_phase=_has_nested_override(
                    phase_override_cfg, "retry", "prepare_recirculation_max_correction_attempts"
                ),
            )
        ),
        "solution_volume_l": _resolve_float(
            _choose_phase_or_execution(
                phase_value=dosing_cfg.get("solution_volume_l"),
                execution_value=execution_correction_cfg.get("solution_volume_l"),
                prefer_phase=_has_nested_override(phase_override_cfg, "dosing", "solution_volume_l"),
            ),
            100.0,
            1.0,
            10000.0,
        ),
        "controllers": controllers_cfg,
        "pump_calibration": dict(pump_calibration_cfg),
        "ec_component_policy": _normalize_component_policy(
            _choose_phase_or_execution(
                phase_value=phase_cfg.get("ec_component_policy"),
                execution_value=execution_correction_cfg.get("ec_component_policy"),
                prefer_phase=_has_nested_override(phase_override_cfg, "ec_component_policy"),
            )
        ),
        "actuators": {},
    }


def _build_prepare_tolerance_cfg(
    phase_cfg: Mapping[str, Any],
    execution_prepare_tolerance: Mapping[str, Any],
    phase_override_cfg: Mapping[str, Any],
) -> dict[str, Any]:
    phase_tolerance = _to_mapping(_to_mapping(phase_cfg.get("tolerance")).get("prepare_tolerance"))
    return {
        "ph_pct": _resolve_float(
            _choose_phase_or_execution(
                phase_value=phase_tolerance.get("ph_pct"),
                execution_value=execution_prepare_tolerance.get("ph_pct"),
                prefer_phase=_has_nested_override(phase_override_cfg, "tolerance", "prepare_tolerance", "ph_pct"),
            ),
            15.0,
            0.1,
            100.0,
        ),
        "ec_pct": _resolve_float(
            _choose_phase_or_execution(
                phase_value=phase_tolerance.get("ec_pct"),
                execution_value=execution_prepare_tolerance.get("ec_pct"),
                prefer_phase=_has_nested_override(phase_override_cfg, "tolerance", "prepare_tolerance", "ec_pct"),
            ),
            25.0,
            0.1,
            100.0,
        ),
    }

