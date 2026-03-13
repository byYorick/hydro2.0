"""Legacy intent helpers used by AE3-Lite compat ingress/runtime."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, Optional

from ae3lite.api.contracts import StartCycleRequest
from ae3lite.infrastructure.metrics import INTENT_CLAIMED, INTENT_STALE_RECLAIMED, INTENT_TERMINAL

TERMINAL_INTENT_STATUSES = {"completed", "failed", "cancelled"}
ACTIVE_INTENT_STATUSES = {"claimed", "running"}


def _affected_rows(command_tag: Any) -> int:
    try:
        return int(str(command_tag).split()[-1])
    except (AttributeError, IndexError, TypeError, ValueError):
        return 0


async def claim_start_cycle_intent(
    *,
    zone_id: int,
    req: StartCycleRequest,
    now: datetime,
    claimed_stale_after_sec: int = 180,
    running_stale_after_sec: int = 1800,
    fetch_fn: Callable[..., Awaitable[Any]],
) -> Dict[str, Any]:
    stale_claimed_before = now - timedelta(seconds=max(1, int(claimed_stale_after_sec)))
    stale_running_before = now - timedelta(seconds=max(1, int(running_stale_after_sec)))
    rows = await fetch_fn(
        """
        WITH candidate AS (
            SELECT id, status AS previous_status
            FROM zone_automation_intents
            WHERE zone_id = $1
              AND idempotency_key = $2
              AND (
                    status IN ('pending', 'failed')
                    OR (status = 'claimed' AND claimed_at IS NOT NULL AND claimed_at <= $4)
              )
              AND NOT EXISTS (
                    SELECT 1
                    FROM zone_automation_intents active_intent
                    WHERE active_intent.zone_id = $1
                      AND active_intent.idempotency_key <> $2
                      AND (
                            (
                                active_intent.status = 'running'
                                AND (active_intent.updated_at IS NULL OR active_intent.updated_at > $5)
                            )
                            OR (active_intent.status = 'claimed' AND (active_intent.claimed_at IS NULL OR active_intent.claimed_at > $4))
                      )
              )
              AND EXISTS (
                    SELECT 1
                    FROM zones z
                    WHERE z.id = $1
                    FOR UPDATE
              )
              AND (not_before IS NULL OR not_before <= $3)
              AND (status <> 'failed' OR retry_count < max_retries)
            ORDER BY id DESC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE zone_automation_intents intents
        SET status = 'claimed',
            claimed_at = $3,
            retry_count = CASE
                WHEN intents.status IN ('failed', 'claimed') THEN intents.retry_count + 1
                ELSE intents.retry_count
            END,
            updated_at = $3
        FROM candidate
        WHERE intents.id = candidate.id
        RETURNING intents.*, candidate.previous_status
        """,
        zone_id,
        req.idempotency_key,
        now,
        stale_claimed_before,
        stale_running_before,
    )
    if rows:
        intent = dict(rows[0])
        source_status = str(intent.pop("previous_status", "") or "").strip().lower() or "unknown"
        INTENT_CLAIMED.labels(source_status=source_status).inc()
        if source_status == "claimed":
            INTENT_STALE_RECLAIMED.inc()
        return {"decision": "claimed", "intent": intent}

    existing_rows = await fetch_fn(
        """
        SELECT *
        FROM zone_automation_intents
        WHERE zone_id = $1
          AND idempotency_key = $2
        ORDER BY id DESC
        LIMIT 1
        """,
        zone_id,
        req.idempotency_key,
    )
    requested_intent: Dict[str, Any] = {}
    if existing_rows:
        existing = dict(existing_rows[0])
        status = str(existing.get("status") or "").strip().lower()
        if status in {"pending", "failed"}:
            requested_intent = existing
        if status in ACTIVE_INTENT_STATUSES:
            return {"decision": "deduplicated", "intent": existing}
        if status in TERMINAL_INTENT_STATUSES:
            return {"decision": "terminal", "intent": existing}

    active_zone_rows = await fetch_fn(
        """
        SELECT *
        FROM zone_automation_intents
        WHERE zone_id = $1
          AND idempotency_key <> $2
          AND (
                (
                    status = 'running'
                    AND (updated_at IS NULL OR updated_at > $4)
                )
                OR (status = 'claimed' AND (claimed_at IS NULL OR claimed_at > $3))
          )
        ORDER BY id DESC
        LIMIT 1
        """,
        zone_id,
        req.idempotency_key,
        stale_claimed_before,
        stale_running_before,
    )
    if active_zone_rows:
        return {
            "decision": "zone_busy",
            "intent": dict(active_zone_rows[0]),
            "requested_intent": requested_intent,
        }

    cross_zone_rows = await fetch_fn(
        """
        SELECT *
        FROM zone_automation_intents
        WHERE idempotency_key = $1
          AND zone_id <> $2
        ORDER BY id DESC
        LIMIT 1
        """,
        req.idempotency_key,
        zone_id,
    )
    if cross_zone_rows:
        return {"decision": "conflict_cross_zone", "intent": dict(cross_zone_rows[0])}

    return {"decision": "missing", "intent": {}}


async def mark_intent_running(
    *,
    intent_id: int,
    now: datetime,
    execute_fn: Callable[..., Awaitable[Any]],
) -> None:
    await execute_fn(
        """
        UPDATE zone_automation_intents
        SET status = 'running',
            updated_at = $2
        WHERE id = $1
          AND status IN ('claimed', 'running')
        """,
        intent_id,
        now,
    )


async def mark_intent_terminal(
    *,
    intent_id: int,
    now: datetime,
    success: bool,
    error_code: Optional[str],
    error_message: Optional[str],
    execute_fn: Callable[..., Awaitable[Any]],
) -> None:
    status = "completed" if success else "failed"
    result = await execute_fn(
        """
        UPDATE zone_automation_intents
        SET status = $2,
            completed_at = $3,
            updated_at = $3,
            error_code = $4,
            error_message = $5
        WHERE id = $1
          AND status IN ('pending', 'claimed', 'running')
        """,
        intent_id,
        status,
        now,
        error_code if not success else None,
        error_message if not success else None,
    )
    if _affected_rows(result) > 0:
        INTENT_TERMINAL.labels(status=status).inc()


__all__ = [
    "ACTIVE_INTENT_STATUSES",
    "TERMINAL_INTENT_STATUSES",
    "claim_start_cycle_intent",
    "mark_intent_running",
    "mark_intent_terminal",
]
