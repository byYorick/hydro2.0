"""Unified resilience contract constants (S10 incremental consolidation)."""

from __future__ import annotations

import re

# Infra alert codes
INFRA_ZONE_BACKOFF_SKIP = "infra_zone_backoff_skip"
INFRA_ZONE_TARGETS_MISSING = "infra_zone_targets_missing"
INFRA_ZONE_DATA_UNAVAILABLE = "infra_zone_data_unavailable"
INFRA_ZONE_DEGRADED_MODE = "infra_zone_degraded_mode"
INFRA_ZONE_REQUIRED_NODES_OFFLINE = "infra_zone_required_nodes_offline"
INFRA_CONTROLLER_COMMAND_SKIPPED_CIRCUIT_OPEN = "infra_controller_command_skipped_circuit_open"
INFRA_CONTROLLER_COOLDOWN_SKIP = "infra_controller_cooldown_skip"
INFRA_CONTROLLER_FAILED = "infra_controller_failed"
INFRA_CORRECTION_FLAGS_MISSING = "infra_correction_flags_missing"
INFRA_CORRECTION_FLAGS_STALE = "infra_correction_flags_stale"
INFRA_CORRECTION_COMMAND_UNCONFIRMED = "infra_correction_command_unconfirmed"
INFRA_EC_BATCH_PARTIAL_FAILURE_COMPENSATION_ENQUEUE_FAILED = (
    "infra_ec_batch_partial_failure_compensation_enqueue_failed"
)
INFRA_CORRECTION_ANOMALY_BLOCK = "infra_correction_anomaly_block"
INFRA_IRRIGATION_PUMP_BLOCKED = "infra_irrigation_pump_blocked"
INFRA_ZONE_DELETION_CHECK_FAILED = "infra_zone_deletion_check_failed"
INFRA_PID_CONFIG_UPDATE_CHECK_FAILED = "infra_pid_config_update_check_failed"
INFRA_ZONE_EVENT_WRITE_FAILED = "infra_zone_event_write_failed"
INFRA_AUTOMATION_API_UNHANDLED_EXCEPTION = "infra_automation_api_unhandled_exception"
INFRA_AUTOMATION_API_HTTP_5XX = "infra_automation_api_http_5xx"
INFRA_AUTOMATION_BACKGROUND_TASK_CRASHED = "infra_automation_background_task_crashed"
INFRA_SCHEDULER_TASK_RECOVERY_PERSIST_FAILED = "infra_scheduler_task_recovery_persist_failed"
INFRA_SCHEDULER_TASK_RECOVERY_EVENT_FAILED = "infra_scheduler_task_recovery_event_failed"
INFRA_WORKFLOW_STATE_RECOVERY_ENQUEUE_FAILED = "infra_workflow_state_recovery_enqueue_failed"
INFRA_WORKFLOW_STATE_RECOVERY_ROW_FAILED = "infra_workflow_state_recovery_row_failed"
INFRA_ZONE_WORKFLOW_STATE_PERSIST_FAILED = "infra_zone_workflow_state_persist_failed"
INFRA_TASK_NO_ONLINE_NODES = "infra_task_no_online_nodes"
INFRA_UNKNOWN_ERROR = "infra_unknown_error"
INFRA_DIAGNOSTICS_SERVICE_UNAVAILABLE = "infra_diagnostics_service_unavailable"
INFRA_SCHEDULER_TASK_EVENT_PERSIST_FAILED = "infra_scheduler_task_event_persist_failed"
INFRA_CYCLE_START_NODES_UNAVAILABLE = "infra_cycle_start_nodes_unavailable"
INFRA_CYCLE_START_TANK_LEVEL_UNAVAILABLE = "infra_cycle_start_tank_level_unavailable"
INFRA_CYCLE_START_TANK_LEVEL_STALE = "infra_cycle_start_tank_level_stale"
INFRA_TANK_REFILL_TIMEOUT = "infra_tank_refill_timeout"
INFRA_CYCLE_START_REFILL_COMMAND_FAILED = "infra_cycle_start_refill_command_failed"
INFRA_CYCLE_START_ENQUEUE_FAILED = "infra_cycle_start_enqueue_failed"
INFRA_COMMAND_NODE_ZONE_VALIDATION_FAILED = "infra_command_node_zone_validation_failed"
INFRA_COMMAND_NODE_ZONE_MISMATCH = "infra_command_node_zone_mismatch"
INFRA_COMMAND_CHANNEL_TYPE_VALIDATION_FAILED = "infra_command_channel_type_validation_failed"
INFRA_COMMAND_INVALID_CHANNEL_TYPE = "infra_command_invalid_channel_type"
INFRA_COMMAND_PUBLISH_RESPONSE_DECODE_ERROR = "infra_command_publish_response_decode_error"
INFRA_COMMAND_SEND_FAILED = "infra_command_send_failed"
INFRA_COMMAND_TIMEOUT = "infra_command_timeout"
INFRA_COMMAND_TRACKER_UNAVAILABLE = "infra_command_tracker_unavailable"
INFRA_COMMAND_FAILED = "infra_command_failed"
INFRA_COMMAND_INVALID = "infra_command_invalid"
INFRA_COMMAND_BUSY = "infra_command_busy"
INFRA_COMMAND_NO_EFFECT = "infra_command_no_effect"
INFRA_COMMAND_EFFECT_NOT_CONFIRMED = "infra_command_effect_not_confirmed"
INFRA_CONFIG_FETCH_FAILED = "infra_config_fetch_failed"
INFRA_ZONE_PROCESSING_FAILED = "infra_zone_processing_failed"
INFRA_ZONE_FAILURE_RATE_HIGH = "infra_zone_failure_rate_high"
INFRA_SYSTEM_UNHEALTHY = "infra_system_unhealthy"
INFRA_HEALTH_CHECK_FAILED = "infra_health_check_failed"
INFRA_API_CIRCUIT_OPEN_NO_CACHE = "infra_api_circuit_open_no_cache"
INFRA_CONFIG_FETCH_UNAVAILABLE = "infra_config_fetch_unavailable"
INFRA_CONFIG_MISSING_GREENHOUSE_UID = "infra_config_missing_greenhouse_uid"
INFRA_DB_CIRCUIT_OPEN = "infra_db_circuit_open"
INFRA_AUTOMATION_LOOP_ERROR = "infra_automation_loop_error"
INFRA_CORRECTION_FLAGS_TELEMETRY_SAMPLES_MISSING = "infra_correction_flags_telemetry_samples_missing"

