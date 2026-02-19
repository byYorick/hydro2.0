import asyncio
import hashlib
import logging
import os
import random
import socket
import sys
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import asyncpg
import httpx
from common.db import create_scheduler_log, create_zone_event, fetch
from common.env import get_settings
from common.infra_alerts import send_infra_alert, send_infra_exception_alert
from common.logging_setup import install_exception_handlers, setup_standard_logging
from common.service_logs import send_service_log
from common.simulation_events import record_simulation_event
from common.trace_context import (
    clear_trace_id,
    get_trace_id,
    inject_trace_id_header,
    set_trace_id,
)
from common.utils.time import utcnow
from prometheus_client import Counter, Gauge, Histogram, start_http_server

# Настройка логирования
setup_standard_logging("scheduler")
install_exception_handlers("scheduler")

logger = logging.getLogger(__name__)

SCHEDULE_EXECUTIONS = Counter("schedule_executions_total", "Scheduled tasks executed", ["zone_id", "task_type"])
ACTIVE_SCHEDULES = Gauge("active_schedules", "Number of active schedules")
COMMAND_REST_ERRORS = Counter("scheduler_command_rest_errors_total", "REST command errors from scheduler", ["error_type"])
SCHEDULER_DIAGNOSTICS = Counter(
    "scheduler_diagnostics_total",
    "Scheduler diagnostics counters",
    ["reason"],
)
SCHEDULER_TASK_STATUS = Counter(
    "scheduler_task_status_total",
    "Status of abstract scheduler tasks",
    ["task_type", "status"],
)
SCHEDULER_TASK_ACCEPT_LATENCY_SEC = Histogram(
    "scheduler_task_accept_latency_sec",
    "Latency between scheduler submit and automation accept response",
    ["task_type"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
SCHEDULER_TASK_COMPLETION_LATENCY_SEC = Histogram(
    "scheduler_task_completion_latency_sec",
    "Latency between scheduler accept and terminal status",
    ["task_type", "status"],
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300),
)
TASK_ACCEPT_TO_TERMINAL_LATENCY = Histogram(
    "task_accept_to_terminal_latency",
    "Scheduler task accept-to-terminal latency (seconds)",
    ["task_type", "status"],
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300),
)
TASK_DEADLINE_VIOLATION_RATE = Gauge(
    "task_deadline_violation_rate",
    "Share of tasks with deadline violations (rejected/expired)",
    ["task_type"],
)
SCHEDULER_ACTIVE_TASKS = Gauge(
    "scheduler_active_tasks",
    "Current number of active abstract scheduler tasks",
)
SCHEDULER_LEADER_ROLE = Gauge(
    "scheduler_leader_role",
    "Scheduler leader role: 1 leader, 0 follower",
)
SCHEDULER_LEADER_TRANSITIONS = Counter(
    "scheduler_leader_transitions_total",
    "Scheduler leader transitions",
    ["transition"],
)
SCHEDULER_DISPATCH_SKIPS = Counter(
    "scheduler_dispatch_skips_total",
    "Scheduler dispatch skips by reason",
    ["reason"],
)

# URL automation-engine для отправки абстрактных задач
AUTOMATION_ENGINE_URL = os.getenv("AUTOMATION_ENGINE_URL", "http://automation-engine:9405")

