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

    targets_payload = (
        zone_targets
        if isinstance(zone_targets, dict)
        else (payload.get("targets") if isinstance(payload.get("targets"), dict) else {})
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

    recovery_max_attempts_raw = recovery_cfg.get("max_attempts")
    if recovery_max_attempts_raw is None:
        recovery_max_attempts_raw = recovery_cfg.get("max_continue_attempts")

    return {
        "required_node_types": required_node_types,
        "clean_fill_timeout_sec": resolve_int_fn(startup.get("clean_fill_timeout_sec"), 1200, 30),
        "solution_fill_timeout_sec": resolve_int_fn(startup.get("solution_fill_timeout_sec"), 1800, 30),
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
