from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Coroutine, Dict, Optional, Set


async def drain_background_tasks(
    *,
    background_tasks: Set[asyncio.Task],
    logger: Any,
    timeout_sec: float = 5.0,
) -> None:
    if not background_tasks:
        return
    pending = [task for task in list(background_tasks) if not task.done()]
    for task in pending:
        task.cancel()
    try:
        await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True),
            timeout=max(float(timeout_sec), 0.1),
        )
    except asyncio.TimeoutError:
        logger.warning("Background task shutdown timeout: pending=%s", sum(1 for t in pending if not t.done()))
    finally:
        for task in list(background_tasks):
            if task.done():
                background_tasks.discard(task)


def spawn_background_task(
    coro: Coroutine[Any, Any, Any],
    *,
    task_name: str,
    zone_id: Optional[int],
    task_id: Optional[str],
    task_type: Optional[str],
    background_tasks: Set[asyncio.Task],
    spawn_policy_fn: Callable[..., asyncio.Task],
    send_infra_exception_alert_fn: Callable[..., Awaitable[Any]],
    logger: Any,
) -> asyncio.Task:
    task = spawn_policy_fn(
        coro,
        task_name=task_name,
        zone_id=zone_id,
        task_id=task_id,
        task_type=task_type,
        send_infra_exception_alert_fn=send_infra_exception_alert_fn,
        logger=logger,
    )
    background_tasks.add(task)
    task.add_done_callback(lambda done_task: background_tasks.discard(done_task))
    return task


async def is_scheduler_single_writer_active(
    *,
    enforce: bool,
    scheduler_bootstrap_lock: Any,
    scheduler_bootstrap_leases: Dict[str, Dict[str, Any]],
    now: datetime,
    zone_id: Optional[int] = None,
) -> bool:
    if not enforce:
        return False
    async with scheduler_bootstrap_lock:
        stale_keys = [
            key
            for key, payload in scheduler_bootstrap_leases.items()
            if not isinstance(payload.get("expires_at"), datetime) or payload.get("expires_at") <= now
        ]
        for key in stale_keys:
            scheduler_bootstrap_leases.pop(key, None)
        if zone_id is None:
            return bool(scheduler_bootstrap_leases)
        target_zone_id = int(zone_id)
        for payload in scheduler_bootstrap_leases.values():
            try:
                if int(payload.get("zone_id")) == target_zone_id:
                    return True
            except Exception:
                continue
        return False


def build_scheduler_single_writer_lease_key(*, zone_id: int, intent_id: int, task_id: str) -> str:
    # Single-writer must be unique per zone, not per intent/task.
    _ = intent_id
    _ = task_id
    return f"start_cycle:{zone_id}"


async def set_scheduler_single_writer_lease(
    *,
    lease_key: str,
    zone_id: int,
    intent_id: int,
    task_id: str,
    lease_ttl_sec: int,
    scheduler_bootstrap_lock: Any,
    scheduler_bootstrap_leases: Dict[str, Dict[str, Any]],
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = now + timedelta(seconds=max(1, int(lease_ttl_sec)))
    async with scheduler_bootstrap_lock:
        existing = scheduler_bootstrap_leases.get(lease_key)
        started_at = (
            existing.get("started_at")
            if isinstance(existing, dict) and isinstance(existing.get("started_at"), datetime)
            else now
        )
        scheduler_bootstrap_leases[lease_key] = {
            "lease_key": lease_key,
            "zone_id": int(zone_id),
            "intent_id": int(intent_id or 0),
            "task_id": str(task_id or ""),
            "started_at": started_at,
            "updated_at": now,
            "expires_at": expires_at,
        }


async def release_scheduler_single_writer_lease(
    *,
    lease_key: str,
    scheduler_bootstrap_lock: Any,
    scheduler_bootstrap_leases: Dict[str, Dict[str, Any]],
) -> None:
    async with scheduler_bootstrap_lock:
        scheduler_bootstrap_leases.pop(lease_key, None)


async def execute_scheduler_task_with_single_writer_lease(
    task_id: str,
    req: Any,
    trace_id: Optional[str],
    *,
    lease_key: str,
    zone_id: int,
    intent_id: int,
    execute_scheduler_task_fn: Callable[[str, Any, Optional[str]], Awaitable[None]],
    set_scheduler_single_writer_lease_fn: Callable[..., Awaitable[None]],
    lease_refresh_sec: int,
) -> None:
    execution_task = asyncio.create_task(execute_scheduler_task_fn(task_id, req, trace_id))
    refresh_timeout = float(max(1, int(lease_refresh_sec)))
    try:
        while True:
            done, _ = await asyncio.wait({execution_task}, timeout=refresh_timeout)
            if done:
                await execution_task
                return
            await set_scheduler_single_writer_lease_fn(
                lease_key=lease_key,
                zone_id=zone_id,
                intent_id=intent_id,
                task_id=task_id,
            )
    except Exception:
        if not execution_task.done():
            execution_task.cancel()
            await asyncio.gather(execution_task, return_exceptions=True)
        raise


__all__ = [
    "build_scheduler_single_writer_lease_key",
    "drain_background_tasks",
    "execute_scheduler_task_with_single_writer_lease",
    "is_scheduler_single_writer_active",
    "release_scheduler_single_writer_lease",
    "set_scheduler_single_writer_lease",
    "spawn_background_task",
]
