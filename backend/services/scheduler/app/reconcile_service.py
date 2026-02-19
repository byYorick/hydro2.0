from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, Tuple

import httpx

from app.runtime_state import SchedulerRuntimeState
from infrastructure import ae_client


def register_active_task(m: Any, task_id: str, metadata: Dict[str, Any]) -> None:
    state = SchedulerRuntimeState.from_module(m)
    state.active_tasks[task_id] = metadata
    schedule_key = str(metadata.get("schedule_key") or "")
    if schedule_key:
        state.active_schedule_tasks[schedule_key] = task_id
    m.SCHEDULER_ACTIVE_TASKS.set(len(state.active_tasks))
    state.apply_to_module(m)


def drop_active_task(m: Any, task_id: str) -> None:
    state = SchedulerRuntimeState.from_module(m)
    metadata = state.active_tasks.pop(task_id, None)
    if metadata:
        schedule_key = str(metadata.get("schedule_key") or "")
        if schedule_key and state.active_schedule_tasks.get(schedule_key) == task_id:
            state.active_schedule_tasks.pop(schedule_key, None)
    m.SCHEDULER_ACTIVE_TASKS.set(len(state.active_tasks))
    state.apply_to_module(m)


def is_schedule_busy(m: Any, schedule_key: str) -> bool:
    state = SchedulerRuntimeState.from_module(m)
    task_id = state.active_schedule_tasks.get(schedule_key)
    return bool(task_id and task_id in state.active_tasks)


async def zone_exists_preflight(m: Any, zone_id: int) -> Optional[bool]:
    try:
        rows = await m.fetch(
            """
            SELECT 1
            FROM zones
            WHERE id = $1
            LIMIT 1
            """,
            zone_id,
        )
        return bool(rows)
    except Exception as exc:
        m.logger.warning(
            "Scheduler zone preflight check failed, continue in fail-open mode: zone_id=%s error=%s",
            zone_id,
            exc,
            exc_info=True,
        )
        return None


async def create_zone_event_safe(
    m: Any,
    zone_id: int,
    event_type: str,
    payload: Dict[str, Any],
    *,
    task_id: Optional[str] = None,
    task_type: Optional[str] = None,
) -> bool:
    try:
        await m.create_zone_event(zone_id, event_type, payload)
        return True
    except Exception as exc:
        await m._emit_scheduler_diagnostic(
            reason="zone_event_write_failed",
            message=(
                f"Scheduler не смог записать zone_event {event_type} "
                f"для task {task_id or 'unknown'} (zone={zone_id})"
            ),
            level="error",
            zone_id=zone_id,
            details={
                "task_id": task_id,
                "task_type": task_type,
                "event_type": event_type,
                "error": str(exc),
            },
            alert_code="infra_scheduler_zone_event_write_failed",
            error_type=type(exc).__name__,
        )
        return False


