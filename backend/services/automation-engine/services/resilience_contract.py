"""Unified resilience contract constants (S10 incremental consolidation)."""

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
INFRA_IRRIGATION_PUMP_BLOCKED = "infra_irrigation_pump_blocked"
INFRA_ZONE_DELETION_CHECK_FAILED = "infra_zone_deletion_check_failed"
INFRA_PID_CONFIG_UPDATE_CHECK_FAILED = "infra_pid_config_update_check_failed"
INFRA_ZONE_EVENT_WRITE_FAILED = "infra_zone_event_write_failed"

# Reason codes
REASON_REQUIRED_NODES_OFFLINE = "required_nodes_offline"
REASON_REQUIRED_NODES_RECOVERED = "required_nodes_recovered"
REASON_CORRECTION_MISSING_FLAGS = "missing_flags"
REASON_CORRECTION_STALE_FLAGS = "stale_flags"
REASON_CORRECTION_GATING_PASSED = "gating_passed"
