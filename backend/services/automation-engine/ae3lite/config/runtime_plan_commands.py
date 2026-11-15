"""runtime plan commands: one cohesive policy."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ae3lite.config.runtime_plan_values import (
    _REQUIRED_TWO_TANK_PLAN_CHANNELS,
    _STAGE_TIMEOUT_GUARDS,
    HL_RUN_PUMP_MAX_DURATION_MS,
)
from ae3lite.config.runtime_plan_values_policy import _normalize_node_types
from ae3lite.domain.errors import PlannerConfigurationError


def default_two_tank_command_plan(
    plan_name: str,
    *,
    irrigation_duration_ms: int | None = None,
) -> list[dict[str, Any]]:
    requested_ms = int(irrigation_duration_ms or 120_000)
    if plan_name == "irrigation_start" and requested_ms > HL_RUN_PUMP_MAX_DURATION_MS:
        raise PlannerConfigurationError(
            "irrigation_start run_pump duration_ms="
            f"{requested_ms} exceeds history-logger ceiling {HL_RUN_PUMP_MAX_DURATION_MS}; "
            "refusing to open valves before an INVALID pump command"
        )
    pump_duration_ms = max(1000, min(HL_RUN_PUMP_MAX_DURATION_MS, requested_ms))
    defaults: dict[str, list[dict[str, Any]]] = {
        "irrigation_start": [
            {"channel": "valve_solution_supply", "cmd": "set_relay", "params": {"state": True}},
            {"channel": "valve_irrigation", "cmd": "set_relay", "params": {"state": True}},
            {"channel": "pump_main", "cmd": "run_pump", "params": {"duration_ms": pump_duration_ms}},
        ],
        "irrigation_pump_stop": [
            {"channel": "pump_main", "cmd": "set_relay", "params": {"state": False}},
        ],
        "irrigation_stop": [
            {"channel": "pump_main", "cmd": "set_relay", "params": {"state": False}},
            {"channel": "valve_irrigation", "cmd": "set_relay", "params": {"state": False}},
            {"channel": "valve_solution_supply", "cmd": "set_relay", "params": {"state": False}},
        ],
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
        "recirc_dilute_start": [
            {"channel": "valve_clean_supply", "cmd": "set_relay", "params": {"state": True}},
        ],
        "recirc_dilute_stop": [
            {"channel": "valve_clean_supply", "cmd": "set_relay", "params": {"state": False}},
        ],
        "solution_drain_start": [{"channel": "valve_drain", "cmd": "set_relay", "params": {"state": True}}],
        "solution_drain_stop": [{"channel": "valve_drain", "cmd": "set_relay", "params": {"state": False}}],
    }
    return [dict(item) for item in defaults.get(plan_name, ())]


def _irrigation_start_duration_ms(irrigation_execution: Any) -> int:
    """Duration for default irrigation_start run_pump; matches planner fallback 120s."""
    duration_sec = 120
    if isinstance(irrigation_execution, Mapping):
        raw = irrigation_execution.get("duration_sec")
        try:
            duration_sec = max(1, min(3600, int(raw)))
        except (TypeError, ValueError):
            duration_sec = 120
    duration_ms = max(1000, int(duration_sec) * 1000)
    if duration_ms > HL_RUN_PUMP_MAX_DURATION_MS:
        raise PlannerConfigurationError(
            "irrigation_start run_pump duration_ms="
            f"{duration_ms} exceeds history-logger ceiling {HL_RUN_PUMP_MAX_DURATION_MS}; "
            "refusing to open valves before an INVALID pump command"
        )
    return duration_ms


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
                "complete_on_ack": bool(entry.get("complete_on_ack")),
            }
        )
    return normalized


def _apply_stage_timeout_guard(
    *,
    plan_name: str,
    normalized_plan: list[dict[str, Any]],
    runtime: Mapping[str, Any],
) -> None:
    guard = _STAGE_TIMEOUT_GUARDS.get(plan_name)
    if not guard:
        return

    stage_name, timeout_key = guard
    timeout_sec = int(runtime.get(timeout_key) or 0)
    if timeout_sec <= 0:
        return

    for entry in normalized_plan:
        if str(entry.get("channel") or "").strip().lower() != "pump_main":
            continue
        params = dict(entry.get("params") or {})
        params["timeout_ms"] = timeout_sec * 1000
        params["stage"] = stage_name
        entry["params"] = params
        entry["complete_on_ack"] = True
        return


def _assert_required_command_contract(*, plan_name: str, normalized_plan: Sequence[Mapping[str, Any]]) -> None:
    required_channels = _REQUIRED_TWO_TANK_PLAN_CHANNELS.get(plan_name)
    if not required_channels:
        return

    present_channels = {
        str(entry.get("channel") or "").strip().lower() for entry in normalized_plan if isinstance(entry, Mapping)
    }
    missing_channels = [channel for channel in required_channels if channel not in present_channels]
    if missing_channels:
        raise PlannerConfigurationError(
            f"two_tank command plan {plan_name} не содержит обязательные каналы: {', '.join(missing_channels)}"
        )


def _assert_run_pump_duration_within_hl_ceiling(
    *,
    plan_name: str,
    normalized_plan: Sequence[Mapping[str, Any]],
) -> None:
    """Fail-closed before valve commands if run_pump exceeds HL duration sanity ceiling."""
    for entry in normalized_plan:
        if not isinstance(entry, Mapping):
            continue
        if str(entry.get("cmd") or "").strip().lower() != "run_pump":
            continue
        params = entry.get("params")
        params = params if isinstance(params, Mapping) else {}
        try:
            duration_ms = int(params.get("duration_ms") or 0)
        except (TypeError, ValueError):
            continue
        if duration_ms > HL_RUN_PUMP_MAX_DURATION_MS:
            raise PlannerConfigurationError(
                f"two_tank command plan {plan_name} run_pump duration_ms={duration_ms} "
                f"exceeds history-logger ceiling {HL_RUN_PUMP_MAX_DURATION_MS}; "
                "refusing to open valves before an INVALID pump command"
            )
