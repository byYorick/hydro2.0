"""Helpers for AE2-Lite scheduler intents lifecycle."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, Optional

from ae2lite.api_contracts import SchedulerTaskRequest, StartCycleRequest

TERMINAL_INTENT_STATUSES = {"completed", "failed", "cancelled"}


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _intent_task_type(intent_payload: Dict[str, Any]) -> str:
    raw = str(intent_payload.get("task_type") or "diagnostics").strip().lower()
    return raw if raw else "diagnostics"


def _intent_correlation_id(*, intent_id: int, retry_count: int, idempotency_key: str) -> str:
    digest = hashlib.sha256(str(idempotency_key or "").encode("utf-8")).hexdigest()[:16]
    return f"start-cycle-intent:{max(intent_id, 0)}:{max(retry_count, 0)}:{digest}"


def _intent_runtime_payload(
    *,
    zone_id: int,
    req: StartCycleRequest,
    intent_payload: Dict[str, Any],
    default_topology: str,
) -> Dict[str, Any]:
    payload = _as_dict(intent_payload.get("task_payload"))
    if payload:
        return dict(payload)

    execution = {
        "topology": str(intent_payload.get("topology") or default_topology),
        "workflow": str(intent_payload.get("workflow") or "cycle_start"),
    }
    return {
        "workflow": execution["workflow"],
        "topology": execution["topology"],
        "source": str(intent_payload.get("source") or req.source),
        "config": {"execution": execution},
        "trigger": "start_cycle_api",
        "intent_zone_id": zone_id,
    }


def build_scheduler_task_request_from_intent(
    *,
    zone_id: int,
    req: StartCycleRequest,
    intent_row: Dict[str, Any],
    now: datetime,
    due_in_sec: int,
    expires_in_sec: int,
    default_topology: str,
) -> SchedulerTaskRequest:
    intent_payload = _as_dict(intent_row.get("payload"))
    due_at = now + timedelta(seconds=max(1, int(due_in_sec)))
    expires_at = now + timedelta(seconds=max(2, int(expires_in_sec)))
    retry_count = int(intent_row.get("retry_count") or 0)
    intent_id = int(intent_row.get("id") or 0)

    return SchedulerTaskRequest(
        zone_id=zone_id,
        task_type=_intent_task_type(intent_payload),
        payload=_intent_runtime_payload(
            zone_id=zone_id,
            req=req,
            intent_payload=intent_payload,
            default_topology=default_topology,
        ),
        scheduled_for=now.isoformat(),
        due_at=due_at.isoformat(),
        expires_at=expires_at.isoformat(),
        correlation_id=_intent_correlation_id(
            intent_id=intent_id,
            retry_count=retry_count,
            idempotency_key=req.idempotency_key,
        ),
    )


async def claim_start_cycle_intent(
    *,
    zone_id: int,
    req: StartCycleRequest,
    now: datetime,
    fetch_fn: Callable[..., Awaitable[Any]],
) -> Dict[str, Any]:
    rows = await fetch_fn(
        """
        WITH candidate AS (
            SELECT id
            FROM zone_automation_intents
            WHERE zone_id = $1
              AND idempotency_key = $2
              AND status IN ('pending', 'failed')
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
                WHEN intents.status = 'failed' THEN intents.retry_count + 1
                ELSE intents.retry_count
            END,
            updated_at = $3
        FROM candidate
        WHERE intents.id = candidate.id
        RETURNING intents.*
        """,
        zone_id,
        req.idempotency_key,
        now,
    )
    if rows:
        return {"decision": "claimed", "intent": dict(rows[0])}

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
    if existing_rows:
        existing = dict(existing_rows[0])
        status = str(existing.get("status") or "").strip().lower()
        if status in {"claimed", "running", "completed"}:
            return {"decision": "deduplicated", "intent": existing}
        if status in TERMINAL_INTENT_STATUSES:
            return {"decision": "terminal", "intent": existing}
    cross_zone_rows = await fetch_fn(
        """
        SELECT *
        FROM zone_automation_intents
        WHERE idempotency_key = $1
        ORDER BY id DESC
        LIMIT 1
        """,
        req.idempotency_key,
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
    await execute_fn(
        """
        UPDATE zone_automation_intents
        SET status = $2,
            completed_at = $3,
            updated_at = $3,
            error_code = $4,
            error_message = $5
        WHERE id = $1
        """,
        intent_id,
        "completed" if success else "failed",
        now,
        error_code if not success else None,
        error_message if not success else None,
    )


__all__ = [
    "build_scheduler_task_request_from_intent",
    "claim_start_cycle_intent",
    "mark_intent_running",
    "mark_intent_terminal",
]
