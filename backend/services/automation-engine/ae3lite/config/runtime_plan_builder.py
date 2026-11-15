"""Compatibility entry points for config/runtime_plan_builder.py; implementations have explicit policy owners."""

from __future__ import annotations
from ae3lite.config.runtime_plan_assembly import (
    assemble_pack_runtime,
    resolve_two_tank_runtime_plan,
    resolve_two_tank_runtime,
    _resolve_solution_change_enabled,
)
from ae3lite.config.runtime_plan_commands import (
    default_two_tank_command_plan,
    _irrigation_start_duration_ms,
    _normalize_command_plan,
    _apply_stage_timeout_guard,
    _assert_required_command_contract,
    _assert_run_pump_duration_within_hl_ceiling,
)
from ae3lite.config.runtime_plan_validation import (
    _require_pid_configs,
    _require_zone_correction_contract,
    _collect_missing_paths,
    _validate_prepare_recirculation_timing,
    _tank_recirc_observe_window_sec,
)
from ae3lite.config.runtime_plan_values_policy import (
    _normalize_node_types,
    _normalize_required_node_types,
    _normalize_labels,
    _require_labels,
    _resolve_int,
    _resolve_bounded_int,
    _resolve_float,
    _require_int,
    _require_float,
    _require_str,
    _normalize_controllers,
    _normalize_component_policy,
    _to_mapping,
    _merge_recursive,
    _first_non_null,
    _optional_float,
    _optional_bool,
    _irrigation_subsystem,
)
from ae3lite.config.runtime_plan_targets import (
    _compute_prepare_ec_share,
    _compute_component_share,
    _build_day_night_config,
    _resolve_phase_target,
    _resolve_phase_target_bound,
    _build_soil_moisture_target,
)
from ae3lite.config.runtime_plan_irrigation import (
    _build_irrigation_execution,
    _build_irrigation_decision,
    _build_irrigation_recovery,
    _build_fail_safe_guards,
    _build_irrigation_safety,
    _build_solution_health,
)
from ae3lite.config.runtime_plan_correction import (
    _build_recirc_dilute_cfg,
    _build_correction_cfg,
    _build_prepare_tolerance_cfg,
)
from ae3lite.config.runtime_plan_values import (
    _MAX_CORRECTION_ATTEMPTS,
    HL_RUN_PUMP_MAX_DURATION_MS,
    _REQUIRED_TWO_TANK_PLAN_CHANNELS,
    _STAGE_TIMEOUT_GUARDS,
    _REQUIRED_ZONE_CORRECTION_TEMPLATE,
)

__all__ = [
    "assemble_pack_runtime",
    "default_two_tank_command_plan",
    "resolve_two_tank_runtime",
    "resolve_two_tank_runtime_plan",
]
