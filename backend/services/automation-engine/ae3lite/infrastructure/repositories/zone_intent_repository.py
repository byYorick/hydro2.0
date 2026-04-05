"""PostgreSQL-репозиторий жизненного цикла zone automation intent в AE3-Lite."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from ae3lite.api.contracts import StartCycleRequest, StartIrrigationRequest, StartLightingTickRequest
from ae3lite.infrastructure.metrics import INTENT_CLAIMED, INTENT_STALE_RECLAIMED, INTENT_TERMINAL
from common.db import execute, fetch


def _affected_rows(command_tag: Any) -> int:
    try:
        return int(str(command_tag).split()[-1])
    except (AttributeError, IndexError, TypeError, ValueError):
        return 0


_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
_ACTIVE_STATUSES = frozenset({"claimed", "running"})


class PgZoneIntentRepository:
    """Управляет жизненным циклом `zone_automation_intents` для AE3-Lite."""

    async def claim_start_cycle(
        self,
        *,
        zone_id: int,
        req: StartCycleRequest,
        now: datetime,
        claimed_stale_after_sec: int = 180,
        running_stale_after_sec: int = 1800,
    ) -> dict[str, Any]:
        return await self._claim_by_idempotency_key(
            zone_id=zone_id,
            idempotency_key=req.idempotency_key,
            now=now,
            claimed_stale_after_sec=claimed_stale_after_sec,
            running_stale_after_sec=running_stale_after_sec,
        )

    async def claim_start_irrigation(
        self,
        *,
        zone_id: int,
        req: StartIrrigationRequest,
        now: datetime,
        claimed_stale_after_sec: int = 180,
        running_stale_after_sec: int = 1800,
    ) -> dict[str, Any]:
        return await self._claim_by_idempotency_key(
            zone_id=zone_id,
            idempotency_key=req.idempotency_key,
            now=now,
            claimed_stale_after_sec=claimed_stale_after_sec,
            running_stale_after_sec=running_stale_after_sec,
        )

    async def claim_start_lighting_tick(
        self,
        *,
        zone_id: int,
        req: StartLightingTickRequest,
        now: datetime,
        claimed_stale_after_sec: int = 180,
        running_stale_after_sec: int = 1800,
    ) -> dict[str, Any]:
        return await self._claim_by_idempotency_key(
            zone_id=zone_id,
            idempotency_key=req.idempotency_key,
            now=now,
            claimed_stale_after_sec=claimed_stale_after_sec,
            running_stale_after_sec=running_stale_after_sec,
        )

    async def _claim_by_idempotency_key(
        self,
        *,
        zone_id: int,
        idempotency_key: str,
        now: datetime,
        claimed_stale_after_sec: int,
        running_stale_after_sec: int,
    ) -> dict[str, Any]:
        stale_claimed_before = now - timedelta(seconds=max(1, int(claimed_stale_after_sec)))
        stale_running_before = now - timedelta(seconds=max(1, int(running_stale_after_sec)))
        rows = await fetch(
            """
            WITH candidate AS (
                SELECT id, status AS previous_status
                FROM zone_automation_intents
                WHERE zone_id = $1
                  AND idempotency_key = $2
                  AND (
                        status IN ('pending', 'failed')
                        OR (status = 'claimed' AND claimed_at IS NOT NULL AND claimed_at <= $4)
                        OR (status = 'running' AND updated_at IS NOT NULL AND updated_at <= $5)
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
                    WHEN intents.status IN ('failed', 'claimed', 'running') THEN intents.retry_count + 1
                    ELSE intents.retry_count
                END,
                updated_at = $3
            FROM candidate
            WHERE intents.id = candidate.id
            RETURNING intents.*, candidate.previous_status
            """,
            zone_id,
            idempotency_key,
            now,
            stale_claimed_before,
            stale_running_before,
        )
        if rows:
            intent = dict(rows[0])
            source_status = str(intent.pop("previous_status", "") or "").strip().lower() or "unknown"
            INTENT_CLAIMED.labels(source_status=source_status).inc()
            if source_status in {"claimed", "running"}:
                INTENT_STALE_RECLAIMED.inc()
            return {"decision": "claimed", "intent": intent}

        existing_rows = await fetch(
            """
            SELECT *
            FROM zone_automation_intents
            WHERE zone_id = $1
              AND idempotency_key = $2
            ORDER BY id DESC
            LIMIT 1
            """,
            zone_id,
            idempotency_key,
        )
        requested_intent: dict[str, Any] = {}
        stale_same_key_running_intent: dict[str, Any] = {}
        if existing_rows:
            existing = dict(existing_rows[0])
            status = str(existing.get("status") or "").strip().lower()
            if status in {"pending", "failed"}:
                requested_intent = existing
            if status in _ACTIVE_STATUSES:
                is_stale_running = (
                    status == "running"
                    and existing.get("updated_at") is not None
                    and existing["updated_at"] <= stale_running_before
                )
                if is_stale_running:
                    requested_intent = existing
                    stale_same_key_running_intent = existing
                else:
                    return {"decision": "deduplicated", "intent": existing}
            if status in _TERMINAL_STATUSES:
                return {"decision": "terminal", "intent": existing}

        active_zone_rows = await fetch(
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
            idempotency_key,
            stale_claimed_before,
            stale_running_before,
        )
        if active_zone_rows:
            return {
                "decision": "zone_busy",
                "intent": dict(active_zone_rows[0]),
                "requested_intent": requested_intent,
            }

        if stale_same_key_running_intent:
            return {"decision": "deduplicated", "intent": stale_same_key_running_intent}

        return {"decision": "missing", "intent": {}}

    async def mark_running(self, *, intent_id: int, now: datetime) -> None:
        await execute(
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

    async def mark_terminal(
        self,
        *,
        intent_id: int,
        now: datetime,
        success: bool,
        error_code: Optional[str],
        error_message: Optional[str],
    ) -> None:
        status = "completed" if success else "failed"
        result = await execute(
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


__all__ = ["PgZoneIntentRepository"]
