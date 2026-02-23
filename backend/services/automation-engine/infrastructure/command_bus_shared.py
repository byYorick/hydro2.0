"""Shared constants and metrics for CommandBus helpers."""

import os

from prometheus_client import Counter, Histogram

_TRUE_VALUES = {"1", "true", "yes", "on"}
_DEFAULT_CLOSED_LOOP_TIMEOUT_SEC = max(1.0, float(os.getenv("AE_COMMAND_CLOSED_LOOP_TIMEOUT_SEC", "60")))
_TERMINAL_COMMAND_STATUSES = {"DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT", "TIMEOUT", "SEND_FAILED"}
_ACTUATOR_COMMANDS = {"set_relay", "set_pwm", "run_pump", "dose", "light_on", "light_off"}
_SYSTEM_MODE_COMMANDS = {"activate_sensor_mode", "deactivate_sensor_mode"}
_DEFAULT_COMMAND_DEDUPE_TTL_SEC = max(10, int(os.getenv("AE_COMMAND_DEDUPE_TTL_SEC", "3600")))
_MAX_COMMAND_DEDUPE_ENTRIES = max(1000, int(os.getenv("AE_COMMAND_DEDUPE_MAX_ENTRIES", "50000")))

REST_PUBLISH_ERRORS = Counter("rest_command_errors_total", "REST command publish errors", ["error_type"])
COMMANDS_SENT = Counter("automation_commands_sent_total", "Commands sent by automation", ["zone_id", "metric"])
COMMAND_VALIDATION_FAILED = Counter("command_validation_failed_total", "Failed command validations", ["zone_id", "reason"])
COMMAND_REST_LATENCY = Histogram("command_rest_latency_seconds", "REST command publish latency", buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0])
COMMAND_DEDUPE_DECISIONS = Counter(
    "command_dedupe_decisions_total",
    "Command dedupe decisions before publish",
    ["outcome"],
)
COMMAND_DEDUPE_HITS = Counter(
    "command_dedupe_hits_total",
    "Command dedupe hits (duplicate decisions)",
    ["outcome"],
)
COMMAND_DEDUPE_RESERVE_CONFLICTS = Counter(
    "command_dedupe_reserve_conflicts_total",
    "Command dedupe reserve conflicts",
)

