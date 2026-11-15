"""runtime plan assembly: one cohesive policy."""

from __future__ import annotations

from typing import Any, Mapping

from ae3lite.config.runtime_plan_commands import (
    _apply_stage_timeout_guard,
    _assert_required_command_contract,
    _assert_run_pump_duration_within_hl_ceiling,
    _irrigation_start_duration_ms,
    _normalize_command_plan,
    default_two_tank_command_plan,
)
from ae3lite.config.runtime_plan_correction import (
    _build_correction_cfg,
    _build_prepare_tolerance_cfg,
    _build_recirc_dilute_cfg,
)
from ae3lite.config.runtime_plan_irrigation import (
    _build_fail_safe_guards,
    _build_irrigation_decision,
    _build_irrigation_execution,
    _build_irrigation_recovery,
    _build_irrigation_safety,
    _build_solution_health,
)
from ae3lite.config.runtime_plan_targets import (
    _build_day_night_config,
    _build_soil_moisture_target,
    _compute_component_share,
    _resolve_phase_target,
    _resolve_phase_target_bound,
)
from ae3lite.config.runtime_plan_validation import (
    _require_pid_configs,
    _require_zone_correction_contract,
    _validate_prepare_recirculation_timing,
)
from ae3lite.config.runtime_plan_values_policy import (
    _first_non_null,
    _merge_recursive,
    _normalize_required_node_types,
    _require_float,
    _require_int,
    _require_labels,
    _resolve_bounded_int,
    _resolve_float,
    _to_mapping,
)
from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError
from ae3lite.domain.services.phase_utils import normalize_phase_key as _normalize_phase_key


def assemble_pack_runtime(snapshot: Any, pack: Any) -> dict[str, Any]:
    """Собирает runtime dict из срезов, которые требует пакет topology.

    Гидравлические профили ``two_tank`` и ``single_tank`` считают общий
    two-tank dict, затем оставляют только ``pack.command_plan_keys``.
    """
    profile = str(getattr(pack, "plan_profile", "") or "")
    if profile not in {"two_tank", "single_tank"}:
        raise PlannerConfigurationError(f"assemble_pack_runtime не поддерживает plan_profile={profile or 'empty'}")
    runtime = resolve_two_tank_runtime(snapshot)
    allowed = getattr(pack, "command_plan_keys", None)
    if allowed:
        specs = runtime.get("command_specs")
        if isinstance(specs, dict):
            runtime["command_specs"] = {name: steps for name, steps in specs.items() if name in allowed}
    return runtime


def resolve_two_tank_runtime_plan(snapshot: Any) -> Any:
    """Build and validate the typed `RuntimePlan` for a snapshot."""
    # Local import avoids a circular import at module load time
    # (config.loader → ae3lite.config → metrics → various domain services).
    from ae3lite.config.loader import load_runtime_plan

    runtime_dict = resolve_two_tank_runtime(snapshot)
    zone_id = int(getattr(snapshot, "zone_id", 0) or 0) or None
    return load_runtime_plan(
        runtime_dict,
        zone_id=zone_id,
        namespace="runtime.plan:two_tank",
    )


