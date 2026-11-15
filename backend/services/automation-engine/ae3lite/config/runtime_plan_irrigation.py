"""runtime plan irrigation: one cohesive policy."""

from __future__ import annotations

from typing import Any, Mapping

from ae3lite.config.runtime_plan_values_policy import (
    _irrigation_subsystem,
    _optional_bool,
    _optional_float,
    _require_int,
    _resolve_bounded_int,
    _resolve_float,
    _to_mapping,
)


def _build_irrigation_execution(snapshot: Any) -> dict[str, Any]:
    irrigation = _to_mapping(_to_mapping(getattr(snapshot, "targets", None)).get("irrigation"))
    # Canonical path after merge_task_execution: targets.irrigation.execution.*.
    # Top-level irrigation.* kept as fallback for legacy snapshots.
    execution = _to_mapping(irrigation.get("execution"))

    def _exec_or_top(key: str, default: Any = None) -> Any:
        if key in execution:
            return execution.get(key)
        if key in irrigation:
            return irrigation.get(key)
        return default

    corr_during = bool(_exec_or_top("correction_during_irrigation", True))
    ec_component = str(_exec_or_top("irrigation_ec_component") or "none").strip().lower()
    if ec_component not in {"none", "calcium", "npk"}:
        ec_component = "none"
    if irrigation.get("duration_sec") is None or irrigation.get("interval_sec") is None:
        # Для путей планирования `cycle_start` irrigation-target'ы могут отсутствовать.
        # Они обязательны только при реальном выполнении задач `irrigation_start`.
        return {
            "duration_sec": None,
            "interval_sec": None,
            "correction_during_irrigation": corr_during,
            "irrigation_ec_component": ec_component,
            "correction_slack_sec": _resolve_bounded_int(
                irrigation.get("correction_slack_sec"),
                900 if corr_during else 0,
                0,
                7200,
            ),
            "stage_timeout_sec": (
                _resolve_bounded_int(irrigation.get("stage_timeout_sec"), 3600, 1, 86400)
                if irrigation.get("stage_timeout_sec") is not None
                else None
            ),
        }
    duration_sec = _require_int(
        irrigation.get("duration_sec"),
        path="targets.irrigation.duration_sec",
        minimum=1,
        maximum=3600,
    )
    correction_slack_sec = _resolve_bounded_int(
        irrigation.get("correction_slack_sec"),
        900 if corr_during else 0,
        0,
        7200,
    )
    stage_timeout_sec = None
    if irrigation.get("stage_timeout_sec") is not None:
        stage_timeout_sec = _resolve_bounded_int(
            irrigation.get("stage_timeout_sec"),
            max(1, duration_sec + correction_slack_sec),
            1,
            86400,
        )
    return {
        "duration_sec": duration_sec,
        "interval_sec": _require_int(
            irrigation.get("interval_sec"),
            path="targets.irrigation.interval_sec",
            minimum=1,
            maximum=86400,
        ),
        "correction_during_irrigation": corr_during,
        "irrigation_ec_component": ec_component,
        "correction_slack_sec": correction_slack_sec,
        "stage_timeout_sec": stage_timeout_sec,
    }


def _build_irrigation_decision(snapshot: Any) -> dict[str, Any]:
    subsystem = _irrigation_subsystem(snapshot)
    decision = _to_mapping(subsystem.get("decision"))
    strategy = str(decision.get("strategy") or "task").strip().lower() or "task"
    config = _to_mapping(decision.get("config"))
    return {
        "strategy": strategy,
        "config": {
            "lookback_sec": _resolve_bounded_int(config.get("lookback_sec"), 1800, 60, 86400),
            "min_samples": _resolve_bounded_int(config.get("min_samples"), 3, 1, 100),
            "stale_after_sec": _resolve_bounded_int(config.get("stale_after_sec"), 600, 30, 86400),
            "hysteresis_pct": _resolve_float(config.get("hysteresis_pct"), 2.0, 0.0, 100.0),
            "spread_alert_threshold_pct": _resolve_float(
                config.get("spread_alert_threshold_pct"),
                12.0,
                0.0,
                100.0,
            ),
        },
    }


