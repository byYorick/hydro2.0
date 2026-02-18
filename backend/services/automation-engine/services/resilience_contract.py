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

# Reason codes
REASON_REQUIRED_NODES_OFFLINE = "required_nodes_offline"
REASON_REQUIRED_NODES_RECOVERED = "required_nodes_recovered"
