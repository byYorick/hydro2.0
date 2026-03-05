"""Helpers for two-tank runtime configuration resolution."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence

ExtractExecutionConfigFn = Callable[[Dict[str, Any]], Dict[str, Any]]
NormalizeNodeTypeListFn = Callable[[Any, Sequence[str]], List[str]]
ResolveIntFn = Callable[[Any, int, int], int]
ResolveFloatFn = Callable[[Any, float, float, float], float]
NormalizeLabelsFn = Callable[[Any, Sequence[str]], List[str]]

_logger = logging.getLogger(__name__)


def default_two_tank_command_plan(plan_name: str) -> List[Dict[str, Any]]:
    defaults: Dict[str, List[Dict[str, Any]]] = {
        "clean_fill_start": [
            {"channel": "valve_clean_fill", "cmd": "set_relay", "params": {"state": True}},
        ],
        "clean_fill_stop": [
            {"channel": "valve_clean_fill", "cmd": "set_relay", "params": {"state": False}},
        ],
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
        "irrigation_recovery_start": [
            {"channel": "valve_irrigation", "cmd": "set_relay", "params": {"state": False}},
            {"channel": "valve_solution_supply", "cmd": "set_relay", "params": {"state": True}},
            {"channel": "valve_solution_fill", "cmd": "set_relay", "params": {"state": True}},
            {"channel": "pump_main", "cmd": "set_relay", "params": {"state": True}},
        ],
        "irrigation_recovery_stop": [
            {"channel": "pump_main", "cmd": "set_relay", "params": {"state": False}},
            {"channel": "valve_solution_fill", "cmd": "set_relay", "params": {"state": False}},
            {"channel": "valve_solution_supply", "cmd": "set_relay", "params": {"state": False}},
            {"channel": "valve_irrigation", "cmd": "set_relay", "params": {"state": True}},
        ],
    }
    return [dict(item) for item in defaults.get(plan_name, [])]


def normalize_command_plan(
    raw: Any,
    *,
    default_plan: Sequence[Dict[str, Any]],
    default_node_types: Sequence[str],
    default_allow_no_effect: bool,
    default_dedupe_bypass: bool,
    normalize_node_type_list_fn: NormalizeNodeTypeListFn,
) -> List[Dict[str, Any]]:
    if not isinstance(raw, Sequence):
        raw = default_plan
    normalized: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        channel = str(item.get("channel") or "").strip().lower()
        if not channel:
            continue
        cmd = str(item.get("cmd") or "set_relay").strip() or "set_relay"
        params = item.get("params") if isinstance(item.get("params"), dict) else {}
        node_types = normalize_node_type_list_fn(item.get("node_types"), default_node_types)
        allow_no_effect = (
            bool(item.get("allow_no_effect"))
            if "allow_no_effect" in item
            else bool(default_allow_no_effect)
        )
        dedupe_bypass = (
            bool(item.get("dedupe_bypass"))
            if "dedupe_bypass" in item
            else bool(default_dedupe_bypass)
        )
        normalized.append(
            {
                "channel": channel,
                "cmd": cmd,
                "params": dict(params),
                "node_types": node_types,
                "allow_no_effect": allow_no_effect,
                "dedupe_bypass": dedupe_bypass,
            }
        )
    return normalized


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _pick_first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _resolve_optional_float(raw: Any, *, minimum: float, maximum: float) -> Optional[float]:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return max(float(minimum), min(float(maximum), value))


def _compact_optional_map(values: Dict[str, Optional[float]]) -> Dict[str, float]:
    return {key: float(value) for key, value in values.items() if value is not None}


def _resolve_volume_based_timeout_sec(
    *,
    volume_l_raw: Any,
    flow_lpm_raw: Any,
    flow_lps_raw: Any,
    timeout_buffer_pct: float,
    resolve_float_fn: ResolveFloatFn,
    minimum_timeout_sec: int = 30,
) -> Optional[int]:
    volume_l = resolve_float_fn(volume_l_raw, -1.0, -1.0, 100000.0)
    if volume_l <= 0.0:
        return None

    flow_lpm = resolve_float_fn(flow_lpm_raw, -1.0, -1.0, 100000.0)
    flow_lps = resolve_float_fn(flow_lps_raw, -1.0, -1.0, 100000.0)
    if flow_lpm <= 0.0 and flow_lps > 0.0:
        flow_lpm = flow_lps * 60.0
    if flow_lpm <= 0.0:
        return None

    base_sec = (volume_l / flow_lpm) * 60.0
    if base_sec <= 0.0:
        return None

    timeout_sec = int(round(base_sec * (1.0 + max(0.0, timeout_buffer_pct) / 100.0)))
    return max(minimum_timeout_sec, timeout_sec)


def resolve_two_tank_runtime_config(
    payload: Dict[str, Any],
    *,
    refill_check_delay_sec: int,
    extract_execution_config_fn: ExtractExecutionConfigFn,
    normalize_node_type_list_fn: NormalizeNodeTypeListFn,
    resolve_int_fn: ResolveIntFn,
    resolve_float_fn: ResolveFloatFn,
    normalize_labels_fn: NormalizeLabelsFn,
    zone_targets: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    execution = extract_execution_config_fn(payload)
    startup = execution.get("startup") if isinstance(execution.get("startup"), dict) else {}
    targets_payload = (
        zone_targets
        if isinstance(zone_targets, dict)
        else (payload.get("targets") if isinstance(payload.get("targets"), dict) else {})
    )
    irrigation_targets = _as_dict(targets_payload.get("irrigation"))
    irrigation_execution = _as_dict(irrigation_targets.get("execution"))
    required_node_types = normalize_node_type_list_fn(startup.get("required_node_types"), ("irrig",))

    commands_cfg = execution.get("two_tank_commands") if isinstance(execution.get("two_tank_commands"), dict) else {}
    clean_fill_start_default = default_two_tank_command_plan("clean_fill_start")
    clean_fill_stop_default = default_two_tank_command_plan("clean_fill_stop")
    solution_fill_start_default = default_two_tank_command_plan("solution_fill_start")
    solution_fill_stop_default = default_two_tank_command_plan("solution_fill_stop")
    prepare_recirculation_start_default = default_two_tank_command_plan("prepare_recirculation_start")
    prepare_recirculation_stop_default = default_two_tank_command_plan("prepare_recirculation_stop")
    irrigation_recovery_start_default = default_two_tank_command_plan("irrigation_recovery_start")
    irrigation_recovery_stop_default = default_two_tank_command_plan("irrigation_recovery_stop")

    clean_fill_start = normalize_command_plan(
        commands_cfg.get("clean_fill_start"),
        default_plan=clean_fill_start_default,
        default_node_types=required_node_types,
        default_allow_no_effect=True,
        default_dedupe_bypass=True,
        normalize_node_type_list_fn=normalize_node_type_list_fn,
    )
    clean_fill_stop = normalize_command_plan(
        commands_cfg.get("clean_fill_stop"),
        default_plan=clean_fill_stop_default,
        default_node_types=required_node_types,
        default_allow_no_effect=False,
        default_dedupe_bypass=True,
        normalize_node_type_list_fn=normalize_node_type_list_fn,
    )
    solution_fill_start = normalize_command_plan(
        commands_cfg.get("solution_fill_start"),
        default_plan=solution_fill_start_default,
        default_node_types=required_node_types,
        default_allow_no_effect=True,
        default_dedupe_bypass=True,
        normalize_node_type_list_fn=normalize_node_type_list_fn,
    )
    solution_fill_stop = normalize_command_plan(
        commands_cfg.get("solution_fill_stop"),
        default_plan=solution_fill_stop_default,
        default_node_types=required_node_types,
        default_allow_no_effect=False,
        default_dedupe_bypass=True,
        normalize_node_type_list_fn=normalize_node_type_list_fn,
    )
    prepare_recirculation_start = normalize_command_plan(
        commands_cfg.get("prepare_recirculation_start"),
        default_plan=prepare_recirculation_start_default,
        default_node_types=required_node_types,
        default_allow_no_effect=True,
        default_dedupe_bypass=True,
        normalize_node_type_list_fn=normalize_node_type_list_fn,
    )
    prepare_recirculation_stop = normalize_command_plan(
        commands_cfg.get("prepare_recirculation_stop"),
        default_plan=prepare_recirculation_stop_default,
        default_node_types=required_node_types,
        default_allow_no_effect=False,
        default_dedupe_bypass=True,
        normalize_node_type_list_fn=normalize_node_type_list_fn,
    )
    irrigation_recovery_start = normalize_command_plan(
        commands_cfg.get("irrigation_recovery_start"),
        default_plan=irrigation_recovery_start_default,
        default_node_types=required_node_types,
        default_allow_no_effect=True,
        default_dedupe_bypass=True,
        normalize_node_type_list_fn=normalize_node_type_list_fn,
    )
    irrigation_recovery_stop = normalize_command_plan(
        commands_cfg.get("irrigation_recovery_stop"),
        default_plan=irrigation_recovery_stop_default,
        default_node_types=required_node_types,
        default_allow_no_effect=False,
        default_dedupe_bypass=True,
        normalize_node_type_list_fn=normalize_node_type_list_fn,
    )

    recovery_cfg = execution.get("irrigation_recovery") if isinstance(execution.get("irrigation_recovery"), dict) else {}
    degraded_cfg = recovery_cfg.get("degraded_tolerance") if isinstance(recovery_cfg.get("degraded_tolerance"), dict) else {}
    prepare_tolerance_cfg = execution.get("prepare_tolerance") if isinstance(execution.get("prepare_tolerance"), dict) else {}
    recovery_tolerance_cfg = recovery_cfg.get("target_tolerance") if isinstance(recovery_cfg.get("target_tolerance"), dict) else {}
    fallback_prepare_tolerance_cfg = execution.get("prepare_target_tolerance") if isinstance(execution.get("prepare_target_tolerance"), dict) else {}
    prepare_hard_bounds_cfg = execution.get("prepare_hard_bounds") if isinstance(execution.get("prepare_hard_bounds"), dict) else {}
    prepare_abs_tolerance_cfg = execution.get("prepare_absolute_tolerance") if isinstance(execution.get("prepare_absolute_tolerance"), dict) else {}
    if not prepare_abs_tolerance_cfg:
        prepare_abs_tolerance_cfg = (
            execution.get("prepare_target_tolerance_abs")
            if isinstance(execution.get("prepare_target_tolerance_abs"), dict)
            else {}
        )

    ph_payload = targets_payload.get("ph") if isinstance(targets_payload.get("ph"), dict) else {}
    ec_payload = targets_payload.get("ec") if isinstance(targets_payload.get("ec"), dict) else {}
    nutrition_payload = targets_payload.get("nutrition") if isinstance(targets_payload.get("nutrition"), dict) else {}
    nutrition_components = nutrition_payload.get("components") if isinstance(nutrition_payload.get("components"), dict) else {}
    nutrition_npk = nutrition_components.get("npk") if isinstance(nutrition_components.get("npk"), dict) else {}

    target_ph_raw = execution.get("target_ph")
    if target_ph_raw is None:
        target_ph_raw = ph_payload.get("target")
    if target_ph_raw is None:
        target_ph_raw = targets_payload.get("target_ph")
    if target_ph_raw is None:
        target_ph_raw = targets_payload.get("ph_target")
    target_ec_raw = execution.get("target_ec")
    if target_ec_raw is None:
        target_ec_raw = ec_payload.get("target")
    if target_ec_raw is None:
        target_ec_raw = targets_payload.get("target_ec")
    if target_ec_raw is None:
        target_ec_raw = targets_payload.get("ec_target")
    target_ph = resolve_float_fn(target_ph_raw, 5.8, 0.1, 14.0)
    target_ec = resolve_float_fn(target_ec_raw, 1.6, 0.0, 20.0)
    if target_ph_raw is None:
        _logger.warning(
            "Zone two_tank: target_ph not found, using default %.2f",
            target_ph,
        )
    if target_ec_raw is None:
        _logger.warning(
            "Zone two_tank: target_ec not found, using default %.3f",
            target_ec,
        )
    npk_ratio_raw = execution.get("nutrient_npk_ratio_pct")
    if npk_ratio_raw is None:
        npk_ratio_raw = execution.get("npk_ratio_pct")
    if npk_ratio_raw is None:
        npk_ratio_raw = startup.get("nutrient_npk_ratio_pct")
    if npk_ratio_raw is None:
        npk_ratio_raw = nutrition_npk.get("ratio_pct")
    nutrient_npk_ratio_pct = resolve_float_fn(npk_ratio_raw, 100.0, 0.0, 100.0)
    target_ec_prepare_raw = execution.get("target_ec_prepare_npk")
    if target_ec_prepare_raw is None:
        target_ec_prepare_raw = startup.get("target_ec_prepare_npk")
    if target_ec_prepare_raw is None:
        target_ec_prepare_raw = target_ec * (nutrient_npk_ratio_pct / 100.0)
    target_ec_prepare = resolve_float_fn(target_ec_prepare_raw, target_ec, 0.0, 20.0)
    prepare_hard_bounds = _compact_optional_map(
        {
            "ph_min": _resolve_optional_float(
                _pick_first(prepare_hard_bounds_cfg.get("ph_min"), ph_payload.get("min")),
                minimum=0.1,
                maximum=14.0,
            ),
            "ph_max": _resolve_optional_float(
                _pick_first(prepare_hard_bounds_cfg.get("ph_max"), ph_payload.get("max")),
                minimum=0.1,
                maximum=14.0,
            ),
            "ec_min": _resolve_optional_float(
                _pick_first(prepare_hard_bounds_cfg.get("ec_min"), ec_payload.get("min")),
                minimum=0.0,
                maximum=20.0,
            ),
            "ec_max": _resolve_optional_float(
                _pick_first(prepare_hard_bounds_cfg.get("ec_max"), ec_payload.get("max")),
                minimum=0.0,
                maximum=20.0,
            ),
        }
    )
    if prepare_hard_bounds.get("ph_min") is not None and prepare_hard_bounds.get("ph_max") is not None:
        if prepare_hard_bounds["ph_min"] > prepare_hard_bounds["ph_max"]:
            prepare_hard_bounds["ph_min"], prepare_hard_bounds["ph_max"] = (
                prepare_hard_bounds["ph_max"],
                prepare_hard_bounds["ph_min"],
            )
    if prepare_hard_bounds.get("ec_min") is not None and prepare_hard_bounds.get("ec_max") is not None:
        if prepare_hard_bounds["ec_min"] > prepare_hard_bounds["ec_max"]:
            prepare_hard_bounds["ec_min"], prepare_hard_bounds["ec_max"] = (
                prepare_hard_bounds["ec_max"],
                prepare_hard_bounds["ec_min"],
            )
    prepare_absolute_tolerance = _compact_optional_map(
        {
            "ph_abs": _resolve_optional_float(
                _pick_first(
                    prepare_abs_tolerance_cfg.get("ph_abs"),
                    prepare_tolerance_cfg.get("ph_abs"),
                    fallback_prepare_tolerance_cfg.get("ph_abs"),
                ),
                minimum=0.0,
                maximum=14.0,
            ),
            "ec_abs": _resolve_optional_float(
                _pick_first(
                    prepare_abs_tolerance_cfg.get("ec_abs"),
                    prepare_tolerance_cfg.get("ec_abs"),
                    fallback_prepare_tolerance_cfg.get("ec_abs"),
                ),
                minimum=0.0,
                maximum=20.0,
            ),
        }
    )

    recovery_max_attempts_raw = recovery_cfg.get("max_attempts")
    if recovery_max_attempts_raw is None:
        recovery_max_attempts_raw = recovery_cfg.get("max_continue_attempts")

    clean_fill_timeout_raw = startup.get("clean_fill_timeout_sec")
    solution_fill_timeout_raw = startup.get("solution_fill_timeout_sec")
    clean_fill_timeout_default = resolve_int_fn(clean_fill_timeout_raw, 1200, 30)
    solution_fill_timeout_default = resolve_int_fn(solution_fill_timeout_raw, 1800, 30)
    timeout_buffer_pct = resolve_float_fn(
        _pick_first(
            startup.get("fill_timeout_buffer_pct"),
            startup.get("timeout_buffer_pct"),
            execution.get("fill_timeout_buffer_pct"),
        ),
        20.0,
        0.0,
        200.0,
    )
    timeout_strategy = str(startup.get("fill_timeout_strategy") or "").strip().lower()
    use_volume_timeouts = bool(startup.get("fill_timeout_from_volume")) or timeout_strategy in {
        "volume",
        "volume_based",
        "flow",
        "auto",
    }
    default_flow_lpm = _pick_first(
        startup.get("fill_flow_lpm"),
        startup.get("flow_lpm"),
        execution.get("fill_flow_lpm"),
        irrigation_execution.get("fill_flow_lpm"),
    )
    default_flow_lps = _pick_first(
        startup.get("fill_flow_lps"),
        startup.get("flow_lps"),
        execution.get("fill_flow_lps"),
        irrigation_execution.get("fill_flow_lps"),
    )

    clean_fill_timeout_volume_based = _resolve_volume_based_timeout_sec(
        volume_l_raw=_pick_first(
            startup.get("clean_fill_volume_l"),
            execution.get("clean_fill_volume_l"),
            irrigation_execution.get("clean_tank_fill_l"),
        ),
        flow_lpm_raw=_pick_first(
            startup.get("clean_fill_flow_lpm"),
            execution.get("clean_fill_flow_lpm"),
            irrigation_execution.get("clean_fill_flow_lpm"),
            default_flow_lpm,
        ),
        flow_lps_raw=_pick_first(
            startup.get("clean_fill_flow_lps"),
            execution.get("clean_fill_flow_lps"),
            irrigation_execution.get("clean_fill_flow_lps"),
            default_flow_lps,
        ),
        timeout_buffer_pct=timeout_buffer_pct,
        resolve_float_fn=resolve_float_fn,
    )
    solution_fill_timeout_volume_based = _resolve_volume_based_timeout_sec(
        volume_l_raw=_pick_first(
            startup.get("solution_fill_volume_l"),
            execution.get("solution_fill_volume_l"),
            irrigation_execution.get("nutrient_tank_target_l"),
        ),
        flow_lpm_raw=_pick_first(
            startup.get("solution_fill_flow_lpm"),
            execution.get("solution_fill_flow_lpm"),
            irrigation_execution.get("solution_fill_flow_lpm"),
            default_flow_lpm,
        ),
        flow_lps_raw=_pick_first(
            startup.get("solution_fill_flow_lps"),
            execution.get("solution_fill_flow_lps"),
            irrigation_execution.get("solution_fill_flow_lps"),
            default_flow_lps,
        ),
        timeout_buffer_pct=timeout_buffer_pct,
        resolve_float_fn=resolve_float_fn,
    )

    clean_fill_timeout_sec = clean_fill_timeout_default
    if use_volume_timeouts or clean_fill_timeout_raw is None:
        if clean_fill_timeout_volume_based is not None:
            clean_fill_timeout_sec = clean_fill_timeout_volume_based
    solution_fill_timeout_sec = solution_fill_timeout_default
    if use_volume_timeouts or solution_fill_timeout_raw is None:
        if solution_fill_timeout_volume_based is not None:
            solution_fill_timeout_sec = solution_fill_timeout_volume_based
    if clean_fill_timeout_sec != clean_fill_timeout_default or solution_fill_timeout_sec != solution_fill_timeout_default:
        _logger.info(
            "Zone two_tank: volume-based fill timeout applied (clean_fill_timeout_sec=%s solution_fill_timeout_sec=%s buffer_pct=%.1f)",
            clean_fill_timeout_sec,
            solution_fill_timeout_sec,
            timeout_buffer_pct,
        )

    return {
        "required_node_types": required_node_types,
        "clean_fill_timeout_sec": clean_fill_timeout_sec,
        "solution_fill_timeout_sec": solution_fill_timeout_sec,
        "poll_interval_sec": resolve_int_fn(startup.get("level_poll_interval_sec"), refill_check_delay_sec, 10),
        "clean_fill_retry_cycles": resolve_int_fn(startup.get("clean_fill_retry_cycles"), 1, 0),
        "prepare_recirculation_timeout_sec": resolve_int_fn(startup.get("prepare_recirculation_timeout_sec"), 1200, 30),
        "irr_state_max_age_sec": resolve_int_fn(startup.get("irr_state_max_age_sec"), 30, 5),
        "irr_state_wait_timeout_sec": resolve_int_fn(startup.get("irr_state_wait_timeout_sec"), 2, 0),
        "irrigation_recovery_timeout_sec": resolve_int_fn(recovery_cfg.get("timeout_sec"), 600, 30),
        "irrigation_recovery_max_attempts": resolve_int_fn(recovery_max_attempts_raw, 2, 1),
        "irrigation_recovery_retry_timeout_multiplier": resolve_float_fn(
            recovery_cfg.get("retry_timeout_multiplier"),
            1.5,
            1.0,
            3.0,
        ),
        "level_switch_on_threshold": resolve_float_fn(startup.get("level_switch_on_threshold"), 0.5, 0.0, 1.0),
        "startup_clean_level_retry_attempts": resolve_int_fn(
            startup.get("clean_level_retry_attempts"),
            6,
            0,
        ),
        "startup_clean_level_retry_delay_sec": resolve_float_fn(
            startup.get("clean_level_retry_delay_sec"),
            1.0,
            0.0,
            30.0,
        ),
        "sensor_mode_stabilization_time_sec": resolve_int_fn(
            startup.get("sensor_mode_stabilization_time_sec"),
            60,
            0,
        ),
        "sensor_mode_telemetry_grace_sec": resolve_int_fn(
            startup.get("sensor_mode_telemetry_grace_sec"),
            90,
            0,
        ),
        "clean_max_labels": normalize_labels_fn(startup.get("clean_max_sensor_labels"), ("level_clean_max", "clean_max")),
        "clean_min_labels": normalize_labels_fn(startup.get("clean_min_sensor_labels"), ("level_clean_min", "clean_min")),
        "solution_max_labels": normalize_labels_fn(startup.get("solution_max_sensor_labels"), ("level_solution_max", "solution_max")),
        "solution_min_labels": normalize_labels_fn(
            startup.get("solution_min_sensor_labels"),
            ("level_solution_min", "solution_min"),
        ),
        "target_ph": target_ph,
        "target_ec": target_ec,
        "target_ec_prepare": target_ec_prepare,
        "nutrient_npk_ratio_pct": nutrient_npk_ratio_pct,
        "prepare_hard_bounds": prepare_hard_bounds,
        "prepare_absolute_tolerance": prepare_absolute_tolerance,
        "prepare_tolerance": {
            "ec_pct": resolve_float_fn(
                prepare_tolerance_cfg.get("ec_pct", fallback_prepare_tolerance_cfg.get("ec_pct")),
                25.0,
                0.1,
                100.0,
            ),
            "ph_pct": resolve_float_fn(
                prepare_tolerance_cfg.get("ph_pct", fallback_prepare_tolerance_cfg.get("ph_pct")),
                5.0,  # DEFAULT pH tolerance 5% → ±0.29 for target 5.75
                0.1,
                100.0,
            ),
        },
        "recovery_tolerance": {
            "ec_pct": resolve_float_fn(recovery_tolerance_cfg.get("ec_pct"), 10.0, 0.1, 100.0),
            "ph_pct": resolve_float_fn(recovery_tolerance_cfg.get("ph_pct"), 5.0, 0.1, 100.0),
        },
        "degraded_tolerance": {
            "ec_pct": resolve_float_fn(degraded_cfg.get("ec_pct"), 20.0, 0.1, 100.0),
            "ph_pct": resolve_float_fn(degraded_cfg.get("ph_pct"), 10.0, 0.1, 100.0),
        },
        "commands": {
            "clean_fill_start": clean_fill_start,
            "clean_fill_stop": clean_fill_stop,
            "solution_fill_start": solution_fill_start,
            "solution_fill_stop": solution_fill_stop,
            "prepare_recirculation_start": prepare_recirculation_start,
            "prepare_recirculation_stop": prepare_recirculation_stop,
            "irrigation_recovery_start": irrigation_recovery_start,
            "irrigation_recovery_stop": irrigation_recovery_stop,
        },
    }


__all__ = [
    "default_two_tank_command_plan",
    "normalize_command_plan",
    "resolve_two_tank_runtime_config",
]
