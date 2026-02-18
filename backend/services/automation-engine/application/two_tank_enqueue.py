"""Helpers for enqueueing two-tank follow-up checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

from services.resilience_contract import SCHEDULER_SOURCE_TWO_TANK_STARTUP

BuildTwoTankCheckPayloadFn = Callable[..., Dict[str, Any]]
EnqueueTaskFn = Callable[..., Awaitable[Dict[str, Any]]]


async def enqueue_two_tank_check(
    *,
    zone_id: int,
    payload: Dict[str, Any],
    workflow: str,
    phase_started_at: datetime,
    phase_timeout_at: datetime,
    poll_interval_sec: int,
    phase_cycle: Optional[int],
    build_two_tank_check_payload_fn: BuildTwoTankCheckPayloadFn,
    enqueue_task_fn: EnqueueTaskFn,
    now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc).replace(tzinfo=None),
) -> Dict[str, Any]:
    next_payload = build_two_tank_check_payload_fn(
        payload=payload,
        workflow=workflow,
        phase_started_at=phase_started_at,
        phase_timeout_at=phase_timeout_at,
        phase_cycle=phase_cycle,
    )
    next_check_at = now_factory() + timedelta(seconds=poll_interval_sec)
    if next_check_at > phase_timeout_at:
        next_check_at = phase_timeout_at
    return await enqueue_task_fn(
        zone_id=zone_id,
        task_type="diagnostics",
        payload=next_payload,
        scheduled_for=next_check_at.isoformat(),
        expires_at=phase_timeout_at.isoformat(),
        source=SCHEDULER_SOURCE_TWO_TANK_STARTUP,
    )


__all__ = ["enqueue_two_tank_check"]
