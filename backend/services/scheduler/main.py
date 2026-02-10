import asyncio
import hashlib
import logging
import os
import socket
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from common.db import create_scheduler_log, create_zone_event, fetch
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
SCHEDULER_ACTIVE_TASKS = Gauge(
    "scheduler_active_tasks",
    "Current number of active abstract scheduler tasks",
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
SCHEDULER_MAIN_TICK_SEC = max(1.0, float(os.getenv("SCHEDULER_MAIN_TICK_SEC", "5")))
SCHEDULER_DISPATCH_INTERVAL_SEC = max(1.0, float(os.getenv("SCHEDULER_DISPATCH_INTERVAL_SEC", "60")))

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

# Временное хранилище последнего тика per zone (для sim-time пересечений)
_LAST_SCHEDULE_CHECKS: Dict[int, datetime] = {}
_ACTIVE_TASKS: Dict[str, Dict[str, Any]] = {}
_ACTIVE_SCHEDULE_TASKS: Dict[str, str] = {}
_WINDOW_LAST_STATE: Dict[str, bool] = {}
_INTERNAL_ENQUEUE_TASK_NAME_PREFIX = "ae_internal_enqueue_"
_INTERNAL_ENQUEUE_SCAN_LIMIT = max(50, int(os.getenv("SCHEDULER_INTERNAL_ENQUEUE_SCAN_LIMIT", "500")))

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


def _get_last_check(zone_id: int, now_dt: datetime, sim_clock: Optional[SimulationClock]) -> datetime:
    last_check = _LAST_SCHEDULE_CHECKS.get(zone_id)
    if last_check is not None:
        return last_check
    delta_seconds = 60.0
    if sim_clock:
        delta_seconds *= sim_clock.time_scale
    return now_dt - timedelta(seconds=delta_seconds)


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

        if photoperiod_hours and start_time_str:
            start_t = _parse_time_spec(str(start_time_str))
            if start_t:
                end_time_dt = datetime.combine(datetime.today(), start_t) + timedelta(hours=float(photoperiod_hours))
                schedules.append(
                    {
                        "zone_id": zone_id,
                        "type": "lighting",
                        "start_time": start_t,
                        "end_time": end_time_dt.time(),
                        "targets": targets,
                        "config": lighting,
                    }
                )
        else:
            lighting_schedule = targets.get("lighting_schedule")
            if isinstance(lighting_schedule, str) and "-" in lighting_schedule:
                parts = lighting_schedule.split("-", 1)
                start_t = _parse_time_spec(parts[0].strip())
                end_t = _parse_time_spec(parts[1].strip())
                if start_t and end_t:
                    schedules.append(
                        {
                            "zone_id": zone_id,
                            "type": "lighting",
                            "start_time": start_t,
                            "end_time": end_t,
                            "targets": targets,
                            "config": lighting,
                        }
                    )
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
            WHERE task_name = $1 AND status = 'completed'
            ORDER BY created_at DESC
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
    return status in {"completed", "done", "failed", "rejected", "timeout", "error", "not_found"}


def _normalize_terminal_status(status: str) -> str:
    if status == "done":
        return "completed"
    if status == "error":
        return "failed"
    return status


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
    headers = inject_trace_id_header()
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


async def _load_pending_internal_enqueues() -> List[Dict[str, Any]]:
    try:
        rows = await fetch(
            """
            SELECT DISTINCT ON (task_name)
                task_name, status, details, created_at
            FROM scheduler_logs
            WHERE task_name LIKE $1
            ORDER BY task_name, created_at DESC, id DESC
            LIMIT $2
            """,
            f"{_INTERNAL_ENQUEUE_TASK_NAME_PREFIX}%",
            _INTERNAL_ENQUEUE_SCAN_LIMIT,
        )
    except Exception as exc:
        await _emit_scheduler_diagnostic(
            reason="internal_enqueue_load_failed",
            message="Scheduler не смог загрузить internal enqueue задачи",
            level="error",
            details={"error": str(exc)},
            alert_code="infra_scheduler_internal_enqueue_load_failed",
            error_type=type(exc).__name__,
        )
        return []

    pending: List[Dict[str, Any]] = []
    for row in rows:
        if str(row.get("status") or "").lower() != "pending":
            continue
        details = row.get("details")
        if not isinstance(details, dict):
            continue
        pending.append(details)
    return pending


async def _mark_internal_enqueue_status(task_name: str, status: str, details: Dict[str, Any]) -> None:
    payload = dict(details)
    payload["status"] = status
    payload["updated_at"] = utcnow().replace(tzinfo=None).isoformat()
    await create_scheduler_log(task_name, status, payload)


async def process_internal_enqueued_tasks(now_dt: datetime) -> None:
    pending = await _load_pending_internal_enqueues()
    for item in pending:
        enqueue_id = str(item.get("enqueue_id") or "").strip()
        task_name = f"{_INTERNAL_ENQUEUE_TASK_NAME_PREFIX}{enqueue_id}" if enqueue_id else ""
        if not task_name:
            continue

        zone_id_raw = item.get("zone_id")
        task_type = str(item.get("task_type") or "").strip().lower()
        try:
            zone_id = int(zone_id_raw)
        except (TypeError, ValueError):
            await _mark_internal_enqueue_status(task_name, "failed", {**item, "error": "invalid_zone_id"})
            continue
        if task_type not in SUPPORTED_TASK_TYPES:
            await _mark_internal_enqueue_status(task_name, "failed", {**item, "error": "unsupported_task_type"})
            continue

        scheduled_for = str(item.get("scheduled_for") or "").strip() or now_dt.isoformat()
        scheduled_for_dt = _parse_iso_datetime_utc(scheduled_for) or now_dt
        if scheduled_for_dt > now_dt:
            continue

        expires_at_raw = item.get("expires_at")
        expires_at_dt = _parse_iso_datetime_utc(str(expires_at_raw)) if expires_at_raw else None
        if expires_at_dt and now_dt > expires_at_dt:
            await _mark_internal_enqueue_status(task_name, "expired", {**item, "error": "expired_before_dispatch"})
            await create_zone_event(
                zone_id,
                "SELF_TASK_EXPIRED",
                {
                    "enqueue_id": enqueue_id,
                    "task_type": task_type,
                    "scheduled_for": scheduled_for,
                    "expires_at": expires_at_dt.isoformat(),
                },
            )
            continue

        schedule = {
            "type": task_type,
            "targets": (item.get("payload") or {}).get("targets", {}) if isinstance(item.get("payload"), dict) else {},
            "config": (item.get("payload") or {}).get("config", {}) if isinstance(item.get("payload"), dict) else {},
            "payload": item.get("payload") if isinstance(item.get("payload"), dict) else {},
            "correlation_id": item.get("correlation_id"),
        }
        schedule_key = f"internal_enqueue:{enqueue_id}"
        dispatched = await execute_scheduled_task(
            zone_id=zone_id,
            schedule=schedule,
            trigger_time=scheduled_for_dt,
            schedule_key=schedule_key,
        )
        if not dispatched:
            await _mark_internal_enqueue_status(task_name, "failed", {**item, "error": "dispatch_failed"})
            await create_zone_event(
                zone_id,
                "SELF_TASK_DISPATCH_FAILED",
                {
                    "enqueue_id": enqueue_id,
                    "task_type": task_type,
                    "scheduled_for": scheduled_for,
                },
            )
            continue

        active_task_id = _ACTIVE_SCHEDULE_TASKS.get(schedule_key)
        await _mark_internal_enqueue_status(
            task_name,
            "dispatched",
            {
                **item,
                "task_id": active_task_id,
                "scheduled_for": scheduled_for_dt.isoformat(),
            },
        )
        await create_zone_event(
            zone_id,
            "SELF_TASK_DISPATCHED",
            {
                "enqueue_id": enqueue_id,
                "task_id": active_task_id,
                "task_type": task_type,
                "scheduled_for": scheduled_for_dt.isoformat(),
            },
        )


def _mark_bootstrap_wait(now: datetime, retry: bool = True) -> None:
    global _bootstrap_ready, _bootstrap_lease_id, _bootstrap_next_heartbeat_at, _bootstrap_lease_expires_at, _bootstrap_next_attempt_at, _bootstrap_retry_idx
    _bootstrap_ready = False
    _bootstrap_lease_id = None
    _bootstrap_next_heartbeat_at = None
    _bootstrap_lease_expires_at = None
    if retry:
        backoff = _BOOTSTRAP_BACKOFF_STEPS_SEC[min(_bootstrap_retry_idx, len(_BOOTSTRAP_BACKOFF_STEPS_SEC) - 1)]
        _bootstrap_next_attempt_at = now + timedelta(seconds=backoff)
        _bootstrap_retry_idx = min(_bootstrap_retry_idx + 1, len(_BOOTSTRAP_BACKOFF_STEPS_SEC) - 1)


async def ensure_scheduler_bootstrap_ready() -> bool:
    global _bootstrap_ready, _bootstrap_lease_id, _bootstrap_lease_ttl_sec, _bootstrap_poll_interval_sec
    global _bootstrap_next_attempt_at, _bootstrap_next_heartbeat_at, _bootstrap_lease_expires_at, _bootstrap_retry_idx

    now = utcnow().replace(tzinfo=None)
    if _bootstrap_ready and _bootstrap_lease_expires_at and now < _bootstrap_lease_expires_at:
        return True
    if _bootstrap_next_attempt_at and now < _bootstrap_next_attempt_at:
        return False

    payload = {
        "scheduler_id": SCHEDULER_ID,
        "scheduler_version": SCHEDULER_VERSION,
        "protocol_version": SCHEDULER_PROTOCOL_VERSION,
        "started_at": now.isoformat(),
        "capabilities": {"task_types": sorted(SUPPORTED_TASK_TYPES)},
    }

    headers = inject_trace_id_header()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{AUTOMATION_ENGINE_URL}/scheduler/bootstrap",
                json=payload,
                headers=headers,
            )
    except Exception as exc:
        COMMAND_REST_ERRORS.labels(error_type="bootstrap_request_error").inc()
        await _emit_scheduler_diagnostic(
            reason="scheduler_bootstrap_request_error",
            message="Scheduler не смог выполнить bootstrap в automation-engine",
            level="error",
            details={"error": str(exc)},
            alert_code="infra_scheduler_bootstrap_failed",
            error_type=type(exc).__name__,
        )
        _mark_bootstrap_wait(now, retry=True)
        return False

    if response.status_code != 200:
        COMMAND_REST_ERRORS.labels(error_type=f"bootstrap_http_{response.status_code}").inc()
        await _emit_scheduler_diagnostic(
            reason="scheduler_bootstrap_http_error",
            message=f"Scheduler получил HTTP {response.status_code} на bootstrap",
            level="error",
            details={"response": response.text[:300]},
            alert_code="infra_scheduler_bootstrap_failed",
            error_type=f"http_{response.status_code}",
        )
        _mark_bootstrap_wait(now, retry=True)
        return False

    body = response.json() if response.content else {}
    data = body.get("data") if isinstance(body, dict) else {}
    bootstrap_status = str(data.get("bootstrap_status") or "").lower()

    _bootstrap_lease_ttl_sec = max(10, int(data.get("lease_ttl_sec") or _bootstrap_lease_ttl_sec))
    _bootstrap_poll_interval_sec = max(1, int(data.get("poll_interval_sec") or _bootstrap_poll_interval_sec))

    if bootstrap_status == "ready":
        lease_id = data.get("lease_id")
        if not isinstance(lease_id, str) or not lease_id.strip():
            await _emit_scheduler_diagnostic(
                reason="scheduler_bootstrap_missing_lease",
                message="Scheduler получил bootstrap_status=ready без lease_id",
                level="error",
                details={"body": body},
                alert_code="infra_scheduler_bootstrap_failed",
                error_type="missing_lease_id",
            )
            _mark_bootstrap_wait(now, retry=True)
            return False

        _bootstrap_ready = True
        _bootstrap_lease_id = lease_id
        _bootstrap_lease_expires_at = now + timedelta(seconds=_bootstrap_lease_ttl_sec)
        _bootstrap_next_heartbeat_at = now + timedelta(seconds=max(1, _bootstrap_lease_ttl_sec // 2))
        _bootstrap_next_attempt_at = None
        _bootstrap_retry_idx = 0
        send_service_log(
            service="scheduler",
            level="info",
            message="Scheduler bootstrap completed",
            context={
                "scheduler_id": SCHEDULER_ID,
                "lease_id": lease_id,
                "lease_ttl_sec": _bootstrap_lease_ttl_sec,
                "poll_interval_sec": _bootstrap_poll_interval_sec,
            },
        )
        return True

    level = "critical" if bootstrap_status == "deny" else "warning"
    await _emit_scheduler_diagnostic(
        reason=f"scheduler_bootstrap_{bootstrap_status or 'unknown'}",
        message=f"Scheduler bootstrap status: {bootstrap_status or 'unknown'}",
        level=level,
        details={"body": body},
        alert_code="infra_scheduler_bootstrap_not_ready",
        error_type=bootstrap_status or "unknown",
    )
    _mark_bootstrap_wait(now, retry=True)
    return False


async def send_scheduler_bootstrap_heartbeat() -> bool:
    global _bootstrap_ready, _bootstrap_next_heartbeat_at, _bootstrap_lease_expires_at

    now = utcnow().replace(tzinfo=None)
    if not _bootstrap_ready:
        return False
    if _bootstrap_next_heartbeat_at and now < _bootstrap_next_heartbeat_at:
        return True
    if not _bootstrap_lease_id:
        _mark_bootstrap_wait(now, retry=True)
        return False

    headers = inject_trace_id_header()
    payload = {"scheduler_id": SCHEDULER_ID, "lease_id": _bootstrap_lease_id}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{AUTOMATION_ENGINE_URL}/scheduler/bootstrap/heartbeat",
                json=payload,
                headers=headers,
            )
    except Exception as exc:
        COMMAND_REST_ERRORS.labels(error_type="bootstrap_heartbeat_request_error").inc()
        await _emit_scheduler_diagnostic(
            reason="scheduler_bootstrap_heartbeat_error",
            message="Scheduler не смог отправить bootstrap heartbeat",
            level="error",
            details={"error": str(exc)},
            alert_code="infra_scheduler_bootstrap_heartbeat_failed",
            error_type=type(exc).__name__,
        )
        _mark_bootstrap_wait(now, retry=True)
        return False

    if response.status_code != 200:
        COMMAND_REST_ERRORS.labels(error_type=f"bootstrap_heartbeat_http_{response.status_code}").inc()
        _mark_bootstrap_wait(now, retry=True)
        return False

    body = response.json() if response.content else {}
    data = body.get("data") if isinstance(body, dict) else {}
    status = str(data.get("bootstrap_status") or "").lower()
    if status != "ready":
        _mark_bootstrap_wait(now, retry=True)
        return False

    _bootstrap_lease_expires_at = now + timedelta(seconds=max(10, int(data.get("lease_ttl_sec") or _bootstrap_lease_ttl_sec)))
    _bootstrap_next_heartbeat_at = now + timedelta(seconds=max(1, _bootstrap_lease_ttl_sec // 2))
    return True


async def submit_task_to_automation_engine(
    *,
    zone_id: int,
    task_type: str,
    payload: Optional[Dict[str, Any]] = None,
    scheduled_for: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Optional[str]:
    created_trace = False
    if not get_trace_id():
        set_trace_id()
        created_trace = True

    try:
        effective_correlation_id = correlation_id or _build_scheduler_correlation_id(
            zone_id=zone_id,
            task_type=task_type,
            scheduled_for=scheduled_for,
            schedule_key=(payload or {}).get("schedule_key") if isinstance(payload, dict) else None,
        )
        req_payload: Dict[str, Any] = {
            "zone_id": zone_id,
            "task_type": task_type,
            "payload": payload or {},
            "correlation_id": effective_correlation_id,
        }
        if scheduled_for:
            req_payload["scheduled_for"] = scheduled_for
        due_at, expires_at = _compute_task_deadlines(scheduled_for)
        if due_at:
            req_payload["due_at"] = due_at
        if expires_at:
            req_payload["expires_at"] = expires_at

        headers = _scheduler_headers()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{AUTOMATION_ENGINE_URL}/scheduler/task",
                json=req_payload,
                headers=headers,
            )

        if response.status_code not in (200, 202):
            COMMAND_REST_ERRORS.labels(error_type=f"http_{response.status_code}").inc()
            await _emit_scheduler_diagnostic(
                reason="task_submit_http_error",
                message=(
                    f"Scheduler получил HTTP {response.status_code} при отправке "
                    f"абстрактной задачи {task_type} для зоны {zone_id}"
                ),
                level="error",
                zone_id=zone_id,
                details={
                    "task_type": task_type,
                    "response": response.text[:300],
                    "correlation_id": effective_correlation_id,
                },
                alert_code="infra_scheduler_task_submit_failed",
                error_type=f"http_{response.status_code}",
            )
            return None

        body = response.json()
        data = body.get("data") if isinstance(body, dict) else None
        task_id = data.get("task_id") if isinstance(data, dict) else None
        if not task_id:
            COMMAND_REST_ERRORS.labels(error_type="task_id_missing").inc()
            await _emit_scheduler_diagnostic(
                reason="task_submit_missing_task_id",
                message=f"Scheduler не получил task_id для задачи {task_type} зоны {zone_id}",
                level="error",
                zone_id=zone_id,
                details={"task_type": task_type, "body": body, "correlation_id": effective_correlation_id},
                alert_code="infra_scheduler_task_submit_failed",
                error_type="TaskIdMissing",
            )
            return None

        await record_simulation_event(
            zone_id,
            service="scheduler",
            stage="task_submit",
            status="accepted",
            message="Абстрактная задача передана в automation-engine",
            payload={"task_id": task_id, "task_type": task_type, "correlation_id": effective_correlation_id},
        )
        return str(task_id)

    except httpx.TimeoutException as e:
        COMMAND_REST_ERRORS.labels(error_type="timeout").inc()
        await _emit_scheduler_diagnostic(
            reason="task_submit_timeout",
            message=f"Scheduler получил таймаут при отправке задачи {task_type} для зоны {zone_id}",
            level="error",
            zone_id=zone_id,
            details={"task_type": task_type, "error": str(e), "correlation_id": effective_correlation_id},
            alert_code="infra_scheduler_task_submit_timeout",
            error_type="timeout",
        )
        return None
    except Exception as e:
        COMMAND_REST_ERRORS.labels(error_type=type(e).__name__).inc()
        await send_infra_exception_alert(
            error=e,
            code="infra_unknown_error",
            alert_type="Scheduler Task Submit Unexpected Error",
            severity="error",
            zone_id=zone_id,
            service="scheduler",
            component="task_dispatch",
            error_type=type(e).__name__,
            details={"task_type": task_type, "correlation_id": effective_correlation_id},
        )
        return None
    finally:
        if created_trace:
            clear_trace_id()


async def wait_task_completion(
    *,
    zone_id: int,
    task_id: str,
    task_type: str,
    timeout_sec: float = SCHEDULER_TASK_TIMEOUT_SEC,
) -> Tuple[bool, str, Dict[str, Any]]:
    created_trace = False
    if not get_trace_id():
        set_trace_id()
        created_trace = True

    deadline = utcnow().timestamp() + timeout_sec
    headers = _scheduler_headers()

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            while utcnow().timestamp() < deadline:
                try:
                    response = await client.get(
                        f"{AUTOMATION_ENGINE_URL}/scheduler/task/{task_id}",
                        headers=headers,
                    )
                except httpx.TimeoutException:
                    COMMAND_REST_ERRORS.labels(error_type="task_status_timeout").inc()
                    await asyncio.sleep(SCHEDULER_TASK_POLL_INTERVAL_SEC)
                    continue
                except Exception as exc:
                    COMMAND_REST_ERRORS.labels(error_type="task_status_request_error").inc()
                    await _emit_scheduler_diagnostic(
                        reason="task_status_request_failed",
                        message=(
                            f"Scheduler не смог получить статус задачи {task_type} "
                            f"({task_id}) для зоны {zone_id}"
                        ),
                        level="error",
                        zone_id=zone_id,
                        details={"task_id": task_id, "error": str(exc)},
                        alert_code="infra_scheduler_task_status_failed",
                        error_type=type(exc).__name__,
                    )
                    return False, "status_request_failed", {}

                if response.status_code == 404:
                    return False, "not_found", {}
                if response.status_code != 200:
                    COMMAND_REST_ERRORS.labels(error_type=f"task_status_http_{response.status_code}").inc()
                    await asyncio.sleep(SCHEDULER_TASK_POLL_INTERVAL_SEC)
                    continue

                body = response.json() if response.content else {}
                data = body.get("data") if isinstance(body, dict) else {}
                status = str(data.get("status") or "").lower()
                status_payload = data if isinstance(data, dict) else {}

                if status in {"completed", "done"}:
                    return True, "completed", status_payload
                if status in {"failed", "rejected", "timeout", "error"}:
                    return False, status, status_payload

                await asyncio.sleep(SCHEDULER_TASK_POLL_INTERVAL_SEC)

        return False, "timeout", {}
    finally:
        if created_trace:
            clear_trace_id()


async def _fetch_task_status_once(task_id: str) -> Tuple[Optional[str], Dict[str, Any]]:
    headers = _scheduler_headers()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{AUTOMATION_ENGINE_URL}/scheduler/task/{task_id}",
                headers=headers,
            )
    except httpx.TimeoutException:
        COMMAND_REST_ERRORS.labels(error_type="task_status_timeout").inc()
        return None, {}
    except Exception as exc:
        COMMAND_REST_ERRORS.labels(error_type="task_status_request_error").inc()
        logger.warning("Scheduler task status request failed: task_id=%s error=%s", task_id, exc, exc_info=True)
        return None, {}

    if response.status_code == 404:
        return "not_found", {}
    if response.status_code != 200:
        COMMAND_REST_ERRORS.labels(error_type=f"task_status_http_{response.status_code}").inc()
        return None, {}

    body = response.json() if response.content else {}
    data = body.get("data") if isinstance(body, dict) else {}
    status = str(data.get("status") or "").lower()
    return status or None, data if isinstance(data, dict) else {}


def _register_active_task(task_id: str, metadata: Dict[str, Any]) -> None:
    _ACTIVE_TASKS[task_id] = metadata
    schedule_key = str(metadata.get("schedule_key") or "")
    if schedule_key:
        _ACTIVE_SCHEDULE_TASKS[schedule_key] = task_id
    SCHEDULER_ACTIVE_TASKS.set(len(_ACTIVE_TASKS))


def _drop_active_task(task_id: str) -> None:
    metadata = _ACTIVE_TASKS.pop(task_id, None)
    if metadata:
        schedule_key = str(metadata.get("schedule_key") or "")
        if schedule_key and _ACTIVE_SCHEDULE_TASKS.get(schedule_key) == task_id:
            _ACTIVE_SCHEDULE_TASKS.pop(schedule_key, None)
    SCHEDULER_ACTIVE_TASKS.set(len(_ACTIVE_TASKS))


def _is_schedule_busy(schedule_key: str) -> bool:
    task_id = _ACTIVE_SCHEDULE_TASKS.get(schedule_key)
    return bool(task_id and task_id in _ACTIVE_TASKS)


async def reconcile_active_tasks() -> None:
    if not _ACTIVE_TASKS:
        SCHEDULER_ACTIVE_TASKS.set(0)
        return

    now = utcnow().replace(tzinfo=None)
    for task_id, metadata in list(_ACTIVE_TASKS.items()):
        zone_id = int(metadata.get("zone_id") or 0)
        task_type = str(metadata.get("task_type") or "unknown")
        task_name = str(metadata.get("task_name") or f"{task_type}_zone_{zone_id}")
        accepted_at = metadata.get("accepted_at")
        accepted_dt = accepted_at if isinstance(accepted_at, datetime) else now

        status, status_payload = await _fetch_task_status_once(task_id)

        if status is None:
            elapsed = max(0.0, (now - accepted_dt).total_seconds())
            if elapsed >= SCHEDULER_TASK_TIMEOUT_SEC:
                status = "timeout"
            else:
                continue

        if not _is_terminal_status(status):
            continue

        terminal_status = _normalize_terminal_status(status)
        completion_elapsed = max(0.0, (now - accepted_dt).total_seconds())
        SCHEDULER_TASK_COMPLETION_LATENCY_SEC.labels(task_type=task_type, status=terminal_status).observe(completion_elapsed)

        if terminal_status == "completed":
            SCHEDULE_EXECUTIONS.labels(zone_id=zone_id, task_type=task_type).inc()
            SCHEDULER_TASK_STATUS.labels(task_type=task_type, status="completed").inc()
            await create_scheduler_log(
                task_name,
                "completed",
                {
                    "zone_id": zone_id,
                    "task_type": task_type,
                    "task_id": task_id,
                    "status": terminal_status,
                    "status_payload": status_payload,
                },
            )
            await create_zone_event(
                zone_id,
                "SCHEDULE_TASK_COMPLETED",
                {"task_type": task_type, "task_id": task_id, "status": terminal_status},
            )
        else:
            final_status = terminal_status or "failed"
            SCHEDULER_TASK_STATUS.labels(task_type=task_type, status=final_status).inc()
            await create_scheduler_log(
                task_name,
                "failed",
                {
                    "zone_id": zone_id,
                    "task_type": task_type,
                    "task_id": task_id,
                    "status": final_status,
                    "status_payload": status_payload,
                },
            )
            await create_zone_event(
                zone_id,
                "SCHEDULE_TASK_FAILED",
                {"task_type": task_type, "task_id": task_id, "status": final_status},
            )

        _drop_active_task(task_id)


async def execute_scheduled_task(
    *,
    zone_id: int,
    schedule: Dict[str, Any],
    trigger_time: datetime,
    schedule_key: Optional[str] = None,
) -> bool:
    task_type = str(schedule.get("type") or "").strip().lower()
    if task_type not in SUPPORTED_TASK_TYPES:
        await _emit_scheduler_diagnostic(
            reason="unsupported_task_type",
            message=f"Scheduler получил неподдерживаемый task_type={task_type} для зоны {zone_id}",
            level="warning",
            zone_id=zone_id,
            details={"schedule": schedule},
            alert_code="infra_scheduler_unsupported_task_type",
        )
        return False

    task_name = f"{task_type}_zone_{zone_id}"
    normalized_key = schedule_key or _build_schedule_key(zone_id, schedule)
    if _is_schedule_busy(normalized_key):
        return False

    await create_scheduler_log(
        task_name,
        "running",
        {
            "zone_id": zone_id,
            "task_type": task_type,
            "trigger_time": trigger_time.isoformat(),
            "schedule_key": normalized_key,
        },
    )

    schedule_payload = schedule.get("payload") if isinstance(schedule.get("payload"), dict) else {}
    payload: Dict[str, Any] = dict(schedule_payload)
    payload.setdefault("targets", schedule.get("targets") or {})
    payload.setdefault("config", schedule.get("config") or {})
    payload["trigger_time"] = trigger_time.isoformat()
    payload["schedule_key"] = normalized_key

    if task_type == "lighting" and schedule.get("start_time") and schedule.get("end_time"):
        now_t = trigger_time.time()
        start_t = schedule.get("start_time")
        end_t = schedule.get("end_time")
        desired_state = _is_time_in_window(now_t, start_t, end_t)
        payload.update(
            {
                "desired_state": desired_state,
                "start_time": start_t.isoformat(),
                "end_time": end_t.isoformat(),
            }
        )

    submitted_at = utcnow().replace(tzinfo=None)
    preset_correlation_id = str(schedule.get("correlation_id") or "").strip()
    correlation_id = preset_correlation_id or _build_scheduler_correlation_id(
        zone_id=zone_id,
        task_type=task_type,
        scheduled_for=trigger_time.isoformat(),
        schedule_key=normalized_key,
    )
    task_id = await submit_task_to_automation_engine(
        zone_id=zone_id,
        task_type=task_type,
        payload=payload,
        scheduled_for=trigger_time.isoformat(),
        correlation_id=correlation_id,
    )
    accepted_at = utcnow().replace(tzinfo=None)

    if not task_id:
        SCHEDULER_TASK_STATUS.labels(task_type=task_type, status="submit_failed").inc()
        await create_scheduler_log(
            task_name,
            "failed",
            {
                "zone_id": zone_id,
                "task_type": task_type,
                "error": "submit_failed",
                "schedule_key": normalized_key,
            },
        )
        await create_zone_event(
            zone_id,
            "SCHEDULE_TASK_FAILED",
            {
                "task_type": task_type,
                "reason": "submit_failed",
                "correlation_id": correlation_id,
            },
        )
        return False

    SCHEDULER_TASK_ACCEPT_LATENCY_SEC.labels(task_type=task_type).observe(
        max(0.0, (accepted_at - submitted_at).total_seconds())
    )

    await create_zone_event(
        zone_id,
        "SCHEDULE_TASK_ACCEPTED",
        {
            "task_type": task_type,
            "task_id": task_id,
            "trigger_time": trigger_time.isoformat(),
            "schedule_key": normalized_key,
            "correlation_id": correlation_id,
        },
    )
    _register_active_task(
        task_id,
        {
            "zone_id": zone_id,
            "task_type": task_type,
            "task_name": task_name,
            "accepted_at": accepted_at,
            "schedule_key": normalized_key,
            "correlation_id": correlation_id,
        },
    )
    return True


async def check_and_execute_schedules(_unused: Any = None):
    """Check schedules and submit abstract tasks to automation-engine."""
    await reconcile_active_tasks()
    now_for_internal = utcnow().replace(tzinfo=None)
    await process_internal_enqueued_tasks(now_for_internal)
    schedules = await get_active_schedules()
    zone_ids = sorted({schedule["zone_id"] for schedule in schedules})
    simulation_clocks = await get_simulation_clocks(zone_ids)

    real_now = datetime.now()
    executed: set = set()
    observed_window_keys: set = set()
    zone_now: Dict[int, datetime] = {}
    zone_last: Dict[int, datetime] = {}

    for schedule in schedules:
        zone_id = schedule["zone_id"]
        task_type = schedule["type"]

        key = _build_schedule_key(zone_id, schedule)
        if key in executed:
            continue

        sim_clock = simulation_clocks.get(zone_id)
        if zone_id not in zone_now:
            now_dt = sim_clock.now() if sim_clock else real_now
            zone_now[zone_id] = now_dt
            zone_last[zone_id] = _get_last_check(zone_id, now_dt, sim_clock)

        now_dt = zone_now[zone_id]
        last_dt = zone_last[zone_id]

        interval_sec = _safe_positive_int(schedule.get("interval_sec"))
        task_name = f"{task_type}_zone_{zone_id}"

        if interval_sec > 0:
            should_run = await _should_run_interval_task(
                task_name=task_name,
                interval_sec=interval_sec,
                sim_clock=sim_clock,
            )
            if should_run:
                dispatched = await execute_scheduled_task(
                    zone_id=zone_id,
                    schedule=schedule,
                    trigger_time=now_dt,
                    schedule_key=key,
                )
                if dispatched:
                    executed.add(key)
            continue

        schedule_time = schedule.get("time")
        if schedule_time:
            crossings = _schedule_crossings(last_dt, now_dt, schedule_time)
            for trigger_time in crossings:
                await execute_scheduled_task(
                    zone_id=zone_id,
                    schedule=schedule,
                    trigger_time=trigger_time,
                    schedule_key=key,
                )
            if crossings:
                executed.add(key)
            continue

        # Окно (например свет): dispatch только при смене desired_state.
        if schedule.get("start_time") and schedule.get("end_time"):
            observed_window_keys.add(key)
            desired_state = _is_time_in_window(
                now_dt.time(),
                schedule["start_time"],
                schedule["end_time"],
            )
            last_state = _WINDOW_LAST_STATE.get(key)
            if last_state is None or last_state != desired_state:
                dispatched = await execute_scheduled_task(
                    zone_id=zone_id,
                    schedule=schedule,
                    trigger_time=now_dt,
                    schedule_key=key,
                )
                if dispatched:
                    _WINDOW_LAST_STATE[key] = desired_state
            executed.add(key)
            continue

        await _emit_scheduler_diagnostic(
            reason="schedule_without_trigger",
            message=f"Scheduler пропустил задачу {task_type} зоны {zone_id}: отсутствует trigger",
            level="warning",
            zone_id=zone_id,
            details={"schedule": schedule},
            alert_code="infra_scheduler_schedule_without_trigger",
        )

    for zone_id, now_dt in zone_now.items():
        _LAST_SCHEDULE_CHECKS[zone_id] = now_dt

    for stale_key in list(_WINDOW_LAST_STATE.keys()):
        if stale_key not in observed_window_keys:
            _WINDOW_LAST_STATE.pop(stale_key, None)


async def main():
    start_http_server(9402)  # Prometheus metrics
    send_service_log(
        service="scheduler",
        level="info",
        message="Scheduler service started",
        context={"port": 9402, "mode": "planner-only"},
    )
    last_dispatch_at: Optional[datetime] = None

    while True:
        try:
            ready = await ensure_scheduler_bootstrap_ready()
            await send_scheduler_bootstrap_heartbeat()
            now = utcnow().replace(tzinfo=None)
            should_dispatch = False
            if ready:
                if last_dispatch_at is None:
                    should_dispatch = True
                else:
                    elapsed = (now - last_dispatch_at).total_seconds()
                    should_dispatch = elapsed >= SCHEDULER_DISPATCH_INTERVAL_SEC
            if should_dispatch:
                await check_and_execute_schedules()
                last_dispatch_at = now
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down")
            break
        except Exception as e:
            logger.exception(f"Error in scheduler main loop: {e}")
            send_service_log(
                service="scheduler",
                level="error",
                message="Error in scheduler main loop",
                context={"error": str(e)},
            )
            await asyncio.sleep(max(1.0, SCHEDULER_MAIN_TICK_SEC))

        await asyncio.sleep(max(1.0, SCHEDULER_MAIN_TICK_SEC))


if __name__ == "__main__":
    asyncio.run(main())
