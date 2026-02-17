"""Scheduler bootstrap/lease helpers for API layer decomposition."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Tuple

from fastapi import HTTPException


async def validate_scheduler_dispatch_lease(
    *,
    enforce: bool,
    headers: Any,
    scheduler_bootstrap_lock: Any,
    scheduler_bootstrap_leases: Dict[str, Dict[str, Any]],
    cleanup_bootstrap_leases_locked_fn: Callable[[datetime], None],
) -> None:
    if not enforce:
        return

    scheduler_id = str(headers.get("x-scheduler-id") or "").strip()
    lease_id = str(headers.get("x-scheduler-lease-id") or "").strip()
    if not scheduler_id or not lease_id:
        raise HTTPException(status_code=403, detail="scheduler_bootstrap_required")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with scheduler_bootstrap_lock:
        cleanup_bootstrap_leases_locked_fn(now)
        lease = scheduler_bootstrap_leases.get(scheduler_id)
        if not lease:
            raise HTTPException(status_code=409, detail="scheduler_lease_not_found")
        if lease.get("lease_id") != lease_id:
            raise HTTPException(status_code=409, detail="scheduler_lease_mismatch")
        expires_at = lease.get("expires_at")
        if not isinstance(expires_at, datetime) or expires_at <= now:
            scheduler_bootstrap_leases.pop(scheduler_id, None)
            raise HTTPException(status_code=409, detail="scheduler_lease_expired")


async def build_scheduler_bootstrap_response(
    req: Any,
    *,
    scheduler_bootstrap_state_fn: Callable[[], Awaitable[Tuple[str, str]]],
    is_scheduler_protocol_supported_fn: Callable[[str], bool],
    scheduler_bootstrap_lease_ttl_sec: int,
    scheduler_bootstrap_poll_interval_sec: int,
    scheduler_bootstrap_task_timeout_sec: int,
    scheduler_dedupe_window_sec: int,
    scheduler_bootstrap_lock: Any,
    scheduler_bootstrap_leases: Dict[str, Dict[str, Any]],
    cleanup_bootstrap_leases_locked_fn: Callable[[datetime], None],
    new_scheduler_lease_id_fn: Callable[[], str],
    create_scheduler_log_fn: Callable[[str, str, Dict[str, Any]], Awaitable[Any]],
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    bootstrap_status, readiness_reason = await scheduler_bootstrap_state_fn()
    if not is_scheduler_protocol_supported_fn(req.protocol_version):
        bootstrap_status = "deny"
        readiness_reason = "protocol_not_supported"

    response_payload: Dict[str, Any] = {
        "bootstrap_status": bootstrap_status,
        "lease_ttl_sec": scheduler_bootstrap_lease_ttl_sec,
        "poll_interval_sec": scheduler_bootstrap_poll_interval_sec,
        "task_timeout_sec": scheduler_bootstrap_task_timeout_sec,
        "dedupe_window_sec": scheduler_dedupe_window_sec,
        "server_time": now.isoformat(),
    }
    if bootstrap_status != "ready":
        response_payload["reason"] = "automation_not_ready" if bootstrap_status == "wait" else readiness_reason
        response_payload["readiness_reason"] = readiness_reason

    async with scheduler_bootstrap_lock:
        cleanup_bootstrap_leases_locked_fn(now)
        if bootstrap_status == "ready":
            current = scheduler_bootstrap_leases.get(req.scheduler_id)
            lease_id = (
                str(current.get("lease_id"))
                if isinstance(current, dict) and current.get("lease_id")
                else new_scheduler_lease_id_fn()
            )
            scheduler_bootstrap_leases[req.scheduler_id] = {
                "lease_id": lease_id,
                "scheduler_version": req.scheduler_version,
                "protocol_version": req.protocol_version,
                "created_at": current.get("created_at") if isinstance(current, dict) and current.get("created_at") else now,
                "last_heartbeat_at": now,
                "expires_at": now + timedelta(seconds=scheduler_bootstrap_lease_ttl_sec),
            }
            response_payload["lease_id"] = lease_id
        else:
            scheduler_bootstrap_leases.pop(req.scheduler_id, None)

    await create_scheduler_log_fn(
        f"ae_scheduler_bootstrap_{req.scheduler_id}",
        bootstrap_status,
        {
            "scheduler_id": req.scheduler_id,
            "scheduler_version": req.scheduler_version,
            "protocol_version": req.protocol_version,
            "started_at": req.started_at,
            "bootstrap_status": bootstrap_status,
            "response": response_payload,
        },
    )
    return {"status": "ok", "data": response_payload}


async def build_scheduler_bootstrap_heartbeat_response(
    req: Any,
    *,
    scheduler_bootstrap_state_fn: Callable[[], Awaitable[Tuple[str, str]]],
    scheduler_bootstrap_lease_ttl_sec: int,
    scheduler_bootstrap_poll_interval_sec: int,
    scheduler_bootstrap_lock: Any,
    scheduler_bootstrap_leases: Dict[str, Dict[str, Any]],
    cleanup_bootstrap_leases_locked_fn: Callable[[datetime], None],
    create_scheduler_log_fn: Callable[[str, str, Dict[str, Any]], Awaitable[Any]],
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with scheduler_bootstrap_lock:
        cleanup_bootstrap_leases_locked_fn(now)
        lease = scheduler_bootstrap_leases.get(req.scheduler_id)
        if lease is None or str(lease.get("lease_id") or "") != req.lease_id:
            return {
                "status": "ok",
                "data": {
                    "bootstrap_status": "wait",
                    "reason": "lease_not_found",
                    "poll_interval_sec": scheduler_bootstrap_poll_interval_sec,
                    "server_time": now.isoformat(),
                },
            }
        bootstrap_status, readiness_reason = await scheduler_bootstrap_state_fn()
        if bootstrap_status != "ready":
            scheduler_bootstrap_leases.pop(req.scheduler_id, None)
            return {
                "status": "ok",
                "data": {
                    "bootstrap_status": "wait",
                    "reason": "automation_not_ready",
                    "readiness_reason": readiness_reason,
                    "poll_interval_sec": scheduler_bootstrap_poll_interval_sec,
                    "server_time": now.isoformat(),
                },
            }

        lease["last_heartbeat_at"] = now
        lease["expires_at"] = now + timedelta(seconds=scheduler_bootstrap_lease_ttl_sec)
        response_payload = {
            "bootstrap_status": "ready",
            "lease_id": req.lease_id,
            "lease_ttl_sec": scheduler_bootstrap_lease_ttl_sec,
            "lease_expires_at": lease["expires_at"].isoformat(),
            "server_time": now.isoformat(),
        }

    await create_scheduler_log_fn(
        f"ae_scheduler_bootstrap_{req.scheduler_id}",
        "heartbeat",
        {
            "scheduler_id": req.scheduler_id,
            "lease_id": req.lease_id,
            "bootstrap_status": response_payload["bootstrap_status"],
            "response": response_payload,
        },
    )
    return {"status": "ok", "data": response_payload}


__all__ = [
    "build_scheduler_bootstrap_heartbeat_response",
    "build_scheduler_bootstrap_response",
    "validate_scheduler_dispatch_lease",
]
