"""Runtime constants and feature flags for scheduler executor."""

from __future__ import annotations

import os
from typing import Any


def _runtime_scheduler_constant(name: str, default: Any) -> Any:
    try:
        import scheduler_task_executor as scheduler_public_api  # local import to avoid circular dependency
    except Exception:
        return default
    return getattr(scheduler_public_api, name, default)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


CYCLE_START_REQUIRED_NODE_TYPES = tuple(
    item.strip()
    for item in os.getenv(
        "AE_CYCLE_START_REQUIRED_NODE_TYPES",
        "irrig,climate,light",
    ).split(",")
    if item.strip()
)
CLEAN_TANK_FULL_THRESHOLD = max(0.0, min(1.0, _env_float("AE_CLEAN_TANK_FULL_THRESHOLD", 0.95)))
REFILL_CHECK_DELAY_SEC = max(10, _env_int("AE_REFILL_CHECK_DELAY_SEC", 60))
REFILL_TIMEOUT_SEC = max(30, _env_int("AE_REFILL_TIMEOUT_SEC", 600))
REFILL_COMMAND_DURATION_SEC = max(1, _env_int("AE_REFILL_COMMAND_DURATION_SEC", 30))
TASK_EXECUTE_CLOSED_LOOP_ENFORCE = _env_bool("AE_TASK_EXECUTE_CLOSED_LOOP", True)
TASK_EXECUTE_CLOSED_LOOP_TIMEOUT_SEC = max(1.0, _env_float("AE_TASK_EXECUTE_CLOSED_LOOP_TIMEOUT_SEC", 60.0))
TELEMETRY_FRESHNESS_ENFORCE = _env_bool("AE_TELEMETRY_FRESHNESS_ENFORCE", True)
TELEMETRY_FRESHNESS_MAX_AGE_SEC = max(30, _env_int("AE_TELEMETRY_FRESHNESS_MAX_AGE_SEC", 300))
AUTO_LOGIC_DECISION_V1 = _env_bool("AUTO_LOGIC_DECISION_V1", True)
AUTO_LOGIC_TANK_STATE_MACHINE_V1 = _env_bool("AUTO_LOGIC_TANK_STATE_MACHINE_V1", True)
AE_LEGACY_WORKFLOW_DEFAULT_ENABLED = _env_bool("AE_LEGACY_WORKFLOW_DEFAULT_ENABLED", False)
AUTO_LOGIC_CLIMATE_GUARDS_V1 = _env_bool("AUTO_LOGIC_CLIMATE_GUARDS_V1", True)
AUTO_LOGIC_NEW_SENSORS_V1 = _env_bool("AUTO_LOGIC_NEW_SENSORS_V1", True)
AUTO_LOGIC_EXTENDED_OUTCOME_V1 = _env_bool("AUTO_LOGIC_EXTENDED_OUTCOME_V1", True)
AE_TWOTANK_SAFETY_GUARDS_ENABLED = _env_bool("AE_TWOTANK_SAFETY_GUARDS_ENABLED", True)


TWO_TANK_TOPOLOGIES = {"two_tank_drip_substrate_trays", "two_tank"}
THREE_TANK_TOPOLOGIES = {
    "three_tank_drip_substrate_trays",
    "three_tank_substrate_trays",
    "three_tank",
}
CYCLE_START_WORKFLOWS = {"cycle_start", "refill_check"}


ERR_COMMAND_PUBLISH_FAILED = "command_publish_failed"
ERR_COMMAND_SEND_FAILED = "command_send_failed"
ERR_COMMAND_TIMEOUT = "command_timeout"
ERR_COMMAND_ERROR = "command_error"
ERR_COMMAND_INVALID = "command_invalid"
ERR_COMMAND_BUSY = "command_busy"
ERR_COMMAND_NO_EFFECT = "command_no_effect"
ERR_COMMAND_TRACKER_UNAVAILABLE = "command_tracker_unavailable"
ERR_COMMAND_EFFECT_NOT_CONFIRMED = "command_effect_not_confirmed"
ERR_MAPPING_NOT_FOUND = "mapping_not_found"
ERR_NO_ONLINE_NODES = "no_online_nodes"
ERR_CYCLE_REQUIRED_NODES_UNAVAILABLE = "cycle_start_required_nodes_unavailable"
ERR_CYCLE_TANK_LEVEL_UNAVAILABLE = "cycle_start_tank_level_unavailable"
ERR_CYCLE_TANK_LEVEL_STALE = "cycle_start_tank_level_stale"
ERR_CYCLE_REFILL_TIMEOUT = "cycle_start_refill_timeout"
ERR_CYCLE_REFILL_NODE_NOT_FOUND = "cycle_start_refill_node_not_found"
ERR_CYCLE_REFILL_COMMAND_FAILED = "cycle_start_refill_command_failed"
ERR_CYCLE_SELF_TASK_ENQUEUE_FAILED = "cycle_start_self_task_enqueue_failed"
ERR_CLEAN_TANK_NOT_FILLED_TIMEOUT = "clean_tank_not_filled_timeout"
ERR_SOLUTION_TANK_NOT_FILLED_TIMEOUT = "solution_tank_not_filled_timeout"
ERR_TWO_TANK_LEVEL_UNAVAILABLE = "two_tank_level_unavailable"
ERR_TWO_TANK_LEVEL_STALE = "two_tank_level_stale"
ERR_TWO_TANK_IRR_STATE_UNAVAILABLE = "two_tank_irr_state_unavailable"
ERR_TWO_TANK_IRR_STATE_STALE = "two_tank_irr_state_stale"
ERR_TWO_TANK_IRR_STATE_MISMATCH = "two_tank_irr_state_mismatch"
ERR_TWO_TANK_COMMAND_FAILED = "two_tank_command_failed"
ERR_TWO_TANK_ENQUEUE_FAILED = "two_tank_enqueue_failed"
ERR_TWO_TANK_CHANNEL_NOT_FOUND = "two_tank_channel_not_found"
ERR_PREPARE_NPK_PH_TARGET_NOT_REACHED = "prepare_npk_ph_target_not_reached"
ERR_IRRIGATION_RECOVERY_ATTEMPTS_EXCEEDED = "irrigation_recovery_attempts_exceeded"
ERR_SENSOR_STATE_INCONSISTENT = "sensor_state_inconsistent"
ERR_DIAGNOSTICS_SERVICE_UNAVAILABLE = "diagnostics_service_unavailable"
ERR_INVALID_PAYLOAD_MISSING_WORKFLOW = "invalid_payload_missing_workflow"
ERR_INVALID_PAYLOAD_CONTRACT_VERSION = "invalid_payload_contract_version"

