from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from common.db import execute, fetch
from common.infra_alerts import send_infra_alert
from common.logging_setup import (
    attach_service_context,
    get_log_format,
    get_log_level,
    install_exception_handlers,
    setup_standard_logging,
)
from common.utils.time import utcnow
from config.settings import get_settings as get_automation_settings
from infrastructure.command_bus import COMMANDS_SENT
from infrastructure.runtime_state_store import RuntimeStateStore
from prometheus_client import Counter, Gauge, Histogram
from utils.logging_context import setup_structured_logging

if get_log_format() == "json":
    setup_structured_logging(level=get_log_level())
    attach_service_context("automation-engine")
else:
    setup_standard_logging("automation-engine")
install_exception_handlers("automation-engine")

logger = logging.getLogger(__name__)

ALERT_SEND_TIMEOUT_SECONDS = 5.0
AE_ZONE_PROCESS_TIMEOUT_SEC = max(1.0, float(os.getenv("AE_ZONE_PROCESS_TIMEOUT_SEC", "90")))
SYSTEM_STATE_LOG_INTERVAL_SEC = max(30.0, float(os.getenv("AE_SYSTEM_STATE_LOG_INTERVAL_SEC", "300")))

LOOP_ERRORS = Counter("automation_loop_errors_total", "Errors in automation main loop", ["error_type"])
CONFIG_FETCH_ERRORS = Counter("config_fetch_errors_total", "Errors fetching config from Laravel", ["error_type"])
CONFIG_FETCH_SUCCESS = Counter("config_fetch_success_total", "Successful config fetches from Laravel")

ZONE_PROCESSING_TIME = Histogram(
    "zone_processing_time_seconds",
    "Time to process a single zone",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)
ZONE_PROCESSING_ERRORS = Counter(
    "zone_processing_errors_total",
    "Errors during zone processing",
    ["zone_id", "error_type"],
)
OPTIMAL_CONCURRENCY = Gauge(
    "optimal_concurrency_zones",
    "Calculated optimal concurrency for zone processing",
)

_avg_processing_time = 1.0
_processing_times: list[float] = []
_MAX_SAMPLES = 100
_processing_times_lock = asyncio.Lock()

_shutdown_event = asyncio.Event()
_zone_service: Optional[Any] = None
_command_tracker: Optional[Any] = None
_command_bus: Optional[Any] = None
_runtime_state_restored = False

_last_db_circuit_open_alert_at: Optional[datetime] = None
_DB_CIRCUIT_OPEN_ALERT_THROTTLE_SECONDS = 120
_last_health_unhealthy_alert_at: Optional[datetime] = None
_HEALTH_UNHEALTHY_ALERT_THROTTLE_SECONDS = 180
_last_health_check_failed_alert_at: Optional[datetime] = None
_HEALTH_CHECK_FAILED_ALERT_THROTTLE_SECONDS = 180
_last_config_unavailable_alert_at: Optional[datetime] = None
_CONFIG_UNAVAILABLE_ALERT_THROTTLE_SECONDS = 180
_last_missing_gh_uid_alert_at: Optional[datetime] = None
_MISSING_GH_UID_ALERT_THROTTLE_SECONDS = 300
_last_config_fetch_error_alert_at: Dict[str, datetime] = {}
_CONFIG_FETCH_ERROR_ALERT_THROTTLE_SECONDS = 180
_AE2_RUNTIME_SINGLE_WRITER_ENFORCE = str(os.getenv("AE2_RUNTIME_SINGLE_WRITER_ENFORCE", "1")).strip().lower() in {"1", "true", "yes", "on"}
_AE2_FALLBACK_LOOP_WRITER_ENABLED = str(os.getenv("AE2_FALLBACK_LOOP_WRITER_ENABLED", "0")).strip().lower() in {"1", "true", "yes", "on"}
_last_scheduler_single_writer_skip_log_at: Optional[datetime] = None
_SCHEDULER_SINGLE_WRITER_SKIP_LOG_THROTTLE_SECONDS = 120
# Watchdog: если scheduler-writer активен дольше этого порога — принудительный fallback
_SCHEDULER_WRITER_WATCHDOG_TIMEOUT_SEC: float = max(
    60.0, float(os.getenv("AE2_SCHEDULER_WRITER_WATCHDOG_SEC", "600"))
)
_scheduler_writer_active_since: Optional[float] = None  # time.monotonic(), None если не активен


