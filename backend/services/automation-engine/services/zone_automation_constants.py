"""Shared constants for ZoneAutomationService."""

from prometheus_client import Counter, Histogram

from config.settings import get_settings
from services.resilience_contract import (
    REASON_CORRECTION_GATING_PASSED,
    REASON_CORRECTION_MISSING_FLAGS,
    REASON_CORRECTION_STALE_FLAGS,
)

ZONE_CHECKS = Counter("zone_checks_total", "Zone automation checks")
CHECK_LAT = Histogram("zone_check_seconds", "Zone check duration seconds")

CONTROLLER_COOLDOWN_SECONDS = 60

INITIAL_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 600
BACKOFF_MULTIPLIER = 2
DEGRADED_MODE_THRESHOLD = 3
SKIP_REPORT_THROTTLE_SECONDS = 120
COOLDOWN_SKIP_REPORT_THROTTLE_SECONDS = 120
CONTROLLER_CIRCUIT_OPEN_ALERT_THROTTLE_SECONDS = 120
CORRECTION_FLAGS_MISSING_ALERT_THROTTLE_SECONDS = 120
REQUIRED_NODES_OFFLINE_ALERT_THROTTLE_SECONDS = 120

_AUTOMATION_SETTINGS = get_settings()
CORRECTION_FLAGS_MAX_AGE_SECONDS = max(
    30,
    int(getattr(_AUTOMATION_SETTINGS, "AE_CORRECTION_FLAGS_MAX_AGE_SEC", 300)),
)
CORRECTION_FLAGS_STALE_ALERT_THROTTLE_SECONDS = max(
    30,
    int(getattr(_AUTOMATION_SETTINGS, "AE_CORRECTION_FLAGS_STALE_ALERT_THROTTLE_SEC", 120)),
)
CORRECTION_SKIP_EVENT_THROTTLE_SECONDS = max(
    5,
    int(getattr(_AUTOMATION_SETTINGS, "AE_CORRECTION_SKIP_EVENT_THROTTLE_SEC", 120)),
)
CORRECTION_FLAGS_REQUIRE_TIMESTAMPS = bool(
    getattr(_AUTOMATION_SETTINGS, "AE_CORRECTION_FLAGS_REQUIRE_TS", True)
)
CORRECTION_REQUIRED_FLAG_NAMES = ("flow_active", "stable", "corrections_allowed")
WORKFLOW_PHASE_EVENT_TYPE = "WORKFLOW_PHASE_UPDATED"
WORKFLOW_PHASE_VALUES = {"idle", "tank_filling", "tank_recirc", "ready", "irrigating", "irrig_recirc"}
WORKFLOW_CORRECTION_OPEN_PHASES = {"tank_filling", "tank_recirc"}
WORKFLOW_SENSOR_MODE_EXTERNAL_PHASES = {"tank_filling", "tank_recirc", "irrig_recirc"}
WORKFLOW_EC_COMPONENTS_BY_PHASE = {
    "tank_filling": ["npk"],
    "tank_recirc": ["npk"],
    "irrigating": ["calcium", "magnesium", "micro"],
    "irrig_recirc": ["calcium", "magnesium", "micro"],
}
SENSOR_MODE_POLICY = {
    REASON_CORRECTION_GATING_PASSED: "noop",
    REASON_CORRECTION_MISSING_FLAGS: "noop",
    "flow_inactive": "deactivate",
    "sensor_unstable": "deactivate",
    "corrections_not_allowed": "deactivate",
    REASON_CORRECTION_STALE_FLAGS: "deactivate",
}