def _build_irrigation_recovery(snapshot: Any) -> dict[str, Any]:
    """Deprecated chemistry-recovery block.

    Stages are gone; ``enabled`` is always False (fail-closed). Remaining
    fields still drive solution_min → setup replay and auto-replay after setup.
    """
    subsystem = _irrigation_subsystem(snapshot)
    recovery = _to_mapping(subsystem.get("recovery"))
    return {
        "enabled": False,
        "max_continue_attempts": _resolve_bounded_int(recovery.get("max_continue_attempts"), 5, 1, 30),
        "timeout_sec": _resolve_bounded_int(recovery.get("timeout_sec"), 600, 30, 86400),
        "auto_replay_after_setup": bool(recovery.get("auto_replay_after_setup", False)),
        "max_setup_replays": _resolve_bounded_int(recovery.get("max_setup_replays"), 1, 0, 10),
    }


def _build_fail_safe_guards(execution: Mapping[str, Any]) -> dict[str, Any]:
    guards = _to_mapping(execution.get("fail_safe_guards"))
    return {
        # Deprecated: clean_fill does not apply this min-level delay anymore;
        # runtime keeps it only as a mirror for firmware/config compatibility.
        "clean_fill_min_check_delay_ms": _resolve_bounded_int(
            guards.get("clean_fill_min_check_delay_ms"),
            5000,
            0,
            3600000,
        ),
        "solution_fill_clean_min_check_delay_ms": _resolve_bounded_int(
            guards.get("solution_fill_clean_min_check_delay_ms"),
            5000,
            0,
            3600000,
        ),
        "solution_fill_solution_min_check_delay_ms": _resolve_bounded_int(
            guards.get("solution_fill_solution_min_check_delay_ms"),
            60000,
            0,
            3600000,
        ),
        "solution_topup_clean_min_check_delay_ms": _resolve_bounded_int(
            guards.get("solution_topup_clean_min_check_delay_ms"),
            _resolve_bounded_int(guards.get("solution_fill_clean_min_check_delay_ms"), 5000, 0, 3600000),
            0,
            3600000,
        ),
        "solution_topup_solution_min_check_delay_ms": _resolve_bounded_int(
            guards.get("solution_topup_solution_min_check_delay_ms"),
            _resolve_bounded_int(guards.get("solution_fill_solution_min_check_delay_ms"), 60000, 0, 3600000),
            0,
            3600000,
        ),
        "recirculation_stop_on_solution_min": bool(guards.get("recirculation_stop_on_solution_min", True)),
        "irrigation_stop_on_solution_min": bool(guards.get("irrigation_stop_on_solution_min", True)),
        "estop_debounce_ms": _resolve_bounded_int(
            guards.get("estop_debounce_ms"),
            80,
            20,
            5000,
        ),
    }


def _build_irrigation_safety(snapshot: Any, execution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    subsystem = _irrigation_subsystem(snapshot)
    safety = _to_mapping(subsystem.get("safety"))
    fail_safe_guards = _build_fail_safe_guards(execution or {})
    return {
        "stop_on_solution_min": bool(
            safety.get(
                "stop_on_solution_min",
                fail_safe_guards.get("irrigation_stop_on_solution_min", True),
            )
        ),
    }


def _build_solution_health(snapshot: Any) -> dict[str, Any]:
    """min/max — колонки фазы в phase_targets, не target и не extensions.targets."""
    phase_targets = _to_mapping(getattr(snapshot, "phase_targets", None))
    solution = _to_mapping(phase_targets.get("solution_temp"))
    if not solution:
        solution = _to_mapping(_to_mapping(getattr(snapshot, "targets", None)).get("solution_temp"))
    extensions = _to_mapping(phase_targets.get("extensions"))
    health = _to_mapping(extensions.get("solution_health"))
    return {
        "required": _optional_bool(health.get("required"), False),
        "min_c": _optional_float(solution.get("min")),
        "max_c": _optional_float(solution.get("max")),
        "warn_c": _optional_float(health.get("warn_c")),
        "stop_c": _optional_float(health.get("stop_c")),
        "breach_hold_sec": _resolve_bounded_int(health.get("breach_hold_sec"), 600, 60, 86400),
        "max_temp_skip_pause_sec": _resolve_bounded_int(health.get("max_temp_skip_pause_sec"), 5400, 60, 86400),
    }