async def wait_task_completion(
    m: Any,
    *,
    zone_id: int,
    task_id: str,
    task_type: str,
    timeout_sec: float,
) -> Tuple[bool, str, Dict[str, Any]]:
    created_trace = False
    if not m.get_trace_id():
        m.set_trace_id()
        created_trace = True

    deadline = m.utcnow().timestamp() + timeout_sec
    headers = m._scheduler_headers()

    try:
        while m.utcnow().timestamp() < deadline:
            try:
                response = await ae_client.get_json(
                    url=f"{m.AUTOMATION_ENGINE_URL}/scheduler/task/{task_id}",
                    headers=headers,
                    timeout=5.0,
                )
            except httpx.TimeoutException:
                m.COMMAND_REST_ERRORS.labels(error_type="task_status_timeout").inc()
                await asyncio.sleep(m.SCHEDULER_TASK_POLL_INTERVAL_SEC)
                continue
            except Exception as exc:
                m.COMMAND_REST_ERRORS.labels(error_type="task_status_request_error").inc()
                await m._emit_scheduler_diagnostic(
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
                m.COMMAND_REST_ERRORS.labels(error_type=f"task_status_http_{response.status_code}").inc()
                await asyncio.sleep(m.SCHEDULER_TASK_POLL_INTERVAL_SEC)
                continue

            body = response.json() if response.content else {}
            data = body.get("data") if isinstance(body, dict) else {}
            status = str(data.get("status") or "").lower()
            status_payload = data if isinstance(data, dict) else {}

            if status in {"completed", "done"}:
                return True, "completed", status_payload
            if status in {"failed", "rejected", "expired", "timeout", "error"}:
                return False, status, status_payload

            await asyncio.sleep(m.SCHEDULER_TASK_POLL_INTERVAL_SEC)

        return False, "timeout", {}
    finally:
        if created_trace:
            m.clear_trace_id()


async def fetch_task_status_once(
    m: Any,
    task_id: str,
    *,
    zone_id: Optional[int] = None,
    task_type: Optional[str] = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    headers = m._scheduler_headers()
    try:
        response = await ae_client.get_json(
            url=f"{m.AUTOMATION_ENGINE_URL}/scheduler/task/{task_id}",
            headers=headers,
            timeout=5.0,
        )
    except httpx.TimeoutException:
        m.COMMAND_REST_ERRORS.labels(error_type="task_status_timeout").inc()
        await m._emit_scheduler_diagnostic(
            reason="task_status_timeout",
            message=(
                f"Scheduler получил timeout при чтении статуса задачи {task_type or 'unknown'} "
                f"({task_id}) для зоны {zone_id or 'unknown'}"
            ),
            level="warning",
            zone_id=zone_id,
            details={"task_id": task_id, "task_type": task_type},
            alert_code="infra_scheduler_task_status_timeout",
            error_type="timeout",
        )
        return None, {}
    except Exception as exc:
        m.COMMAND_REST_ERRORS.labels(error_type="task_status_request_error").inc()
        await m._emit_scheduler_diagnostic(
            reason="task_status_request_failed",
            message=(
                f"Scheduler не смог получить статус задачи {task_type or 'unknown'} "
                f"({task_id}) для зоны {zone_id or 'unknown'}"
            ),
            level="error",
            zone_id=zone_id,
            details={"task_id": task_id, "task_type": task_type, "error": str(exc)},
            alert_code="infra_scheduler_task_status_failed",
            error_type=type(exc).__name__,
        )
        return None, {}

    if response.status_code == 404:
        await m._emit_scheduler_diagnostic(
            reason="task_status_not_found",
            message=(
                f"Scheduler получил 404 при чтении статуса задачи {task_type or 'unknown'} "
                f"({task_id}) для зоны {zone_id or 'unknown'}"
            ),
            level="warning",
            zone_id=zone_id,
            details={"task_id": task_id, "task_type": task_type},
            alert_code="infra_scheduler_task_status_not_found",
            error_type="not_found",
        )
        return "not_found", {}
    if response.status_code != 200:
        m.COMMAND_REST_ERRORS.labels(error_type=f"task_status_http_{response.status_code}").inc()
        await m._emit_scheduler_diagnostic(
            reason="task_status_http_error",
            message=(
                f"Scheduler получил HTTP {response.status_code} при чтении статуса "
                f"задачи {task_type or 'unknown'} ({task_id})"
            ),
            level="warning",
            zone_id=zone_id,
            details={
                "task_id": task_id,
                "task_type": task_type,
                "status_code": response.status_code,
            },
            alert_code="infra_scheduler_task_status_failed",
            error_type=f"http_{response.status_code}",
        )
        return None, {}

    body = response.json() if response.content else {}
    data = body.get("data") if isinstance(body, dict) else {}
    status = str(data.get("status") or "").lower()
    return status or None, data if isinstance(data, dict) else {}


async def recover_active_tasks_after_restart(m: Any) -> int:
    state = SchedulerRuntimeState.from_module(m)
    if state.active_tasks:
        m.SCHEDULER_ACTIVE_TASKS.set(len(state.active_tasks))
        return len(state.active_tasks)

    try:
        rows = await m.fetch(
            """
            WITH recent_logs AS (
                SELECT id, details, status, created_at
                FROM scheduler_logs
                WHERE details ? 'task_id'
                  AND status IN ('accepted', 'completed', 'failed')
                ORDER BY created_at DESC, id DESC
                LIMIT $1
            )
            SELECT DISTINCT ON (details->>'task_id')
                details, status, created_at
            FROM recent_logs
            ORDER BY (details->>'task_id'), created_at DESC, id DESC
            """,
            m._ACTIVE_TASK_RECOVERY_SCAN_LIMIT,
        )
    except Exception as exc:
        await m._emit_scheduler_diagnostic(
            reason="active_task_recovery_failed",
            message="Scheduler не смог выполнить startup recovery активных задач",
            level="error",
            details={"error": str(exc)},
            alert_code="infra_scheduler_active_task_recovery_failed",
            error_type=type(exc).__name__,
        )
        return 0

    recovered = 0
    skipped_invalid = 0
    for row in rows:
        status = str(row.get("status") or "").strip().lower()
        if status != "accepted":
            continue

        details = row.get("details")
        if not isinstance(details, dict):
            skipped_invalid += 1
            continue

        task_id = str(details.get("task_id") or "").strip()
        if not task_id or task_id in state.active_tasks:
            continue

        try:
            zone_id = int(details.get("zone_id"))
        except (TypeError, ValueError):
            skipped_invalid += 1
            continue

        task_type = str(details.get("task_type") or "").strip().lower()
        if not task_type:
            skipped_invalid += 1
            continue

        schedule_key = str(details.get("schedule_key") or "")
        correlation_id = str(details.get("correlation_id") or "")
        accepted_at = m._parse_iso_datetime_utc(str(details.get("accepted_at") or ""))
        if accepted_at is None:
            created_at = row.get("created_at")
            accepted_at = created_at if isinstance(created_at, m.datetime) else m.utcnow().replace(tzinfo=None)

        state.active_tasks[task_id] = {
            "zone_id": zone_id,
            "task_type": task_type,
            "task_name": f"{task_type}_zone_{zone_id}",
            "accepted_at": accepted_at,
            "schedule_key": schedule_key,
            "correlation_id": correlation_id,
            "recovered_after_restart": True,
        }
        if schedule_key:
            state.active_schedule_tasks[schedule_key] = task_id
        recovered += 1

    if skipped_invalid > 0:
        await m._emit_scheduler_diagnostic(
            reason="active_task_recovery_invalid_payload",
            message="Scheduler обнаружил некорректные snapshot-и при startup recovery активных задач",
            level="warning",
            details={"skipped_invalid": skipped_invalid},
            alert_code="infra_scheduler_active_task_recovery_invalid_payload",
            error_type="invalid_payload",
        )

    if recovered > 0:
        m.send_service_log(
            service="scheduler",
            level="warning",
            message="Scheduler восстановил активные задачи после рестарта",
            context={"recovered_tasks": recovered},
        )

    m.SCHEDULER_ACTIVE_TASKS.set(len(state.active_tasks))
    state.apply_to_module(m)
    return recovered


async def reconcile_active_tasks(m: Any) -> None:
    state = SchedulerRuntimeState.from_module(m)
    if not state.active_tasks:
        m.SCHEDULER_ACTIVE_TASKS.set(0)
        return

    now = m.utcnow().replace(tzinfo=None)
    for task_id, metadata in list(state.active_tasks.items()):
        zone_id = int(metadata.get("zone_id") or 0)
        task_type = str(metadata.get("task_type") or "unknown")
        task_name = str(metadata.get("task_name") or f"{task_type}_zone_{zone_id}")
        accepted_at = metadata.get("accepted_at")
        accepted_dt = accepted_at if isinstance(accepted_at, m.datetime) else now

        status, status_payload = await m._fetch_task_status_once(
            task_id,
            zone_id=zone_id,
            task_type=task_type,
        )

        if status is None:
            elapsed = max(0.0, (now - accepted_dt).total_seconds())
            if elapsed >= m.SCHEDULER_TASK_TIMEOUT_SEC:
                status = "timeout"
            else:
                continue

        if not m._is_terminal_status(status):
            continue

        terminal_status = m._normalize_terminal_status(status)
        completion_elapsed = max(0.0, (now - accepted_dt).total_seconds())
        m.SCHEDULER_TASK_COMPLETION_LATENCY_SEC.labels(task_type=task_type, status=terminal_status).observe(completion_elapsed)
        m.TASK_ACCEPT_TO_TERMINAL_LATENCY.labels(task_type=task_type, status=terminal_status).observe(completion_elapsed)
        m._update_deadline_violation_rate(task_type, terminal_status)
        outcome = m._extract_task_outcome_fields(status_payload)

        try:
            if terminal_status == "completed":
                m.SCHEDULE_EXECUTIONS.labels(zone_id=zone_id, task_type=task_type).inc()
                m.SCHEDULER_TASK_STATUS.labels(task_type=task_type, status="completed").inc()
                await m.create_scheduler_log(
                    task_name,
                    "completed",
                    {
                        "zone_id": zone_id,
                        "task_type": task_type,
                        "task_id": task_id,
                        "status": terminal_status,
                        "status_payload": status_payload,
                        "action_required": outcome["action_required"],
                        "decision": outcome["decision"],
                        "reason_code": outcome["reason_code"],
                        **m._outcome_extended_fields(outcome),
                        "result": outcome["result"],
                    },
                )
                await m._create_zone_event_safe(
                    zone_id,
                    "SCHEDULE_TASK_COMPLETED",
                    {
                        "task_type": task_type,
                        "task_id": task_id,
                        "status": terminal_status,
                        "action_required": outcome["action_required"],
                        "decision": outcome["decision"],
                        "reason_code": outcome["reason_code"],
                        **m._outcome_extended_fields(outcome),
                    },
                    task_id=task_id,
                    task_type=task_type,
                )
            else:
                final_status = terminal_status or "failed"
                m.SCHEDULER_TASK_STATUS.labels(task_type=task_type, status=final_status).inc()
                await m.create_scheduler_log(
                    task_name,
                    "failed",
                    {
                        "zone_id": zone_id,
                        "task_type": task_type,
                        "task_id": task_id,
                        "status": final_status,
                        "status_payload": status_payload,
                        "error": outcome["error"],
                        "error_code": outcome["error_code"],
                        "action_required": outcome["action_required"],
                        "decision": outcome["decision"],
                        "reason_code": outcome["reason_code"],
                        **m._outcome_extended_fields(outcome),
                    },
                )
                await m._create_zone_event_safe(
                    zone_id,
                    "SCHEDULE_TASK_FAILED",
                    {
                        "task_type": task_type,
                        "task_id": task_id,
                        "status": final_status,
                        "error": outcome["error"],
                        "error_code": outcome["error_code"],
                        "action_required": outcome["action_required"],
                        "decision": outcome["decision"],
                        "reason_code": outcome["reason_code"],
                        **m._outcome_extended_fields(outcome),
                    },
                    task_id=task_id,
                    task_type=task_type,
                )
        except Exception as exc:
            await m._emit_scheduler_diagnostic(
                reason="task_terminal_persist_failed",
                message=(
                    f"Scheduler не смог сохранить terminal snapshot "
                    f"task {task_id} (status={terminal_status})"
                ),
                level="error",
                zone_id=zone_id,
                details={
                    "task_id": task_id,
                    "task_type": task_type,
                    "status": terminal_status,
                    "error": str(exc),
                },
                alert_code="infra_scheduler_task_terminal_persist_failed",
                error_type=type(exc).__name__,
            )
        finally:
            drop_active_task(m, task_id)

    state.apply_to_module(m)