def _serialize_optional_datetime(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else None


def _deserialize_optional_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _export_main_runtime_state() -> Dict[str, Any]:
    return {
        "last_db_circuit_open_alert_at": _serialize_optional_datetime(_last_db_circuit_open_alert_at),
        "last_health_unhealthy_alert_at": _serialize_optional_datetime(_last_health_unhealthy_alert_at),
        "last_health_check_failed_alert_at": _serialize_optional_datetime(_last_health_check_failed_alert_at),
        "last_config_unavailable_alert_at": _serialize_optional_datetime(_last_config_unavailable_alert_at),
        "last_missing_gh_uid_alert_at": _serialize_optional_datetime(_last_missing_gh_uid_alert_at),
        "last_scheduler_single_writer_skip_log_at": _serialize_optional_datetime(_last_scheduler_single_writer_skip_log_at),
        "last_config_fetch_error_alert_at": {
            str(error_type): dt.isoformat()
            for error_type, dt in _last_config_fetch_error_alert_at.items()
            if isinstance(dt, datetime)
        },
    }


def _restore_main_runtime_state(raw_state: Optional[Dict[str, Any]]) -> None:
    global _last_db_circuit_open_alert_at
    global _last_health_unhealthy_alert_at
    global _last_health_check_failed_alert_at
    global _last_config_unavailable_alert_at
    global _last_missing_gh_uid_alert_at
    global _last_config_fetch_error_alert_at
    global _last_scheduler_single_writer_skip_log_at

    state = raw_state if isinstance(raw_state, dict) else {}
    _last_db_circuit_open_alert_at = _deserialize_optional_datetime(state.get("last_db_circuit_open_alert_at"))
    _last_health_unhealthy_alert_at = _deserialize_optional_datetime(state.get("last_health_unhealthy_alert_at"))
    _last_health_check_failed_alert_at = _deserialize_optional_datetime(state.get("last_health_check_failed_alert_at"))
    _last_config_unavailable_alert_at = _deserialize_optional_datetime(state.get("last_config_unavailable_alert_at"))
    _last_missing_gh_uid_alert_at = _deserialize_optional_datetime(state.get("last_missing_gh_uid_alert_at"))
    _last_scheduler_single_writer_skip_log_at = _deserialize_optional_datetime(state.get("last_scheduler_single_writer_skip_log_at"))

    restored: Dict[str, datetime] = {}
    raw_fetch_map = state.get("last_config_fetch_error_alert_at")
    if isinstance(raw_fetch_map, dict):
        for error_type, dt_raw in raw_fetch_map.items():
            dt = _deserialize_optional_datetime(dt_raw)
            if dt is not None:
                restored[str(error_type)] = dt
    _last_config_fetch_error_alert_at = restored


def _restore_zone_runtime_state_snapshot(zone_service: Optional[Any], automation_settings: Any) -> bool:
    if zone_service is None:
        return False
    if not bool(getattr(automation_settings, "AE_RUNTIME_STATE_PERSIST_ENABLED", True)):
        return False

    snapshot_path = str(getattr(automation_settings, "AE_RUNTIME_STATE_SNAPSHOT_PATH", "")).strip()
    if not snapshot_path:
        return False

    snapshot = RuntimeStateStore(snapshot_path).load()
    if not isinstance(snapshot, dict):
        return False

    zone_service.restore_runtime_state(snapshot.get("zone_service"))
    _restore_main_runtime_state(snapshot.get("main_runtime"))
    logger.info(
        "Runtime snapshot restored",
        extra={
            "snapshot_path": snapshot_path,
            "schema_version": snapshot.get("schema_version"),
            "saved_at": snapshot.get("saved_at"),
        },
    )
    return True


def _save_zone_runtime_state_snapshot(zone_service: Optional[Any], automation_settings: Any) -> bool:
    if zone_service is None:
        return False
    if not bool(getattr(automation_settings, "AE_RUNTIME_STATE_PERSIST_ENABLED", True)):
        return False

    snapshot_path = str(getattr(automation_settings, "AE_RUNTIME_STATE_SNAPSHOT_PATH", "")).strip()
    if not snapshot_path:
        return False

    payload = {
        "saved_at": utcnow().isoformat(),
        "zone_service": zone_service.export_runtime_state(),
        "main_runtime": _export_main_runtime_state(),
    }
    saved = RuntimeStateStore(snapshot_path).save(payload)
    if saved:
        logger.info("Runtime snapshot saved", extra={"snapshot_path": snapshot_path})
    return saved


def _should_emit_db_circuit_open_alert(now: datetime) -> bool:
    global _last_db_circuit_open_alert_at
    if _last_db_circuit_open_alert_at is None:
        _last_db_circuit_open_alert_at = now
        return True
    if (now - _last_db_circuit_open_alert_at).total_seconds() >= _DB_CIRCUIT_OPEN_ALERT_THROTTLE_SECONDS:
        _last_db_circuit_open_alert_at = now
        return True
    return False


def _should_emit_health_unhealthy_alert(now: datetime) -> bool:
    global _last_health_unhealthy_alert_at
    if _last_health_unhealthy_alert_at is None:
        _last_health_unhealthy_alert_at = now
        return True
    if (now - _last_health_unhealthy_alert_at).total_seconds() >= _HEALTH_UNHEALTHY_ALERT_THROTTLE_SECONDS:
        _last_health_unhealthy_alert_at = now
        return True
    return False


def _should_emit_health_check_failed_alert(now: datetime) -> bool:
    global _last_health_check_failed_alert_at
    if _last_health_check_failed_alert_at is None:
        _last_health_check_failed_alert_at = now
        return True
    if (now - _last_health_check_failed_alert_at).total_seconds() >= _HEALTH_CHECK_FAILED_ALERT_THROTTLE_SECONDS:
        _last_health_check_failed_alert_at = now
        return True
    return False


def _should_emit_config_unavailable_alert(now: datetime) -> bool:
    global _last_config_unavailable_alert_at
    if _last_config_unavailable_alert_at is None:
        _last_config_unavailable_alert_at = now
        return True
    if (now - _last_config_unavailable_alert_at).total_seconds() >= _CONFIG_UNAVAILABLE_ALERT_THROTTLE_SECONDS:
        _last_config_unavailable_alert_at = now
        return True
    return False


def _should_emit_missing_gh_uid_alert(now: datetime) -> bool:
    global _last_missing_gh_uid_alert_at
    if _last_missing_gh_uid_alert_at is None:
        _last_missing_gh_uid_alert_at = now
        return True
    if (now - _last_missing_gh_uid_alert_at).total_seconds() >= _MISSING_GH_UID_ALERT_THROTTLE_SECONDS:
        _last_missing_gh_uid_alert_at = now
        return True
    return False


def _should_emit_config_fetch_error_alert(now: datetime, error_type: str) -> bool:
    last = _last_config_fetch_error_alert_at.get(error_type)
    if last is None:
        _last_config_fetch_error_alert_at[error_type] = now
        return True
    if (now - last).total_seconds() >= _CONFIG_FETCH_ERROR_ALERT_THROTTLE_SECONDS:
        _last_config_fetch_error_alert_at[error_type] = now
        return True
    return False


def _should_log_scheduler_single_writer_skip(now: datetime) -> bool:
    global _last_scheduler_single_writer_skip_log_at
    if _last_scheduler_single_writer_skip_log_at is None:
        _last_scheduler_single_writer_skip_log_at = now
        return True
    if (now - _last_scheduler_single_writer_skip_log_at).total_seconds() >= _SCHEDULER_SINGLE_WRITER_SKIP_LOG_THROTTLE_SECONDS:
        _last_scheduler_single_writer_skip_log_at = now
        return True
    return False


async def _is_scheduler_single_writer_active() -> bool:
    if not _AE2_RUNTIME_SINGLE_WRITER_ENFORCE:
        return False
    try:
        from api import is_scheduler_single_writer_active
    except Exception:
        return False
    try:
        return bool(await is_scheduler_single_writer_active())
    except Exception as exc:
        logger.warning("Failed to check scheduler single-writer state: %s", exc, exc_info=True)
        return False


async def _emit_config_fetch_failure_alert(*, error_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
    now = utcnow()
    if not _should_emit_config_fetch_error_alert(now, error_type):
        return

    payload_details = dict(details) if isinstance(details, dict) else {}
    payload_details["throttle_seconds"] = _CONFIG_FETCH_ERROR_ALERT_THROTTLE_SECONDS

    await send_infra_alert(
        code="infra_config_fetch_failed",
        alert_type="Config Fetch Failed",
        message=message,
        severity="error",
        zone_id=None,
        service="automation-engine",
        component="config_fetch",
        error_type=error_type,
        details=payload_details,
    )


__all__ = [
    "COMMANDS_SENT",
    "CONFIG_FETCH_ERRORS",
    "CONFIG_FETCH_SUCCESS",
    "LOOP_ERRORS",
    "OPTIMAL_CONCURRENCY",
    "ZONE_PROCESSING_ERRORS",
    "ZONE_PROCESSING_TIME",
    "_AE2_FALLBACK_LOOP_WRITER_ENABLED",
    "_AE2_RUNTIME_SINGLE_WRITER_ENFORCE",
    "_CONFIG_UNAVAILABLE_ALERT_THROTTLE_SECONDS",
    "_DB_CIRCUIT_OPEN_ALERT_THROTTLE_SECONDS",
    "_HEALTH_CHECK_FAILED_ALERT_THROTTLE_SECONDS",
    "_HEALTH_UNHEALTHY_ALERT_THROTTLE_SECONDS",
    "_MAX_SAMPLES",
    "_MISSING_GH_UID_ALERT_THROTTLE_SECONDS",
    "_avg_processing_time",
    "_command_bus",
    "_command_tracker",
    "_emit_config_fetch_failure_alert",
    "_is_scheduler_single_writer_active",
    "_processing_times",
    "_processing_times_lock",
    "_restore_zone_runtime_state_snapshot",
    "_runtime_state_restored",
    "_save_zone_runtime_state_snapshot",
    "_should_emit_config_unavailable_alert",
    "_should_emit_db_circuit_open_alert",
    "_should_emit_health_check_failed_alert",
    "_should_emit_health_unhealthy_alert",
    "_should_emit_missing_gh_uid_alert",
    "_should_log_scheduler_single_writer_skip",
    "_scheduler_writer_active_since",
    "_SCHEDULER_WRITER_WATCHDOG_TIMEOUT_SEC",
    "_shutdown_event",
    "_zone_service",
    "AE_ZONE_PROCESS_TIMEOUT_SEC",
    "ALERT_SEND_TIMEOUT_SECONDS",
    "SYSTEM_STATE_LOG_INTERVAL_SEC",
    "execute",
    "fetch",
    "get_automation_settings",
    "logger",
    "utcnow",
]
