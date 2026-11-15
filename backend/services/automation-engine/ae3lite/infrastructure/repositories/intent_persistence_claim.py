"""PgZoneIntentRepository claim: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from ae3lite.infrastructure.repositories.intent_persistence_shared import (
    _ACTIVE_STATUSES,
    _TERMINAL_STATUSES,
    _is_retryable_failed_intent,
)


@dataclass(frozen=True)
class IntentPersistenceClaimPorts:
    global_intent_claimed: Callable[..., Any]
    global_intent_stale_reclaimed: Callable[..., Any]
    global_fetch: Callable[..., Any]


class IntentPersistenceClaim:
    def __init__(self, ports: IntentPersistenceClaimPorts) -> None:
        self._ports = ports

    async def claim_pending_intent_by_id(
        self,
        *,
        zone_id: int,
        intent_id: int,
        now: datetime,
        claimed_stale_after_sec: int = 180,
        running_stale_after_sec: int = 1800,
    ) -> dict[str, Any]:
        """Claim a just-upserted pending intent by primary key (no SKIP LOCKED races)."""
        stale_claimed_before = now - timedelta(seconds=max(1, int(claimed_stale_after_sec)))
        stale_running_before = now - timedelta(seconds=max(1, int(running_stale_after_sec)))
        active_zone_rows = await self._ports.global_fetch(
            """
            SELECT *
            FROM zone_automation_intents
            WHERE zone_id = $1
              AND id <> $2
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
            intent_id,
            stale_claimed_before,
            stale_running_before,
        )
        if active_zone_rows:
            requested_rows = await self._ports.global_fetch(
                """
                SELECT *
                FROM zone_automation_intents
                WHERE id = $1
                  AND zone_id = $2
                LIMIT 1
                """,
                intent_id,
                zone_id,
            )
            return {
                "decision": "zone_busy",
                "intent": dict(active_zone_rows[0]),
                "requested_intent": dict(requested_rows[0]) if requested_rows else {},
            }

        busy_row = await self.execution_busy_row(zone_id=zone_id, now=now)
        if busy_row is not None:
            requested_rows = await self._ports.global_fetch(
                """
                SELECT *
                FROM zone_automation_intents
                WHERE id = $1
                  AND zone_id = $2
                LIMIT 1
                """,
                intent_id,
                zone_id,
            )
            return {
                "decision": "zone_busy",
                "intent": busy_row,
                "requested_intent": dict(requested_rows[0]) if requested_rows else {},
            }

        # not_before is timestamp(0): PG rounds half-up to whole seconds, so a
        # just-inserted row can have not_before = ceil(now) and fail `<= $3`.
        # Allow 1s slack so reactive claim right after upsert never misses.
        rows = await self._ports.global_fetch(
            """
            UPDATE zone_automation_intents
            SET status = 'claimed',
                claimed_at = $3,
                updated_at = $3
            WHERE id = $1
              AND zone_id = $2
              AND status IN ('pending', 'failed')
              AND (
                    not_before IS NULL
                    OR not_before <= ($3::timestamptz + interval '1 second')
              )
              AND (status <> 'failed' OR retry_count < max_retries)
              AND NOT EXISTS (
                    SELECT 1
                    FROM ae_tasks active_task
                    WHERE active_task.zone_id = $2
                      AND active_task.status IN ('pending', 'claimed', 'running', 'waiting_command')
              )
              AND NOT EXISTS (
                    SELECT 1
                    FROM ae_zone_leases active_lease
                    WHERE active_lease.zone_id = $2
                      AND active_lease.leased_until > $3
              )
            RETURNING *
            """,
            intent_id,
            zone_id,
            now,
        )
        if rows:
            intent = dict(rows[0])
            self._ports.global_intent_claimed().labels(source_status="pending").inc()
            return {"decision": "claimed", "intent": intent}

        existing_rows = await self._ports.global_fetch(
            """
            SELECT *
            FROM zone_automation_intents
            WHERE id = $1
              AND zone_id = $2
            LIMIT 1
            """,
            intent_id,
            zone_id,
        )
        if not existing_rows:
            return {"decision": "missing", "intent": {}}
        existing = dict(existing_rows[0])
        status = str(existing.get("status") or "").strip().lower()
        if status in _ACTIVE_STATUSES:
            return {"decision": "deduplicated", "intent": existing}
        if status in _TERMINAL_STATUSES:
            return {"decision": "terminal", "intent": existing}
        if status in {"pending", "failed"}:
            return {
                "decision": "claim_race",
                "intent": existing,
                "requested_intent": existing,
            }
        return {"decision": "missing", "intent": existing}

    async def execution_busy_row(self, *, zone_id: int, now: datetime) -> dict[str, Any] | None:
        """Live ae_tasks / ae_zone_leases that must block a new intent claim."""
        rows = await self._ports.global_fetch(
            """
            SELECT kind, ref, extra
            FROM (
                SELECT 'task'::text AS kind,
                       t.id::text AS ref,
                       t.status::text AS extra
                FROM ae_tasks t
                WHERE t.zone_id = $1
                  AND t.status IN ('pending', 'claimed', 'running', 'waiting_command')
                UNION ALL
                SELECT 'lease'::text,
                       l.owner::text,
                       l.leased_until::text
                FROM ae_zone_leases l
                WHERE l.zone_id = $1
                  AND l.leased_until > $2
            ) busy
            LIMIT 1
            """,
            zone_id,
            now,
        )
        if not rows:
            return None
        row = dict(rows[0])
        kind = str(row.get("kind") or "").strip().lower()
        if kind == "task":
            raw_ref = str(row.get("ref") or "").strip()
            task_id = int(raw_ref) if raw_ref.isdigit() else None
            return {
                "id": task_id,
                "status": str(row.get("extra") or "").strip().lower(),
                "blocking_kind": "ae_task",
                "blocking_task_id": task_id,
            }
        return {
            "id": None,
            "status": "leased",
            "blocking_kind": "ae_zone_lease",
            "blocking_lease_owner": row.get("ref"),
            "blocking_leased_until": row.get("extra"),
        }

    async def claim_by_idempotency_key(
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
        rows = await self._ports.global_fetch(
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
                  AND NOT EXISTS (
                        SELECT 1
                        FROM ae_tasks active_task
                        WHERE active_task.zone_id = $1
                          AND active_task.status IN ('pending', 'claimed', 'running', 'waiting_command')
                  )
                  AND NOT EXISTS (
                        SELECT 1
                        FROM ae_zone_leases active_lease
                        WHERE active_lease.zone_id = $1
                          AND active_lease.leased_until > $3
                  )
                  AND EXISTS (
                        SELECT 1
                        FROM zones z
                        WHERE z.id = $1
                        FOR UPDATE
                  )
                  AND (
                        not_before IS NULL
                        OR not_before <= ($3::timestamptz + interval '1 second')
                  )
                  AND (status <> 'failed' OR retry_count < max_retries)
                ORDER BY id DESC
                FOR UPDATE
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
            self._ports.global_intent_claimed().labels(source_status=source_status).inc()
            if source_status in {"claimed", "running"}:
                self._ports.global_intent_stale_reclaimed().inc()
            return {"decision": "claimed", "intent": intent}

        existing_rows = await self._ports.global_fetch(
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
                # Retryable failed must not burn the window as terminal before
                # zone_busy: Laravel retries 409 busy with the same key.
                # completed/cancelled (and exhausted failed) stay terminal.
                # Stale claimed/running reclaim is handled by the CTE above.
                if not (status == "failed" and _is_retryable_failed_intent(existing)):
                    return {"decision": "terminal", "intent": existing}

        active_zone_rows = await self._ports.global_fetch(
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

        busy_row = await self.execution_busy_row(zone_id=zone_id, now=now)
        if busy_row is not None:
            return {
                "decision": "zone_busy",
                "intent": busy_row,
                "requested_intent": requested_intent,
            }

        if stale_same_key_running_intent:
            return {"decision": "deduplicated", "intent": stale_same_key_running_intent}

        # Pending/failed row exists for this key but the claim CTE could not lock it
        # (concurrent SKIP LOCKED / transient active-intent race). Surface the row so
        # callers can retry instead of treating it as a hard miss.
        if requested_intent:
            return {
                "decision": "claim_race",
                "intent": requested_intent,
                "requested_intent": requested_intent,
            }

        return {"decision": "missing", "intent": {}}