# Таймауты scheduler->automation-engine task API
SCHEDULER_TASK_TIMEOUT_SEC = max(1.0, float(os.getenv("SCHEDULER_TASK_TIMEOUT_SEC", "30")))
SCHEDULER_TASK_POLL_INTERVAL_SEC = max(0.2, float(os.getenv("SCHEDULER_TASK_POLL_INTERVAL_SEC", "1.0")))
SCHEDULER_DUE_GRACE_SEC = max(1, int(os.getenv("SCHEDULER_DUE_GRACE_SEC", "15")))
SCHEDULER_EXPIRES_AFTER_SEC = max(SCHEDULER_DUE_GRACE_SEC + 1, int(os.getenv("SCHEDULER_EXPIRES_AFTER_SEC", "120")))
SCHEDULER_ID = os.getenv("SCHEDULER_ID", socket.gethostname() or "scheduler-1")
SCHEDULER_VERSION = os.getenv("SCHEDULER_VERSION", "3.0.0")
SCHEDULER_PROTOCOL_VERSION = os.getenv("SCHEDULER_PROTOCOL_VERSION", "2.0")
SCHEDULER_API_TOKEN = str(
    os.getenv("SCHEDULER_API_TOKEN")
    or os.getenv("PY_INGEST_TOKEN")
    or os.getenv("PY_API_TOKEN")
    or ""
).strip()
SCHEDULER_MAIN_TICK_SEC = max(1.0, float(os.getenv("SCHEDULER_MAIN_TICK_SEC", "5")))
SCHEDULER_DISPATCH_INTERVAL_SEC = max(1.0, float(os.getenv("SCHEDULER_DISPATCH_INTERVAL_SEC", "60")))
SCHEDULER_LEADER_ELECTION_ENABLED = os.getenv("SCHEDULER_LEADER_ELECTION", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
SCHEDULER_LEADER_LOCK_SCOPE = os.getenv("SCHEDULER_LEADER_LOCK_SCOPE", "cluster:default")
SCHEDULER_LEADER_RETRY_BACKOFF_SEC = max(1.0, float(os.getenv("SCHEDULER_LEADER_RETRY_BACKOFF_SEC", "2")))
SCHEDULER_LEADER_DB_TIMEOUT_SEC = max(1.0, float(os.getenv("SCHEDULER_LEADER_DB_TIMEOUT_SEC", "5")))
SCHEDULER_LEADER_HEALTHCHECK_SEC = max(1.0, float(os.getenv("SCHEDULER_LEADER_HEALTHCHECK_SEC", "10")))
_TRUE_VALUES = {"1", "true", "yes", "on"}
_CATCHUP_POLICIES = {"skip", "replay_limited", "replay_all"}
_raw_catchup_policy = os.getenv("SCHEDULER_CATCHUP_POLICY", "replay_limited").strip().lower()
SCHEDULER_CATCHUP_POLICY = _raw_catchup_policy if _raw_catchup_policy in _CATCHUP_POLICIES else "replay_limited"
SCHEDULER_CATCHUP_MAX_WINDOWS = max(1, int(os.getenv("SCHEDULER_CATCHUP_MAX_WINDOWS", "3")))
SCHEDULER_CATCHUP_RATE_LIMIT_PER_CYCLE = max(1, int(os.getenv("SCHEDULER_CATCHUP_RATE_LIMIT_PER_CYCLE", "20")))
SCHEDULER_CATCHUP_JITTER_SEC = max(0.0, float(os.getenv("SCHEDULER_CATCHUP_JITTER_SEC", "0")))
SCHEDULER_CURSOR_PERSIST_ENABLED = str(os.getenv("SCHEDULER_CURSOR_PERSIST_ENABLED", "1")).strip().lower() in _TRUE_VALUES

# Bootstrap / heartbeat state
_BOOTSTRAP_BACKOFF_STEPS_SEC = (1, 2, 5, 10, 15)
_bootstrap_ready: bool = False
_bootstrap_lease_id: Optional[str] = None
_bootstrap_lease_ttl_sec: int = 60
_bootstrap_poll_interval_sec: int = 5
_bootstrap_next_attempt_at: Optional[datetime] = None
_bootstrap_next_heartbeat_at: Optional[datetime] = None
_bootstrap_lease_expires_at: Optional[datetime] = None
_bootstrap_retry_idx: int = 0

# Leader election state
_leader_conn: Optional[asyncpg.Connection] = None
_leader_active: bool = False
_leader_next_attempt_at: Optional[datetime] = None
_leader_next_healthcheck_at: Optional[datetime] = None

# Временное хранилище последнего тика per zone (для sim-time пересечений)
_LAST_SCHEDULE_CHECKS: Dict[int, datetime] = {}
_LOADED_ZONE_CURSORS: set[int] = set()
_TASK_TERMINAL_COUNTS: Dict[str, int] = {}
_TASK_DEADLINE_VIOLATIONS: Dict[str, int] = {}
_ACTIVE_TASKS: Dict[str, Dict[str, Any]] = {}
_ACTIVE_SCHEDULE_TASKS: Dict[str, str] = {}
_WINDOW_LAST_STATE: Dict[str, bool] = {}
_INTERNAL_ENQUEUE_TASK_NAME_PREFIX = "ae_internal_enqueue_"
_INTERNAL_ENQUEUE_SCAN_LIMIT = max(50, int(os.getenv("SCHEDULER_INTERNAL_ENQUEUE_SCAN_LIMIT", "500")))
_INTERNAL_ENQUEUE_EXPIRE_GRACE_SEC = max(
    0.0,
    float(
        os.getenv(
            "SCHEDULER_INTERNAL_ENQUEUE_EXPIRE_GRACE_SEC",
            str(max(1.0, SCHEDULER_DISPATCH_INTERVAL_SEC)),
        )
    ),
)
_INTERNAL_ENQUEUE_DISPATCH_MAX_ATTEMPTS = max(
    1,
    int(os.getenv("SCHEDULER_INTERNAL_ENQUEUE_DISPATCH_MAX_ATTEMPTS", "3")),
)
_INTERNAL_ENQUEUE_DISPATCH_BACKOFF_BASE_SEC = max(
    1.0,
    float(os.getenv("SCHEDULER_INTERNAL_ENQUEUE_DISPATCH_BACKOFF_BASE_SEC", "10")),
)
_INTERNAL_ENQUEUE_DISPATCH_BACKOFF_MAX_SEC = max(
    _INTERNAL_ENQUEUE_DISPATCH_BACKOFF_BASE_SEC,
    float(os.getenv("SCHEDULER_INTERNAL_ENQUEUE_DISPATCH_BACKOFF_MAX_SEC", "300")),
)
_ACTIVE_TASK_RECOVERY_SCAN_LIMIT = max(50, int(os.getenv("SCHEDULER_ACTIVE_TASK_RECOVERY_SCAN_LIMIT", "1000")))
SCHEDULER_ZONE_PREFLIGHT_ENFORCE = str(os.getenv("SCHEDULER_ZONE_PREFLIGHT_ENFORCE", "0")).strip().lower() in _TRUE_VALUES

# Анти-спам для сервисных логов/алертов
_LAST_DIAGNOSTIC_AT: Dict[str, datetime] = {}
_DIAGNOSTIC_THROTTLE_SECONDS = 300

SUPPORTED_TASK_TYPES = {
    "irrigation",
    "lighting",
    "ventilation",
    "solution_change",
    "mist",
    "diagnostics",
}


def _diagnostic_allowed(key: str, now: datetime) -> bool:
    last = _LAST_DIAGNOSTIC_AT.get(key)
    if last is None:
        _LAST_DIAGNOSTIC_AT[key] = now
        return True
    if (now - last).total_seconds() >= _DIAGNOSTIC_THROTTLE_SECONDS:
        _LAST_DIAGNOSTIC_AT[key] = now
        return True
    return False


def _safe_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return max(0, default)
    return max(0, parsed)


def _internal_enqueue_dispatch_backoff_sec(attempt: int) -> float:
    # attempt=1 -> base, attempt=2 -> base*2 ...
    exponent = max(0, attempt - 1)
    delay = _INTERNAL_ENQUEUE_DISPATCH_BACKOFF_BASE_SEC * (2 ** exponent)
    return min(_INTERNAL_ENQUEUE_DISPATCH_BACKOFF_MAX_SEC, delay)


async def _emit_scheduler_diagnostic(
    *,
    reason: str,
    message: str,
    level: str = "warning",
    zone_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
    alert_code: Optional[str] = None,
    alert_type: str = "Scheduler Diagnostic",
    error_type: Optional[str] = None,
) -> None:
    SCHEDULER_DIAGNOSTICS.labels(reason=reason).inc()
    now = utcnow().replace(tzinfo=None)
    key = f"{reason}|{zone_id or 'global'}|{level}"
    if not _diagnostic_allowed(key, now):
        return

    context = dict(details) if isinstance(details, dict) else {}
    context.update({"reason": reason, "zone_id": zone_id})
    send_service_log(
        service="scheduler",
        level=level,
        message=message,
        context=context,
    )

    if alert_code:
        severity = "error" if level in {"error", "critical"} else "warning"
        await send_infra_alert(
            code=alert_code,
            alert_type=alert_type,
            message=message,
            severity=severity,
            zone_id=zone_id,
            service="scheduler",
            component="schedule_builder",
            error_type=error_type or reason,
            details=context,
        )


@dataclass(frozen=True)
class SimulationClock:
    real_start: datetime
    sim_start: datetime
    time_scale: float

    def now(self) -> datetime:
        real_now = utcnow().replace(tzinfo=None)
        elapsed = (real_now - self.real_start).total_seconds()
        return self.sim_start + timedelta(seconds=elapsed * self.time_scale)


def _to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return _to_naive_utc(parsed)


def _extract_simulation_clock(row: Dict[str, Any]) -> Optional[SimulationClock]:
    scenario = row.get("scenario") or {}
    sim_meta = scenario.get("simulation") or {}
    real_start = _parse_iso_datetime(sim_meta.get("real_started_at") or sim_meta.get("started_at"))
    sim_start = _parse_iso_datetime(sim_meta.get("sim_started_at") or sim_meta.get("sim_start_at"))
    if not real_start:
        created_at = row.get("created_at")
        if not created_at:
            return None
        real_start = _to_naive_utc(created_at)
    if not sim_start:
        sim_start = real_start

    time_scale = sim_meta.get("time_scale")
    if time_scale is None:
        duration_hours = row.get("duration_hours")
        real_minutes = sim_meta.get("real_duration_minutes")
        real_seconds = sim_meta.get("real_duration_seconds")
        if duration_hours and real_minutes:
            time_scale = (duration_hours * 60) / float(real_minutes)
        elif duration_hours and real_seconds:
            time_scale = (duration_hours * 3600) / float(real_seconds)

    try:
        time_scale_value = float(time_scale)
    except (TypeError, ValueError):
        return None
    if time_scale_value <= 0:
        return None

    return SimulationClock(real_start=real_start, sim_start=sim_start, time_scale=time_scale_value)


def _default_last_check(now_dt: datetime, sim_clock: Optional[SimulationClock]) -> datetime:
    delta_seconds = 60.0
    if sim_clock:
        delta_seconds *= sim_clock.time_scale
    return now_dt - timedelta(seconds=delta_seconds)


def _get_last_check(zone_id: int, now_dt: datetime, sim_clock: Optional[SimulationClock]) -> datetime:
    last_check = _LAST_SCHEDULE_CHECKS.get(zone_id)
    if last_check is not None:
        return last_check
    return _default_last_check(now_dt, sim_clock)


async def _resolve_zone_last_check(zone_id: int, now_dt: datetime, sim_clock: Optional[SimulationClock]) -> datetime:
    last_check = _LAST_SCHEDULE_CHECKS.get(zone_id)
    if last_check is not None:
        return last_check

    fallback = _default_last_check(now_dt, sim_clock)
    if not SCHEDULER_CURSOR_PERSIST_ENABLED:
        _LAST_SCHEDULE_CHECKS[zone_id] = fallback
        return fallback

    if zone_id in _LOADED_ZONE_CURSORS:
        _LAST_SCHEDULE_CHECKS[zone_id] = fallback
        return fallback

    task_name = f"scheduler_cursor_zone_{zone_id}"
    try:
        rows = await fetch(
            """
            SELECT details
            FROM scheduler_logs
            WHERE task_name = $1
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            task_name,
        )
    except Exception as exc:
        await _emit_scheduler_diagnostic(
            reason="schedule_cursor_load_failed",
            message=f"Scheduler не смог загрузить персистентный cursor для зоны {zone_id}",
            level="error",
            zone_id=zone_id,
            details={"error": str(exc), "task_name": task_name},
            alert_code="infra_scheduler_cursor_load_failed",
            error_type=type(exc).__name__,
        )
        return fallback

    _LOADED_ZONE_CURSORS.add(zone_id)
    if rows:
        details = rows[0].get("details")
        if isinstance(details, dict):
            parsed = _parse_iso_datetime_utc(str(details.get("last_check") or details.get("cursor_at") or ""))
            if parsed is not None:
                _LAST_SCHEDULE_CHECKS[zone_id] = parsed
                return parsed

    _LAST_SCHEDULE_CHECKS[zone_id] = fallback
    return fallback


async def _persist_zone_cursor(zone_id: int, cursor_at: datetime) -> None:
    if not SCHEDULER_CURSOR_PERSIST_ENABLED:
        return

    task_name = f"scheduler_cursor_zone_{zone_id}"
    try:
        await create_scheduler_log(
            task_name,
            "cursor",
            {
                "zone_id": zone_id,
                "last_check": cursor_at.isoformat(),
                "cursor_at": cursor_at.isoformat(),
                "catchup_policy": SCHEDULER_CATCHUP_POLICY,
            },
        )
    except Exception as exc:
        await _emit_scheduler_diagnostic(
            reason="schedule_cursor_persist_failed",
            message=f"Scheduler не смог сохранить cursor для зоны {zone_id}",
            level="error",
            zone_id=zone_id,
            details={"error": str(exc), "task_name": task_name},
            alert_code="infra_scheduler_cursor_persist_failed",
            error_type=type(exc).__name__,
        )


def _apply_catchup_policy(crossings: List[datetime], now_dt: datetime) -> List[datetime]:
    if not crossings:
        return []

    if SCHEDULER_CATCHUP_POLICY == "skip":
        return [now_dt]
    if SCHEDULER_CATCHUP_POLICY == "replay_limited":
        return crossings[-SCHEDULER_CATCHUP_MAX_WINDOWS :]
    return crossings


def _schedule_crossings(last_dt: datetime, now_dt: datetime, target: time) -> List[datetime]:
    if now_dt < last_dt:
        last_dt, now_dt = now_dt, last_dt
    start_date = last_dt.date()
    end_date = now_dt.date()
    days = (end_date - start_date).days
    crossings: List[datetime] = []
    for offset in range(days + 1):
        day = start_date + timedelta(days=offset)
        candidate = datetime.combine(day, target)
        if last_dt < candidate <= now_dt:
            crossings.append(candidate)
    return crossings


async def get_simulation_clocks(zone_ids: List[int]) -> Dict[int, SimulationClock]:
    if not zone_ids:
        return {}
    try:
        rows = await fetch(
            """
            SELECT DISTINCT ON (zone_id)
                zone_id,
                scenario,
                duration_hours,
                created_at
            FROM zone_simulations
            WHERE zone_id = ANY($1::int[]) AND status = 'running'
            ORDER BY zone_id, created_at DESC
            """,
            zone_ids,
        )
    except Exception as e:
        logger.warning(f"Failed to load simulation clocks: {e}")
        return {}
    clocks: Dict[int, SimulationClock] = {}
    for row in rows:
        clock = _extract_simulation_clock(row)
        if clock:
            clocks[row["zone_id"]] = clock
    return clocks


def _parse_time_spec(spec: str) -> Optional[time]:
    """Parse time spec like '08:00' or '14:30'."""
    try:
        parts = spec.split(":")
        if len(parts) == 2:
            return time(int(parts[0]), int(parts[1]))
    except Exception:
        pass
    return None


def _is_time_in_window(now: time, start_time: time, end_time: time) -> bool:
    """Check if time falls into a window, including midnight wrap."""
    if start_time == end_time:
        return True
    if start_time < end_time:
        return start_time <= now <= end_time
    return now >= start_time or now <= end_time


def _safe_positive_int(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def _extract_time_specs(value: Any) -> List[time]:
    if value is None:
        return []

    raw_items: List[Any] = []
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, list):
        raw_items = value
    elif isinstance(value, dict):
        if isinstance(value.get("times"), list):
            raw_items = value["times"]
        elif isinstance(value.get("time"), str):
            raw_items = [value["time"]]

    result: List[time] = []
    for item in raw_items:
        parsed = _parse_time_spec(str(item).strip())
        if parsed:
            result.append(parsed)
    return result


def _build_generic_task_schedules(
    *,
    zone_id: int,
    task_type: str,
    config: Dict[str, Any],
    schedule_spec: Any,
    targets: Dict[str, Any],
) -> List[Dict[str, Any]]:
    schedules: List[Dict[str, Any]] = []

    for t in _extract_time_specs(schedule_spec):
        schedules.append(
            {
                "zone_id": zone_id,
                "type": task_type,
                "time": t,
                "targets": targets,
                "config": config,
            }
        )

    interval_sec = _safe_positive_int(
        config.get("interval_sec")
        or config.get("every_sec")
        or config.get("interval")
    )
    if interval_sec > 0:
        schedules.append(
            {
                "zone_id": zone_id,
                "type": task_type,
                "interval_sec": interval_sec,
                "targets": targets,
                "config": config,
            }
        )

    return schedules


def _subsystem_enabled_from_targets(targets: Dict[str, Any], subsystem_key: str) -> Optional[bool]:
    if not isinstance(targets, dict):
        return None
    extensions = targets.get("extensions")
    if not isinstance(extensions, dict):
        return None
    subsystems = extensions.get("subsystems")
    if not isinstance(subsystems, dict):
        return None
    subsystem = subsystems.get(subsystem_key)
    if not isinstance(subsystem, dict):
        return None
    enabled = subsystem.get("enabled")
    if isinstance(enabled, bool):
        return enabled
    return None


def _is_task_schedule_enabled(*, task_type: str, targets: Dict[str, Any], config: Dict[str, Any]) -> bool:
    task_to_subsystem = {
        "irrigation": "irrigation",
        "lighting": "lighting",
        "ventilation": "climate",
        "diagnostics": "diagnostics",
        "solution_change": "solution_change",
    }
    subsystem_key = task_to_subsystem.get(task_type)
    if subsystem_key:
        enabled = _subsystem_enabled_from_targets(targets, subsystem_key)
        if enabled is False:
            return False

    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    if execution.get("force_skip") is True:
        return False
    if config.get("force_skip") is True:
        return False
    return True


async def get_active_schedules() -> List[Dict[str, Any]]:
    """Fetch active schedules from effective targets (GrowCycle)."""
    zone_rows = await fetch(
        """
        SELECT z.id as zone_id
        FROM zones z
        WHERE z.status IN ('online', 'warning', 'RUNNING', 'PAUSED')
        """
    )

    if not zone_rows:
        ACTIVE_SCHEDULES.set(0)
        await _emit_scheduler_diagnostic(
            reason="no_active_zones",
            message="Scheduler не нашел активных зон для построения расписаний",
            level="warning",
            alert_code="infra_scheduler_no_active_zones",
        )
        return []

    zone_ids = [row["zone_id"] for row in zone_rows]

    try:
        from repositories.laravel_api_repository import LaravelApiRepository

        laravel_api = LaravelApiRepository()
        effective_targets_batch = await laravel_api.get_effective_targets_batch(zone_ids)
    except Exception as e:
        logger.error(f"Failed to get effective targets from Laravel API: {e}")
        ACTIVE_SCHEDULES.set(0)
        await _emit_scheduler_diagnostic(
            reason="effective_targets_fetch_exception",
            message="Scheduler не смог получить effective targets из Laravel API",
            level="error",
            details={"error": str(e), "zone_ids_count": len(zone_ids)},
            alert_code="infra_scheduler_effective_targets_fetch_failed",
            error_type=type(e).__name__,
        )
        return []

    if not effective_targets_batch:
        ACTIVE_SCHEDULES.set(0)
        await _emit_scheduler_diagnostic(
            reason="effective_targets_empty_batch",
            message="Scheduler получил пустой effective-targets batch при наличии активных зон",
            level="error",
            details={"zone_ids_count": len(zone_ids)},
            alert_code="infra_scheduler_effective_targets_empty",
        )
        return []

    schedules: List[Dict[str, Any]] = []

    for zone_id in zone_ids:
        effective_targets = effective_targets_batch.get(zone_id)
        if not effective_targets or "error" in effective_targets:
            await _emit_scheduler_diagnostic(
                reason="effective_targets_missing_for_zone",
                message=f"Scheduler не получил effective targets для зоны {zone_id}",
                level="warning",
                zone_id=zone_id,
                details={"has_error": bool(effective_targets and "error" in effective_targets)},
                alert_code="infra_scheduler_effective_targets_missing_zone",
            )
            continue

        targets = effective_targets.get("targets", {})
        if not isinstance(targets, dict):
            await _emit_scheduler_diagnostic(
                reason="invalid_targets_payload",
                message=f"Scheduler получил некорректный targets payload для зоны {zone_id}",
                level="warning",
                zone_id=zone_id,
                details={"targets_type": str(type(targets))},
                alert_code="infra_scheduler_invalid_targets_payload",
            )
            continue

        # 1) Полив: explicit времена + interval
        irrigation = targets.get("irrigation", {}) if isinstance(targets.get("irrigation"), dict) else {}
        irrigation_schedule = targets.get("irrigation_schedule") or irrigation.get("schedule")
        if _is_task_schedule_enabled(task_type="irrigation", targets=targets, config=irrigation):
            irrigation_schedules = _build_generic_task_schedules(
                zone_id=zone_id,
                task_type="irrigation",
                config=irrigation,
                schedule_spec=irrigation_schedule,
                targets=targets,
            )
            schedules.extend(irrigation_schedules)

        # 2) Свет: окно photoperiod или legacy schedule
        lighting = targets.get("lighting", {}) if isinstance(targets.get("lighting"), dict) else {}
        photoperiod_hours = lighting.get("photoperiod_hours")
        start_time_str = lighting.get("start_time")
        lighting_interval_sec = _safe_positive_int(
            lighting.get("interval_sec")
            or lighting.get("every_sec")
            or lighting.get("interval")
        )

        if _is_task_schedule_enabled(task_type="lighting", targets=targets, config=lighting):
            if photoperiod_hours and start_time_str:
                start_t = _parse_time_spec(str(start_time_str))
                if start_t:
                    utc_today = utcnow().date()
                    end_time_dt = datetime.combine(utc_today, start_t) + timedelta(hours=float(photoperiod_hours))
                    schedule_item = {
                        "zone_id": zone_id,
                        "type": "lighting",
                        "start_time": start_t,
                        "end_time": end_time_dt.time(),
                        "targets": targets,
                        "config": lighting,
                    }
                    if lighting_interval_sec > 0:
                        schedule_item["interval_sec"] = lighting_interval_sec
                    schedules.append(schedule_item)
            else:
                lighting_schedule = targets.get("lighting_schedule")
                if isinstance(lighting_schedule, str) and "-" in lighting_schedule:
                    parts = lighting_schedule.split("-", 1)
                    start_t = _parse_time_spec(parts[0].strip())
                    end_t = _parse_time_spec(parts[1].strip())
                    if start_t and end_t:
                        schedule_item = {
                            "zone_id": zone_id,
                            "type": "lighting",
                            "start_time": start_t,
                            "end_time": end_t,
                            "targets": targets,
                            "config": lighting,
                        }
                        if lighting_interval_sec > 0:
                            schedule_item["interval_sec"] = lighting_interval_sec
                        schedules.append(schedule_item)
                else:
                    schedules.extend(
                        _build_generic_task_schedules(
                            zone_id=zone_id,
                            task_type="lighting",
                            config=lighting,
                            schedule_spec=lighting_schedule,
                            targets=targets,
                        )
                    )

        # 3) Generic abstract tasks
        generic_configs: List[Tuple[str, Dict[str, Any], Any]] = [
            (
                "ventilation",
                targets.get("ventilation", {}) if isinstance(targets.get("ventilation"), dict) else {},
                targets.get("ventilation_schedule"),
            ),
            (
                "solution_change",
                targets.get("solution_change", {}) if isinstance(targets.get("solution_change"), dict) else {},
                targets.get("solution_change_schedule"),
            ),
            (
                "mist",
                targets.get("mist", {}) if isinstance(targets.get("mist"), dict) else {},
                targets.get("mist_schedule"),
            ),
            (
                "diagnostics",
                targets.get("diagnostics", {}) if isinstance(targets.get("diagnostics"), dict) else {},
                targets.get("diagnostics_schedule"),
            ),
        ]

        for task_type, config, schedule_spec in generic_configs:
            if not _is_task_schedule_enabled(task_type=task_type, targets=targets, config=config):
                continue
            schedule_source = schedule_spec if schedule_spec is not None else config
            schedules.extend(
                _build_generic_task_schedules(
                    zone_id=zone_id,
                    task_type=task_type,
                    config=config,
                    schedule_spec=schedule_source,
                    targets=targets,
                )
            )

    ACTIVE_SCHEDULES.set(len(schedules))
    if not schedules:
        await _emit_scheduler_diagnostic(
            reason="no_executable_schedules",
            message="Scheduler не построил ни одного исполнимого расписания",
            level="warning",
            details={"zone_ids_count": len(zone_ids)},
            alert_code="infra_scheduler_no_executable_schedules",
        )
    return schedules


async def _should_run_interval_task(
    *,
    task_name: str,
    interval_sec: int,
    sim_clock: Optional[SimulationClock],
) -> bool:
    if interval_sec <= 0:
        return False
    try:
        rows = await fetch(
            """
            SELECT created_at
            FROM scheduler_logs
            WHERE task_name = $1 AND status IN ('completed', 'failed')
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            task_name,
        )
    except Exception as e:
        await _emit_scheduler_diagnostic(
            reason="interval_probe_failed",
            message=f"Scheduler не смог проверить время последнего выполнения {task_name}",
            level="error",
            details={"error": str(e), "interval_sec": interval_sec},
            alert_code="infra_scheduler_interval_probe_failed",
            error_type=type(e).__name__,
        )
        return False

    if not rows:
        return True

    last_completed = rows[0]["created_at"]
    if not isinstance(last_completed, datetime):
        return False

    now_real = utcnow().replace(tzinfo=None)
    elapsed_sec = (now_real - _to_naive_utc(last_completed)).total_seconds()
    required_real_sec = float(interval_sec)
    if sim_clock and sim_clock.time_scale > 0:
        required_real_sec = max(1.0, required_real_sec / sim_clock.time_scale)
    return elapsed_sec >= required_real_sec


def _build_schedule_key(zone_id: int, schedule: Dict[str, Any]) -> str:
    task_type = str(schedule.get("type") or "").strip().lower()
    trigger_bits = [
        f"time={schedule.get('time')}",
        f"start={schedule.get('start_time')}",
        f"end={schedule.get('end_time')}",
        f"interval={schedule.get('interval_sec')}",
    ]
    return f"zone:{zone_id}|type:{task_type}|{'|'.join(trigger_bits)}"


def _is_terminal_status(status: str) -> bool:
    return status in {"completed", "done", "failed", "rejected", "expired", "timeout", "error", "not_found"}


def _normalize_terminal_status(status: str) -> str:
    if status == "done":
        return "completed"
    if status == "error":
        return "failed"
    return status


def _update_deadline_violation_rate(task_type: str, terminal_status: str) -> None:
    normalized_task_type = str(task_type or "unknown")
    total = _TASK_TERMINAL_COUNTS.get(normalized_task_type, 0) + 1
    violations = _TASK_DEADLINE_VIOLATIONS.get(normalized_task_type, 0)
    if terminal_status in {"rejected", "expired"}:
        violations += 1

    _TASK_TERMINAL_COUNTS[normalized_task_type] = total
    _TASK_DEADLINE_VIOLATIONS[normalized_task_type] = violations
    TASK_DEADLINE_VIOLATION_RATE.labels(task_type=normalized_task_type).set(violations / max(total, 1))


def _extract_task_outcome_fields(status_payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = status_payload if isinstance(status_payload, dict) else {}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}

    action_required = payload.get("action_required")
    if not isinstance(action_required, bool):
        action_required = result.get("action_required") if isinstance(result.get("action_required"), bool) else None

    decision = payload.get("decision")
    if not isinstance(decision, str):
        decision = result.get("decision") if isinstance(result.get("decision"), str) else None

    reason_code = payload.get("reason_code")
    if not isinstance(reason_code, str):
        reason_code = result.get("reason_code") if isinstance(result.get("reason_code"), str) else None

    error_code = payload.get("error_code")
    if not isinstance(error_code, str):
        error_code = result.get("error_code") if isinstance(result.get("error_code"), str) else None

    error = payload.get("error")
    if not isinstance(error, str):
        error = result.get("error") if isinstance(result.get("error"), str) else None

    executed_steps = payload.get("executed_steps")
    if not isinstance(executed_steps, list):
        executed_steps = result.get("executed_steps") if isinstance(result.get("executed_steps"), list) else None

    safety_flags = payload.get("safety_flags")
    if not isinstance(safety_flags, list):
        safety_flags = result.get("safety_flags") if isinstance(result.get("safety_flags"), list) else None

    next_due_at = payload.get("next_due_at")
    if not isinstance(next_due_at, str):
        next_due_at = result.get("next_due_at") if isinstance(result.get("next_due_at"), str) else None

    measurements_before_after = payload.get("measurements_before_after")
    if not isinstance(measurements_before_after, dict):
        measurements_before_after = (
            result.get("measurements_before_after")
            if isinstance(result.get("measurements_before_after"), dict)
            else None
        )

    run_mode = payload.get("run_mode")
    if not isinstance(run_mode, str):
        run_mode = result.get("run_mode") if isinstance(result.get("run_mode"), str) else None

    retry_attempt = payload.get("retry_attempt")
    if not isinstance(retry_attempt, int):
        retry_attempt = result.get("retry_attempt") if isinstance(result.get("retry_attempt"), int) else None

    retry_max_attempts = payload.get("retry_max_attempts")
    if not isinstance(retry_max_attempts, int):
        retry_max_attempts = (
            result.get("retry_max_attempts")
            if isinstance(result.get("retry_max_attempts"), int)
            else None
        )

    retry_backoff_sec = payload.get("retry_backoff_sec")
    if not isinstance(retry_backoff_sec, int):
        retry_backoff_sec = (
            result.get("retry_backoff_sec")
            if isinstance(result.get("retry_backoff_sec"), int)
            else None
        )

    return {
        "action_required": action_required,
        "decision": decision,
        "reason_code": reason_code,
        "error_code": error_code,
        "error": error,
        "executed_steps": executed_steps,
        "safety_flags": safety_flags,
        "next_due_at": next_due_at,
        "measurements_before_after": measurements_before_after,
        "run_mode": run_mode,
        "retry_attempt": retry_attempt,
        "retry_max_attempts": retry_max_attempts,
        "retry_backoff_sec": retry_backoff_sec,
        "result": result if result else None,
    }


def _outcome_extended_fields(outcome: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "executed_steps": outcome.get("executed_steps"),
        "safety_flags": outcome.get("safety_flags"),
        "next_due_at": outcome.get("next_due_at"),
        "measurements_before_after": outcome.get("measurements_before_after"),
        "run_mode": outcome.get("run_mode"),
        "retry_attempt": outcome.get("retry_attempt"),
        "retry_max_attempts": outcome.get("retry_max_attempts"),
        "retry_backoff_sec": outcome.get("retry_backoff_sec"),
    }


def _parse_iso_datetime_utc(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return _to_naive_utc(parsed)


def _scheduler_headers() -> Dict[str, str]:
    if not get_trace_id():
        set_trace_id()
    headers = inject_trace_id_header()
    if SCHEDULER_API_TOKEN:
        headers["Authorization"] = f"Bearer {SCHEDULER_API_TOKEN}"
    headers["X-Scheduler-Id"] = SCHEDULER_ID
    if _bootstrap_lease_id:
        headers["X-Scheduler-Lease-Id"] = _bootstrap_lease_id
    return headers


def _build_scheduler_correlation_id(
    *,
    zone_id: int,
    task_type: str,
    scheduled_for: Optional[str],
    schedule_key: Optional[str],
) -> str:
    base = f"{zone_id}|{task_type}|{scheduled_for or ''}|{schedule_key or ''}"
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:20]
    return f"sch:z{zone_id}:{task_type}:{digest}"


def _compute_task_deadlines(scheduled_for: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    scheduled_dt = _parse_iso_datetime_utc(scheduled_for)
    if scheduled_dt is None:
        return None, None
    due_at = scheduled_dt + timedelta(seconds=SCHEDULER_DUE_GRACE_SEC)
    expires_at = scheduled_dt + timedelta(seconds=SCHEDULER_EXPIRES_AFTER_SEC)
    return due_at.isoformat(), expires_at.isoformat()


def _build_leader_lock_key(scope: str) -> int:
    normalized = (scope or "cluster:default").strip().lower()
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    key_unsigned = int.from_bytes(digest[:8], byteorder="big", signed=False)
    if key_unsigned >= (1 << 63):
        return key_unsigned - (1 << 64)
    return key_unsigned


_LEADER_LOCK_KEY = _build_leader_lock_key(SCHEDULER_LEADER_LOCK_SCOPE)


from app import bootstrap_sync as _bootstrap_sync_mod
from app import dispatch_service as _dispatch_service_mod
from app import internal_enqueue_service as _internal_enqueue_service_mod
from app import leader_election as _leader_election_mod
from app import reconcile_service as _reconcile_service_mod
from app import runtime_loop as _runtime_loop_mod
from domain import planning_engine as _planning_engine_mod


def _self_module():
    return sys.modules[__name__]


async def _load_pending_internal_enqueues() -> List[Dict[str, Any]]:
    return await _internal_enqueue_service_mod.load_pending_internal_enqueues(_self_module())


async def _mark_internal_enqueue_status(task_name: str, status: str, details: Dict[str, Any]) -> None:
    await _internal_enqueue_service_mod.mark_internal_enqueue_status(
        _self_module(),
        task_name,
        status,
        details,
    )


async def process_internal_enqueued_tasks(now_dt: datetime) -> None:
    await _internal_enqueue_service_mod.process_internal_enqueued_tasks(_self_module(), now_dt)


async def _transition_to_follower(*, now: datetime, reason: str, retry: bool) -> None:
    await _leader_election_mod.transition_to_follower(m=_self_module(), now=now, reason=reason, retry=retry)


async def release_scheduler_leader(reason: str = "shutdown") -> None:
    await _leader_election_mod.release_scheduler_leader(_self_module(), reason=reason)


async def ensure_scheduler_leader() -> bool:
    return await _leader_election_mod.ensure_scheduler_leader(_self_module())


async def ensure_scheduler_bootstrap_ready() -> bool:
    return await _bootstrap_sync_mod.ensure_scheduler_bootstrap_ready(_self_module())


async def send_scheduler_bootstrap_heartbeat() -> bool:
    return await _bootstrap_sync_mod.send_scheduler_bootstrap_heartbeat(_self_module())


async def submit_task_to_automation_engine(
    *,
    zone_id: int,
    task_type: str,
    payload: Optional[Dict[str, Any]] = None,
    scheduled_for: Optional[str] = None,
    correlation_id: Optional[str] = None,
    include_response_meta: bool = False,
) -> Optional[Union[str, Dict[str, Any]]]:
    return await _dispatch_service_mod.submit_task_to_automation_engine(
        _self_module(),
        zone_id=zone_id,
        task_type=task_type,
        payload=payload,
        scheduled_for=scheduled_for,
        correlation_id=correlation_id,
        include_response_meta=include_response_meta,
    )


async def wait_task_completion(
    *,
    zone_id: int,
    task_id: str,
    task_type: str,
    timeout_sec: float = SCHEDULER_TASK_TIMEOUT_SEC,
) -> Tuple[bool, str, Dict[str, Any]]:
    return await _reconcile_service_mod.wait_task_completion(
        _self_module(),
        zone_id=zone_id,
        task_id=task_id,
        task_type=task_type,
        timeout_sec=timeout_sec,
    )


async def _fetch_task_status_once(
    task_id: str,
    *,
    zone_id: Optional[int] = None,
    task_type: Optional[str] = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    return await _reconcile_service_mod.fetch_task_status_once(
        _self_module(),
        task_id,
        zone_id=zone_id,
        task_type=task_type,
    )


def _register_active_task(task_id: str, metadata: Dict[str, Any]) -> None:
    _reconcile_service_mod.register_active_task(_self_module(), task_id, metadata)


def _drop_active_task(task_id: str) -> None:
    _reconcile_service_mod.drop_active_task(_self_module(), task_id)


def _is_schedule_busy(schedule_key: str) -> bool:
    return _reconcile_service_mod.is_schedule_busy(_self_module(), schedule_key)


async def _zone_exists_preflight(zone_id: int) -> Optional[bool]:
    return await _reconcile_service_mod.zone_exists_preflight(_self_module(), zone_id)


async def _create_zone_event_safe(
    zone_id: int,
    event_type: str,
    payload: Dict[str, Any],
    *,
    task_id: Optional[str] = None,
    task_type: Optional[str] = None,
) -> bool:
    return await _reconcile_service_mod.create_zone_event_safe(
        _self_module(),
        zone_id,
        event_type,
        payload,
        task_id=task_id,
        task_type=task_type,
    )


async def recover_active_tasks_after_restart() -> int:
    return await _reconcile_service_mod.recover_active_tasks_after_restart(_self_module())


async def reconcile_active_tasks() -> None:
    await _reconcile_service_mod.reconcile_active_tasks(_self_module())


async def execute_scheduled_task(
    *,
    zone_id: int,
    schedule: Dict[str, Any],
    trigger_time: datetime,
    schedule_key: Optional[str] = None,
) -> bool:
    return await _dispatch_service_mod.execute_scheduled_task(
        _self_module(),
        zone_id=zone_id,
        schedule=schedule,
        trigger_time=trigger_time,
        schedule_key=schedule_key,
    )


async def check_and_execute_schedules(_unused: Any = None):
    await _planning_engine_mod.check_and_execute_schedules(_self_module(), _unused=_unused)


async def main():
    await _runtime_loop_mod.run_scheduler_main_loop(_self_module())


if __name__ == "__main__":
    asyncio.run(main())