# Reason codes
REASON_REQUIRED_NODES_OFFLINE = "required_nodes_offline"
REASON_REQUIRED_NODES_RECOVERED = "required_nodes_recovered"
REASON_CORRECTION_MISSING_FLAGS = "missing_flags"
REASON_CORRECTION_STALE_FLAGS = "stale_flags"
REASON_CORRECTION_GATING_PASSED = "gating_passed"

# Scheduler execution contract
SCHEDULER_BOOTSTRAP_REQUIRED = "scheduler_bootstrap_required"
SCHEDULER_LEASE_NOT_FOUND = "scheduler_lease_not_found"
SCHEDULER_LEASE_MISMATCH = "scheduler_lease_mismatch"
SCHEDULER_LEASE_EXPIRED = "scheduler_lease_expired"
SCHEDULER_IDEMPOTENCY_PAYLOAD_MISMATCH = "idempotency_payload_mismatch"
SCHEDULER_STATUS_ACCEPTED = "accepted"
SCHEDULER_STATUS_EXPIRED = "expired"
SCHEDULER_STATUS_REJECTED = "rejected"
SCHEDULER_MODE_DEADLINE_REJECTED = "deadline_rejected"
SCHEDULER_MODE_EXECUTION_FAILED = "execution_failed"
SCHEDULER_TASK_RECOVERED_AFTER_RESTART = "task_recovered_after_restart"
SCHEDULER_RETRY_SOURCE = "automation-engine:decision-retry"
SCHEDULER_RETRY_REASON_PAYLOAD_KEY = "decision_retry_reason_code"
SCHEDULER_RETRY_STATUS_FAILED = "failed"

_NON_ALNUM_UNDERSCORE = re.compile(r"[^a-z0-9_]+")


def normalize_resilience_token(value: object, *, fallback: str = "unknown") -> str:
    token = str(value or "").strip().lower()
    token = _NON_ALNUM_UNDERSCORE.sub("_", token).strip("_")
    return token or fallback


def build_decision_alert_code(task_type: object, reason_code: object) -> str:
    return (
        f"infra_"
        f"{normalize_resilience_token(task_type)}_"
        f"{normalize_resilience_token(reason_code)}"
    )
