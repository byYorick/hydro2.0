"""Recovery logic for in-flight scheduler tasks."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

from ae2lite.api_recovery_types import RecoverySummary
from services.resilience_contract import (
    INFRA_SCHEDULER_TASK_RECOVERY_EVENT_FAILED,
    INFRA_SCHEDULER_TASK_RECOVERY_PERSIST_FAILED,
    SCHEDULER_MODE_STARTUP_RECOVERY_FINALIZE,
    SCHEDULER_RECOVERY_SOURCE_STARTUP,
    SCHEDULER_TASK_RECOVERED_AFTER_RESTART,
)


def task_id_from_log_name(task_name: Any) -> Optional[str]:
    if not isinstance(task_name, str):
        return None
    prefix = "ae_scheduler_task_"
    if not task_name.startswith(prefix):
        return None
    task_id = task_name[len(prefix):].strip()
    return task_id or None


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


async def _recover_inflight_intents(
    *,
    fetch_fn: Callable[..., Awaitable[Any]],
    scan_limit: int,
    create_zone_event_fn: Callable[[int, str, Dict[str, Any]], Awaitable[Any]],
    send_infra_exception_alert_fn: Callable[..., Awaitable[Any]],
    logger: logging.Logger,
) -> Dict[str, int]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    terminal_error_code = SCHEDULER_TASK_RECOVERED_AFTER_RESTART
    terminal_error_message = "Automation-engine перезапущен: in-flight intent финализирован recovery-политикой"

    try:
        rows = await fetch_fn(
            """
            SELECT id, zone_id, status, claimed_at, updated_at
            FROM zone_automation_intents
            WHERE status IN ('claimed', 'running')
            ORDER BY updated_at ASC NULLS FIRST, id ASC
            LIMIT $1
            """,
            scan_limit,
        )
    except Exception:
        logger.warning("Scheduler intent recovery scan failed", exc_info=True)
        return {"scanned": 0, "recovered": 0}

    scanned = len(rows)
    recovered = 0
    for row in rows:
        try:
            intent_id = int(row.get("id") or 0)
            zone_id = int(row.get("zone_id") or 0)
        except Exception:
            continue
        status = _normalize_status(row.get("status"))
        if intent_id <= 0 or zone_id <= 0 or status not in {"claimed", "running"}:
            continue

        try:
            updated = await fetch_fn(
                """
                UPDATE zone_automation_intents
                SET status = 'failed',
                    completed_at = $2,
                    updated_at = $2,
                    error_code = $3,
                    error_message = $4
                WHERE id = $1
                  AND status IN ('claimed', 'running')
                RETURNING id
                """,
                intent_id,
                now,
                terminal_error_code,
                terminal_error_message,
            )
        except Exception as exc:
            logger.warning(
                "Failed to recover in-flight intent: intent_id=%s zone_id=%s error=%s",
                intent_id,
                zone_id,
                exc,
                exc_info=True,
            )
            await send_infra_exception_alert_fn(
                error=exc,
                code=INFRA_SCHEDULER_TASK_RECOVERY_PERSIST_FAILED,
                alert_type="Scheduler Intent Recovery Persist Failed",
                severity="error",
                zone_id=zone_id,
                service="automation-engine",
                component="scheduler_intent_recovery",
                error_type=type(exc).__name__,
                details={"intent_id": intent_id},
            )
            continue

        if not updated:
            continue

        recovered += 1
        logger.info(
            "Recovered in-flight intent after restart: intent_id=%s zone_id=%s previous_status=%s",
            intent_id,
            zone_id,
            status,
        )
        try:
            await create_zone_event_fn(
                zone_id,
                "SCHEDULE_TASK_FAILED",
                {
                    "task_id": f"intent-{intent_id}",
                    "task_type": "diagnostics",
                    "intent_id": intent_id,
                    "status": "failed",
                    "error_code": terminal_error_code,
                    "source": SCHEDULER_RECOVERY_SOURCE_STARTUP,
                },
            )
        except Exception as exc:
            logger.warning(
                "Failed to publish intent recovery zone event: intent_id=%s zone_id=%s error=%s",
                intent_id,
                zone_id,
                exc,
                exc_info=True,
            )
            await send_infra_exception_alert_fn(
                error=exc,
                code=INFRA_SCHEDULER_TASK_RECOVERY_EVENT_FAILED,
                alert_type="Scheduler Intent Recovery Event Failed",
                severity="error",
                zone_id=zone_id,
                service="automation-engine",
                component="scheduler_intent_recovery",
                error_type=type(exc).__name__,
                details={"intent_id": intent_id},
            )

    return {"scanned": scanned, "recovered": recovered}


async def recover_inflight_scheduler_tasks(
    *,
    enabled: bool,
    fetch_fn: Callable[..., Awaitable[Any]],
    scan_limit: int,
    build_execution_terminal_result_fn: Callable[..., Dict[str, Any]],
    scheduler_tasks: Dict[str, Dict[str, Any]],
    scheduler_tasks_lock: Any,
    persist_scheduler_task_snapshot_fn: Callable[[Dict[str, Any]], Awaitable[None]],
    create_zone_event_fn: Callable[[int, str, Dict[str, Any]], Awaitable[Any]],
    send_infra_exception_alert_fn: Callable[..., Awaitable[Any]],
    task_recovery_success_rate_gauge: Any,
    logger: logging.Logger,
) -> RecoverySummary:
    if not enabled:
        return {"scanned": 0, "inflight": 0, "recovered": 0}

    try:
        rows = await fetch_fn(
            """
            WITH recent_logs AS (
                SELECT id, task_name, status, details, created_at
                FROM scheduler_logs
                WHERE task_name LIKE 'ae_scheduler_task_st-%'
                ORDER BY created_at DESC, id DESC
                LIMIT $1
            )
            SELECT DISTINCT ON (task_name)
                task_name, status, details, created_at
            FROM recent_logs
            ORDER BY task_name, created_at DESC, id DESC
            """,
            scan_limit,
        )
    except Exception:
        logger.warning("Scheduler task recovery scan failed", exc_info=True)
        return {"scanned": 0, "inflight": 0, "recovered": 0}

    scanned = len(rows)
    inflight = 0
    recovered = 0
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    for row in rows:
        details = row.get("details") if isinstance(row.get("details"), dict) else {}
        raw_status = details.get("status") if isinstance(details, dict) else None
        if not raw_status:
            raw_status = row.get("status")
        status = str(raw_status or "").strip().lower()
        if status not in {"accepted", "running"}:
            continue
        inflight += 1

        task_id = details.get("task_id") if isinstance(details, dict) else None
        if not task_id:
            task_id = task_id_from_log_name(row.get("task_name"))
        zone_id = details.get("zone_id") if isinstance(details, dict) else None
        task_type = details.get("task_type") if isinstance(details, dict) else None
        if not task_id or not zone_id or not task_type:
            continue

        recovery_result = build_execution_terminal_result_fn(
            error_code=SCHEDULER_TASK_RECOVERED_AFTER_RESTART,
            reason="Automation-engine перезапущен: in-flight задача финализирована recovery-политикой",
            mode=SCHEDULER_MODE_STARTUP_RECOVERY_FINALIZE,
            action_required=True,
            decision="fail",
            reason_code=SCHEDULER_TASK_RECOVERED_AFTER_RESTART,
        )

        recovered_task = {
            "task_id": task_id,
            "zone_id": zone_id,
            "task_type": task_type,
            "status": "failed",
            "created_at": details.get("created_at") if isinstance(details, dict) else None,
            "updated_at": now_iso,
            "scheduled_for": details.get("scheduled_for") if isinstance(details, dict) else None,
            "due_at": details.get("due_at") if isinstance(details, dict) else None,
            "expires_at": details.get("expires_at") if isinstance(details, dict) else None,
            "correlation_id": details.get("correlation_id") if isinstance(details, dict) else None,
            "payload_fingerprint": details.get("payload_fingerprint") if isinstance(details, dict) else None,
            "payload": details.get("payload") if isinstance(details.get("payload"), dict) else {},
            "result": recovery_result,
            "error": SCHEDULER_TASK_RECOVERED_AFTER_RESTART,
            "error_code": SCHEDULER_TASK_RECOVERED_AFTER_RESTART,
        }

        if not recovered_task["created_at"]:
            created_at = row.get("created_at")
            recovered_task["created_at"] = created_at.isoformat() if hasattr(created_at, "isoformat") else now_iso

        async with scheduler_tasks_lock:
            scheduler_tasks[task_id] = recovered_task

        try:
            await persist_scheduler_task_snapshot_fn(recovered_task)
        except Exception as exc:
            logger.warning(
                "Failed to persist recovered scheduler task snapshot: task_id=%s error=%s",
                task_id,
                exc,
                exc_info=True,
            )
            await send_infra_exception_alert_fn(
                error=exc,
                code=INFRA_SCHEDULER_TASK_RECOVERY_PERSIST_FAILED,
                alert_type="Scheduler Task Recovery Persist Failed",
                severity="error",
                zone_id=int(zone_id),
                service="automation-engine",
                component="scheduler_task_recovery",
                error_type=type(exc).__name__,
                details={"task_id": task_id, "task_type": task_type},
            )

        try:
            await create_zone_event_fn(
                int(zone_id),
                "SCHEDULE_TASK_FAILED",
                {
                    "task_id": task_id,
                    "task_type": task_type,
                    "status": "failed",
                    "error_code": SCHEDULER_TASK_RECOVERED_AFTER_RESTART,
                    "source": SCHEDULER_RECOVERY_SOURCE_STARTUP,
                },
            )
        except Exception as exc:
            logger.warning(
                "Failed to publish recovery zone event: task_id=%s zone_id=%s error=%s",
                task_id,
                zone_id,
                exc,
                exc_info=True,
            )
            await send_infra_exception_alert_fn(
                error=exc,
                code=INFRA_SCHEDULER_TASK_RECOVERY_EVENT_FAILED,
                alert_type="Scheduler Task Recovery Event Failed",
                severity="error",
                zone_id=int(zone_id),
                service="automation-engine",
                component="scheduler_task_recovery",
                error_type=type(exc).__name__,
                details={"task_id": task_id, "task_type": task_type},
            )
        recovered += 1

    if inflight <= 0:
        task_recovery_success_rate_gauge.set(1.0)
    else:
        task_recovery_success_rate_gauge.set(recovered / inflight)

    intent_summary = await _recover_inflight_intents(
        fetch_fn=fetch_fn,
        scan_limit=scan_limit,
        create_zone_event_fn=create_zone_event_fn,
        send_infra_exception_alert_fn=send_infra_exception_alert_fn,
        logger=logger,
    )

    return {
        "scanned": scanned,
        "inflight": inflight,
        "recovered": recovered,
        "intents_scanned": int(intent_summary.get("scanned") or 0),
        "intents_recovered": int(intent_summary.get("recovered") or 0),
    }


__all__ = ["recover_inflight_scheduler_tasks", "task_id_from_log_name"]