def resolve_two_tank_runtime(snapshot: Any) -> dict[str, Any]:
    execution = _to_mapping(snapshot.diagnostics_execution)
    commands_cfg = _to_mapping(execution.get("two_tank_commands"))
    zone_id = int(getattr(snapshot, "zone_id", 0) or 0)
    resolved_cfg = getattr(snapshot, "correction_config", None)
    if not isinstance(resolved_cfg, Mapping) or not resolved_cfg:
        raise PlannerConfigurationError(
            f"У зоны {zone_id} отсутствует correction_config; критические параметры дозирования переведены в fail-closed режим",
            code=ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
        )
    resolved_base_cfg = _to_mapping(resolved_cfg.get("base"))
    resolved_phases_cfg = _to_mapping(resolved_cfg.get("phases"))
    if not resolved_base_cfg and not resolved_phases_cfg:
        raise PlannerConfigurationError(
            f"У зоны {zone_id} пустой correction_config(base/phases); критические параметры дозирования переведены в fail-closed режим",
            code=ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
        )
    _require_pid_configs(snapshot=snapshot, zone_id=zone_id)
    resolved_pump_calibration_cfg = _to_mapping(resolved_cfg.get("pump_calibration"))
    solution_fill_cfg = _merge_recursive(resolved_base_cfg, _to_mapping(resolved_phases_cfg.get("solution_fill")))
    tank_recirc_cfg = _merge_recursive(resolved_base_cfg, _to_mapping(resolved_phases_cfg.get("tank_recirc")))
    irrigation_cfg = _merge_recursive(resolved_base_cfg, _to_mapping(resolved_phases_cfg.get("irrigation")))
    _require_zone_correction_contract(zone_id=zone_id, config=resolved_base_cfg, config_name="base")
    _require_zone_correction_contract(zone_id=zone_id, config=solution_fill_cfg, config_name="phases.solution_fill")
    _require_zone_correction_contract(zone_id=zone_id, config=tank_recirc_cfg, config_name="phases.tank_recirc")
    _require_zone_correction_contract(zone_id=zone_id, config=irrigation_cfg, config_name="phases.irrigation")
    active_phase_key = _normalize_phase_key(getattr(snapshot, "workflow_phase", None))
    active_phase_map = {
        "solution_fill": solution_fill_cfg,
        "tank_recirc": tank_recirc_cfg,
        "irrigation": irrigation_cfg,
    }
    if active_phase_key in active_phase_map:
        active_phase_cfg = active_phase_map[active_phase_key]
    elif active_phase_key in {"generic", "idle", "ready", ""}:
        active_phase_cfg = solution_fill_cfg if solution_fill_cfg else resolved_base_cfg
    else:
        raise PlannerConfigurationError(
            f"У зоны {zone_id} неподдерживаемый workflow_phase={active_phase_key!r} для two_tank runtime",
            code=ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
        )

    fill_runtime_cfg = _to_mapping(solution_fill_cfg.get("runtime"))
    fill_timing_cfg = _to_mapping(solution_fill_cfg.get("timing"))
    fill_retry_cfg = _to_mapping(solution_fill_cfg.get("retry"))
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
            f"Для зоны {zone_id} обязательно correction_config.base/phases.solution_fill.runtime.required_node_type"
        )
    target_ph = _resolve_phase_target(snapshot=snapshot, zone_id=zone_id, key="ph")
    target_ec = _resolve_phase_target(snapshot=snapshot, zone_id=zone_id, key="ec")
    # Legacy prepare-share fields kept for RuntimePlan loader parity only.
    # Prepare EC owner is water-baseline + cumulative T_* (see nutrient_pipeline).
    # Fill phase may carry calcium-only ratios; T_* / baseline math needs the FULL
    # recipe ratios from tank_recirc (Ca/Mg/NPK/Micro). Otherwise T_ca collapses
    # to T_full and dilute-on-overshoot never triggers on a Ca-step seed.
    ratios_for_share = _to_mapping(solution_fill_cfg.get("ec_component_ratios")) or _to_mapping(
        resolved_base_cfg.get("ec_component_ratios")
    )
    full_component_ratios = (
        _to_mapping(tank_recirc_cfg.get("ec_component_ratios"))
        or _to_mapping(resolved_base_cfg.get("ec_component_ratios"))
        or ratios_for_share
    )
    calcium_share = _compute_component_share(
        full_component_ratios or ratios_for_share,
        component="calcium",
    )
    # Deprecated alias: historically NPK share; now calcium share for fill T_ca pre-estimate.
    npk_ec_share = calcium_share
    target_ec_prepare = round(target_ec * calcium_share, 4)
    day_night_cfg = _build_day_night_config(snapshot)
    recirc_dilute_cfg = _build_recirc_dilute_cfg(
        tank_recirc_cfg=tank_recirc_cfg,
        base_cfg=resolved_base_cfg,
    )
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
        "prepare_recirculation_correction_slack_sec": _require_int(
            recirc_retry_cfg.get("prepare_recirculation_correction_slack_sec"),
            path="correction_config.base/phases.tank_recirc.retry.prepare_recirculation_correction_slack_sec",
            minimum=0,
            maximum=7200,
        ),
        "solution_fill_correction_slack_sec": _resolve_bounded_int(
            fill_retry_cfg.get("solution_fill_correction_slack_sec"),
            900,
            0,
            7200,
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
        "solution_topup_enabled": bool(
            _to_mapping(execution.get("startup")).get(
                "solution_topup_enabled",
                _to_mapping(execution.get("fail_safe_guards")).get("solution_topup_enabled", True),
            )
        ),
        "solution_topup_timeout_sec": _resolve_bounded_int(
            _to_mapping(execution.get("startup")).get("solution_topup_timeout_sec"),
            _require_int(
                fill_runtime_cfg.get("solution_fill_timeout_sec"),
                path="correction_config.base/phases.solution_fill.runtime.solution_fill_timeout_sec",
                minimum=30,
            ),
            30,
            86400,
        ),
        "solution_topup_cooldown_sec": _resolve_bounded_int(
            _to_mapping(execution.get("startup")).get("solution_topup_cooldown_sec"),
            300,
            0,
            86400,
        ),
        "solution_change_enabled": _resolve_solution_change_enabled(snapshot=snapshot, execution=execution),
        "solution_drain_timeout_sec": _resolve_bounded_int(
            _to_mapping(execution.get("startup")).get("solution_drain_timeout_sec"),
            _resolve_bounded_int(
                _to_mapping(execution.get("startup")).get("solution_fill_timeout_sec"),
                900,
                30,
                86400,
            ),
            30,
            86400,
        ),
        "solution_change_operator_confirm_timeout_sec": _resolve_bounded_int(
            _to_mapping(execution.get("startup")).get("solution_change_operator_confirm_timeout_sec"),
            3600,
            60,
            86400,
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
        "irr_state_wait_timeout_sec": _resolve_float(
            _to_mapping(execution.get("startup")).get("irr_state_wait_timeout_sec"),
            default=5.0,
            minimum=0.0,
            maximum=30.0,
        ),
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
        "target_ph_min": _resolve_phase_target_bound(snapshot=snapshot, key="ph", bound="min", fallback=target_ph),
        "target_ph_max": _resolve_phase_target_bound(snapshot=snapshot, key="ph", bound="max", fallback=target_ph),
        "target_ec_min": _resolve_phase_target_bound(snapshot=snapshot, key="ec", bound="min", fallback=target_ec),
        "target_ec_max": _resolve_phase_target_bound(snapshot=snapshot, key="ec", bound="max", fallback=target_ec),
        # Per-phase EC: prepare owner = water baseline + cumulative T_* (runtime capture).
        # target_ec_prepare / npk_ec_share — deprecated aliases (pre-baseline calcium share).
        "target_ec_prepare": target_ec_prepare,
        "target_ec_prepare_min": round(
            _resolve_phase_target_bound(snapshot=snapshot, key="ec", bound="min", fallback=target_ec) * calcium_share, 4
        ),
        "target_ec_prepare_max": round(
            _resolve_phase_target_bound(snapshot=snapshot, key="ec", bound="max", fallback=target_ec) * calcium_share, 4
        ),
        "npk_ec_share": npk_ec_share,
        "ec_component_ratios": dict(full_component_ratios),
        "recirc": recirc_dilute_cfg,
        "day_night_enabled": day_night_cfg["enabled"],
        "day_night_config": day_night_cfg,
        "prepare_tolerance": dict(default_prepare_tolerance),
        "prepare_tolerance_by_phase": prepare_tolerance_by_phase,
        "pid_state": _to_mapping(snapshot.pid_state),
        "pid_configs": _to_mapping(snapshot.pid_configs),
        "process_calibrations": _to_mapping(snapshot.process_calibrations),
        # Конфиг коррекции: каналы дозирования, тайминги, чувствительность.
        # Ключ `actuators` заполняется позже в CycleStartPlanner после resolve actuator'ов.
        "correction": dict(default_correction_cfg),
        "correction_by_phase": correction_by_phase,
        "command_specs": {},
        "fail_safe_guards": _build_fail_safe_guards(execution),
        "irrigation_execution": _build_irrigation_execution(snapshot),
        "irrigation_decision": _build_irrigation_decision(snapshot),
        "irrigation_recovery": _build_irrigation_recovery(snapshot),
        "irrigation_safety": _build_irrigation_safety(snapshot, execution),
        "soil_moisture_target": _build_soil_moisture_target(snapshot),
        "solution_health": _build_solution_health(snapshot),
    }
    _validate_prepare_recirculation_timing(runtime)

    irrigation_duration_ms = _irrigation_start_duration_ms(runtime.get("irrigation_execution"))
    for plan_name in (
        "irrigation_start",
        "irrigation_pump_stop",
        "irrigation_stop",
        "clean_fill_start",
        "clean_fill_stop",
        "solution_fill_start",
        "solution_fill_stop",
        "prepare_recirculation_start",
        "prepare_recirculation_stop",
        "recirc_dilute_start",
        "recirc_dilute_stop",
        "solution_drain_start",
        "solution_drain_stop",
    ):
        runtime["command_specs"][plan_name] = _normalize_command_plan(
            commands_cfg.get(plan_name),
            default_plan=default_two_tank_command_plan(
                plan_name,
                irrigation_duration_ms=irrigation_duration_ms,
            ),
            default_node_types=runtime["required_node_types"],
        )
        _assert_required_command_contract(plan_name=plan_name, normalized_plan=runtime["command_specs"][plan_name])
        _assert_run_pump_duration_within_hl_ceiling(
            plan_name=plan_name,
            normalized_plan=runtime["command_specs"][plan_name],
        )
        _apply_stage_timeout_guard(
            plan_name=plan_name, normalized_plan=runtime["command_specs"][plan_name], runtime=runtime
        )
    return runtime


def _resolve_solution_change_enabled(*, snapshot: Any, execution: Mapping[str, Any]) -> bool:
    startup = _to_mapping(execution.get("startup"))
    if startup.get("solution_change_enabled") is not None:
        return bool(startup.get("solution_change_enabled"))
    targets = getattr(snapshot, "targets", None)
    if not isinstance(targets, Mapping):
        return False
    solution_change = targets.get("solution_change")
    if isinstance(solution_change, Mapping) and solution_change.get("enabled") is not None:
        return bool(solution_change.get("enabled"))
    extensions = targets.get("extensions")
    if isinstance(extensions, Mapping):
        subsystems = extensions.get("subsystems")
        if isinstance(subsystems, Mapping):
            node = subsystems.get("solution_change")
            if isinstance(node, Mapping) and node.get("enabled") is not None:
                return bool(node.get("enabled"))
    return False
