from __future__ import annotations

from typing import Any, Dict, List


async def load_pending_internal_enqueues(m: Any) -> List[Dict[str, Any]]:
    try:
        rows = await m.fetch(
            """
            WITH ranked AS (
                SELECT
                    task_name,
                    status,
                    details,
                    created_at,
                    id,
                    ROW_NUMBER() OVER (PARTITION BY task_name ORDER BY created_at DESC, id DESC) AS rn
                FROM scheduler_logs
                WHERE task_name LIKE $1
            )
            SELECT task_name, status, details, created_at, id
            FROM ranked
            WHERE rn = 1
              AND LOWER(COALESCE(status, '')) = 'pending'
            ORDER BY created_at ASC, id ASC
            LIMIT $2
            """,
            f"{m._INTERNAL_ENQUEUE_TASK_NAME_PREFIX}%",
            m._INTERNAL_ENQUEUE_SCAN_LIMIT,
        )
    except Exception as exc:
        await m._emit_scheduler_diagnostic(
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
        details = row.get("details")
        if not isinstance(details, dict):
            continue
        pending.append(details)
    return pending


async def mark_internal_enqueue_status(m: Any, task_name: str, status: str, details: Dict[str, Any]) -> None:
    payload = dict(details)
    payload["status"] = status
    payload["updated_at"] = m.utcnow().replace(tzinfo=None).isoformat()
    await m.create_scheduler_log(task_name, status, payload)


async def process_internal_enqueued_tasks(m: Any, now_dt) -> None:
    pending = await m._load_pending_internal_enqueues()
    for item in pending:
        enqueue_id = str(item.get("enqueue_id") or "").strip()
        task_name = f"{m._INTERNAL_ENQUEUE_TASK_NAME_PREFIX}{enqueue_id}" if enqueue_id else ""
        if not task_name:
            await m._emit_scheduler_diagnostic(
                reason="internal_enqueue_missing_id",
                message="Scheduler пропустил internal enqueue без enqueue_id",
                level="error",
                details={"payload": item},
                alert_code="infra_scheduler_internal_enqueue_invalid_payload",
                error_type="missing_enqueue_id",
            )
            continue

        zone_id_raw = item.get("zone_id")
        task_type = str(item.get("task_type") or "").strip().lower()
        try:
            zone_id = int(zone_id_raw)
        except (TypeError, ValueError):
            await m._emit_scheduler_diagnostic(
                reason="internal_enqueue_invalid_zone",
                message=f"Scheduler получил internal enqueue с некорректным zone_id: {zone_id_raw}",
                level="error",
                details={"enqueue_id": enqueue_id, "payload": item},
                alert_code="infra_scheduler_internal_enqueue_invalid_payload",
                error_type="invalid_zone_id",
            )
            await m._mark_internal_enqueue_status(task_name, "failed", {**item, "error": "invalid_zone_id"})
            continue
        if task_type not in m.SUPPORTED_TASK_TYPES:
            await m._emit_scheduler_diagnostic(
                reason="internal_enqueue_unsupported_task_type",
                message=f"Scheduler получил internal enqueue с неподдерживаемым task_type={task_type}",
                level="error",
                zone_id=zone_id,
                details={"enqueue_id": enqueue_id, "payload": item},
                alert_code="infra_scheduler_internal_enqueue_invalid_payload",
                error_type="unsupported_task_type",
            )
            await m._mark_internal_enqueue_status(task_name, "failed", {**item, "error": "unsupported_task_type"})
            continue

        scheduled_for = str(item.get("scheduled_for") or "").strip() or now_dt.isoformat()
        scheduled_for_dt = m._parse_iso_datetime_utc(scheduled_for) or now_dt
        if scheduled_for_dt > now_dt:
            continue

        expires_at_raw = item.get("expires_at")
        expires_at_dt = m._parse_iso_datetime_utc(str(expires_at_raw)) if expires_at_raw else None
        if expires_at_dt and now_dt > expires_at_dt:
            expired_by_sec = max(0.0, (now_dt - expires_at_dt).total_seconds())
            if expired_by_sec > m._INTERNAL_ENQUEUE_EXPIRE_GRACE_SEC:
                await m._emit_scheduler_diagnostic(
                    reason="internal_enqueue_expired_before_dispatch",
                    message=f"Scheduler отметил internal enqueue как expired до dispatch (enqueue_id={enqueue_id})",
                    level="warning",
                    zone_id=zone_id,
                    details={
                        "enqueue_id": enqueue_id,
                        "task_type": task_type,
                        "scheduled_for": scheduled_for,
                        "expires_at": expires_at_dt.isoformat(),
                        "expired_by_sec": expired_by_sec,
                        "expire_grace_sec": m._INTERNAL_ENQUEUE_EXPIRE_GRACE_SEC,
                    },
                    alert_code="infra_scheduler_internal_enqueue_expired",
                    error_type="expired_before_dispatch",
                )
                await m._mark_internal_enqueue_status(task_name, "expired", {**item, "error": "expired_before_dispatch"})
                await m.create_zone_event(
                    zone_id,
                    "SELF_TASK_EXPIRED",
                    {
                        "enqueue_id": enqueue_id,
                        "task_type": task_type,
                        "scheduled_for": scheduled_for,
                        "expires_at": expires_at_dt.isoformat(),
                        "expired_by_sec": expired_by_sec,
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
        dispatched = await m.execute_scheduled_task(
            zone_id=zone_id,
            schedule=schedule,
            trigger_time=scheduled_for_dt,
            schedule_key=schedule_key,
        )
        if not dispatched:
            dispatch_retry_count = m._safe_non_negative_int(item.get("dispatch_retry_count"), 0)
            next_retry_count = dispatch_retry_count + 1
            if next_retry_count < m._INTERNAL_ENQUEUE_DISPATCH_MAX_ATTEMPTS:
                backoff_sec = m._internal_enqueue_dispatch_backoff_sec(next_retry_count)
                next_retry_at = now_dt + m.timedelta(seconds=backoff_sec)
                retry_item = {
                    **item,
                    "dispatch_retry_count": next_retry_count,
                    "scheduled_for": next_retry_at.isoformat(),
                    "last_dispatch_error": "dispatch_failed",
                    "last_dispatch_failed_at": now_dt.isoformat(),
                }
                await m._emit_scheduler_diagnostic(
                    reason="internal_enqueue_dispatch_retry_scheduled",
                    message=f"Scheduler отложил retry internal enqueue после dispatch-fail (enqueue_id={enqueue_id})",
                    level="warning",
                    zone_id=zone_id,
                    details={
                        "enqueue_id": enqueue_id,
                        "task_type": task_type,
                        "retry_count": next_retry_count,
                        "max_attempts": m._INTERNAL_ENQUEUE_DISPATCH_MAX_ATTEMPTS,
                        "backoff_sec": backoff_sec,
                        "next_retry_at": next_retry_at.isoformat(),
                    },
                    alert_code="infra_scheduler_internal_enqueue_dispatch_retry",
                    error_type="dispatch_retry_scheduled",
                )
                await m._mark_internal_enqueue_status(task_name, "pending", retry_item)
                await m.create_zone_event(
                    zone_id,
                    "SELF_TASK_DISPATCH_RETRY_SCHEDULED",
                    {
                        "enqueue_id": enqueue_id,
                        "task_type": task_type,
                        "retry_count": next_retry_count,
                        "max_attempts": m._INTERNAL_ENQUEUE_DISPATCH_MAX_ATTEMPTS,
                        "next_retry_at": next_retry_at.isoformat(),
                    },
                )
                continue

            await m._emit_scheduler_diagnostic(
                reason="internal_enqueue_dispatch_failed",
                message=f"Scheduler не смог dispatch-ить internal enqueue задачу (enqueue_id={enqueue_id})",
                level="error",
                zone_id=zone_id,
                details={
                    "enqueue_id": enqueue_id,
                    "task_type": task_type,
                    "scheduled_for": scheduled_for,
                    "retry_count": next_retry_count,
                    "max_attempts": m._INTERNAL_ENQUEUE_DISPATCH_MAX_ATTEMPTS,
                },
                alert_code="infra_scheduler_internal_enqueue_dispatch_failed",
                error_type="dispatch_failed",
            )
            await m._mark_internal_enqueue_status(
                task_name,
                "failed",
                {
                    **item,
                    "error": "dispatch_failed",
                    "dispatch_retry_count": next_retry_count,
                    "dispatch_retry_max_attempts": m._INTERNAL_ENQUEUE_DISPATCH_MAX_ATTEMPTS,
                },
            )
            await m.create_zone_event(
                zone_id,
                "SELF_TASK_DISPATCH_FAILED",
                {
                    "enqueue_id": enqueue_id,
                    "task_type": task_type,
                    "scheduled_for": scheduled_for,
                    "retry_count": next_retry_count,
                    "max_attempts": m._INTERNAL_ENQUEUE_DISPATCH_MAX_ATTEMPTS,
                },
            )
            continue

        active_task_id = m._ACTIVE_SCHEDULE_TASKS.get(schedule_key)
        await m._mark_internal_enqueue_status(
            task_name,
            "dispatched",
            {
                **item,
                "task_id": active_task_id,
                "scheduled_for": scheduled_for_dt.isoformat(),
            },
        )
        await m.create_zone_event(
            zone_id,
            "SELF_TASK_DISPATCHED",
            {
                "enqueue_id": enqueue_id,
                "task_id": active_task_id,
                "task_type": task_type,
                "scheduled_for": scheduled_for_dt.isoformat(),
            },
        )
