"""Startup/stale recovery для greenhouse climate intents и tasks."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from common.db import execute, fetch

logger = logging.getLogger(__name__)

_DEFAULT_STALE_RUNNING_TTL_SEC = 600


async def recover_stale_greenhouse_automation(
    *,
    now: datetime,
    stale_running_ttl_sec: int = _DEFAULT_STALE_RUNNING_TTL_SEC,
) -> dict[str, int]:
    """Возвращает stale greenhouse intents/tasks в pending или terminal failed (bounded)."""
    normalized_now = (
        now.astimezone(timezone.utc).replace(tzinfo=None)
        if now.tzinfo is not None
        else now.replace(microsecond=0)
    )
    stale_before = normalized_now - timedelta(seconds=max(60, int(stale_running_ttl_sec)))

    await execute(
        """
        DELETE FROM greenhouse_automation_leases
        WHERE leased_until <= $1
        """,
        normalized_now,
    )

    requeued_intents = await fetch(
        """
        UPDATE greenhouse_automation_intents AS i
        SET status = 'pending',
            claimed_at = NULL,
            updated_at = $2,
            error_code = NULL,
            error_message = NULL,
            retry_count = LEAST(COALESCE(i.retry_count, 0) + 1, COALESCE(i.max_retries, 3))
        WHERE i.status = 'running'
          AND i.claimed_at IS NOT NULL
          AND i.claimed_at < $1
          AND COALESCE(i.retry_count, 0) < COALESCE(i.max_retries, 3)
        RETURNING i.id
        """,
        stale_before,
        normalized_now,
    )

    failed_intents = await fetch(
        """
        UPDATE greenhouse_automation_intents AS i
        SET status = 'failed',
            completed_at = $2,
            updated_at = $2,
            error_code = 'greenhouse_climate_stale_running',
            error_message = 'Greenhouse climate intent exceeded stale running recovery budget'
        WHERE i.status = 'running'
          AND i.claimed_at IS NOT NULL
          AND i.claimed_at < $1
          AND COALESCE(i.retry_count, 0) >= COALESCE(i.max_retries, 3)
        RETURNING i.id
        """,
        stale_before,
        normalized_now,
    )

    failed_tasks = await fetch(
        """
        UPDATE greenhouse_automation_tasks AS t
        SET status = 'failed',
            workflow_stage = 'recovery',
            error_code = 'greenhouse_climate_stale_running',
            error_message = 'Greenhouse climate task reclaimed after stale running state',
            completed_at = $2,
            updated_at = $2
        WHERE t.status IN ('claimed', 'running', 'waiting_command')
          AND t.updated_at < $1
        RETURNING t.id
        """,
        stale_before,
        normalized_now,
    )

    result = {
        "requeued_intents": len(requeued_intents or []),
        "failed_intents": len(failed_intents or []),
        "failed_tasks": len(failed_tasks or []),
    }
    if any(result[k] for k in ("requeued_intents", "failed_intents", "failed_tasks")):
        logger.warning(
            "Greenhouse climate recovery: requeued_intents=%s failed_intents=%s failed_tasks=%s",
            result["requeued_intents"],
            result["failed_intents"],
            result["failed_tasks"],
        )
    return result