TERMINAL_STATUS_ERROR_CODES = {
    "SEND_FAILED": ERR_COMMAND_SEND_FAILED,
    "TIMEOUT": ERR_COMMAND_TIMEOUT,
    "ERROR": ERR_COMMAND_ERROR,
    "INVALID": ERR_COMMAND_INVALID,
    "BUSY": ERR_COMMAND_BUSY,
    "NO_EFFECT": ERR_COMMAND_NO_EFFECT,
    "TRACKER_UNAVAILABLE": ERR_COMMAND_TRACKER_UNAVAILABLE,
    "__default__": ERR_COMMAND_EFFECT_NOT_CONFIRMED,
}

REASON_REQUIRED_NODES_CHECKED = "required_nodes_checked"
REASON_TANK_LEVEL_CHECKED = "tank_level_checked"
REASON_TANK_REFILL_REQUIRED = "tank_refill_required"
REASON_TANK_REFILL_STARTED = "tank_refill_started"
REASON_TANK_REFILL_IN_PROGRESS = "tank_refill_in_progress"
REASON_TANK_REFILL_COMPLETED = "tank_refill_completed"
REASON_TANK_REFILL_NOT_REQUIRED = "tank_refill_not_required"
REASON_CYCLE_BLOCKED_NODES_UNAVAILABLE = "cycle_start_blocked_nodes_unavailable"
REASON_CYCLE_TANK_LEVEL_UNAVAILABLE = "cycle_start_tank_level_unavailable"
REASON_CYCLE_TANK_LEVEL_STALE = "cycle_start_tank_level_stale"
REASON_CYCLE_REFILL_TIMEOUT = "cycle_start_refill_timeout"
REASON_CYCLE_REFILL_COMMAND_FAILED = "cycle_start_refill_command_failed"
REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED = "cycle_start_self_task_enqueue_failed"
REASON_CLEAN_FILL_STARTED = "clean_fill_started"
REASON_CLEAN_FILL_COMPLETED = "clean_fill_completed"
REASON_CLEAN_FILL_IN_PROGRESS = "clean_fill_in_progress"
REASON_CLEAN_FILL_TIMEOUT = "clean_fill_timeout"
REASON_CLEAN_FILL_RETRY_STARTED = "clean_fill_retry_started"
REASON_SOLUTION_FILL_STARTED = "solution_fill_started"
REASON_SOLUTION_FILL_COMPLETED = "solution_fill_completed"
REASON_SOLUTION_FILL_IN_PROGRESS = "solution_fill_in_progress"
REASON_SOLUTION_FILL_TIMEOUT = "solution_fill_timeout"
REASON_PREPARE_RECIRCULATION_STARTED = "prepare_recirculation_started"
REASON_PREPARE_TARGETS_REACHED = "prepare_targets_reached"
REASON_PREPARE_TARGETS_NOT_REACHED = "prepare_targets_not_reached"
REASON_IRRIGATION_RECOVERY_STARTED = "irrigation_recovery_started"
REASON_IRRIGATION_RECOVERY_RECOVERED = "irrigation_recovery_recovered"
REASON_IRRIGATION_RECOVERY_FAILED = "irrigation_recovery_failed"
REASON_IRRIGATION_RECOVERY_DEGRADED = "irrigation_recovery_degraded"
REASON_MANUAL_ACK_REQUIRED_AFTER_RETRIES = "manual_ack_required_after_retries"
REASON_IRRIGATION_CORRECTION_ATTEMPTS_EXHAUSTED_CONTINUE_IRRIGATION = (
    "irrigation_correction_attempts_exhausted_continue_irrigation"
)
REASON_ONLINE_CORRECTION_FAILED = "online_correction_failed"
REASON_TANK_TO_TANK_CORRECTION_STARTED = "tank_to_tank_correction_started"
REASON_SENSOR_STALE_DETECTED = "sensor_stale_detected"
REASON_SENSOR_LEVEL_UNAVAILABLE = "sensor_level_unavailable"
REASON_SENSOR_STATE_INCONSISTENT = "sensor_state_inconsistent"
REASON_IRR_STATE_UNAVAILABLE = "irr_state_unavailable"
REASON_IRR_STATE_STALE = "irr_state_stale"
REASON_IRR_STATE_MISMATCH = "irr_state_mismatch"
REASON_DIAGNOSTICS_SERVICE_UNAVAILABLE = "diagnostics_service_unavailable"
REASON_WIND_BLOCKED = "wind_blocked"
REASON_OUTSIDE_TEMP_BLOCKED = "outside_temp_blocked"
