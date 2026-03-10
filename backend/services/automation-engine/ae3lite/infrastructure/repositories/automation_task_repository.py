"""PostgreSQL repository for AE3-Lite automation tasks (v2 — explicit columns)."""

from __future__ import annotations

from datetime import timezone
from datetime import datetime
from typing import Any, Mapping, Optional

import asyncpg

from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.entities.workflow_state import CorrectionState, WorkflowState
from common.db import get_pool


class PgAutomationTaskRepository:
    """Atomic task CRUD / state transitions for AE3-Lite v2."""

    def _normalize_timestamp(self, value: datetime) -> datetime:
        normalized = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo is not None else value
        return normalized.replace(microsecond=0)

    # ── Reads ───────────────────────────────────────────────────────

    async def get_by_idempotency_key(self, *, idempotency_key: str) -> Optional[AutomationTask]:
        normalized_key = str(idempotency_key or "").strip()
        if normalized_key == "":
            return None

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM ae_tasks
                WHERE idempotency_key = $1
                LIMIT 1
                """,
                normalized_key,
            )
        return AutomationTask.from_row(row) if row is not None else None

    async def get_active_for_zone(self, *, zone_id: int) -> Optional[AutomationTask]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM ae_tasks
                WHERE zone_id = $1
                  AND status IN ('pending', 'claimed', 'running', 'waiting_command')
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                zone_id,
            )
        return AutomationTask.from_row(row) if row is not None else None

    async def get_by_id(self, *, task_id: int) -> Optional[AutomationTask]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM ae_tasks
                WHERE id = $1
                LIMIT 1
                """,
                task_id,
            )
        return AutomationTask.from_row(row) if row is not None else None

    async def list_for_startup_recovery(self) -> list[AutomationTask]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM ae_tasks
                WHERE status IN ('claimed', 'running', 'waiting_command')
                ORDER BY updated_at ASC, id ASC
                """
            )
        return [AutomationTask.from_row(row) for row in rows]

    # ── Create ──────────────────────────────────────────────────────

    async def create_pending(
        self,
        *,
        zone_id: int,
        idempotency_key: str,
        topology: str,
        intent_source: Optional[str] = None,
        intent_trigger: Optional[str] = None,
        intent_id: Optional[int] = None,
        intent_meta: Optional[Mapping[str, Any]] = None,
        scheduled_for: datetime,
        due_at: datetime,
        now: datetime,
    ) -> Optional[AutomationTask]:
        pool = await get_pool()
        normalized_scheduled_for = self._normalize_timestamp(scheduled_for)
        normalized_due_at = self._normalize_timestamp(due_at)
        normalized_now = self._normalize_timestamp(now)
        normalized_meta = dict(intent_meta) if isinstance(intent_meta, Mapping) else {}
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO ae_tasks (
                        zone_id, task_type, status, idempotency_key,
                        topology, current_stage, workflow_phase,
                        intent_source, intent_trigger, intent_id, intent_meta,
                        scheduled_for, due_at, stage_entered_at,
                        created_at, updated_at
                    )
                    VALUES (
                        $1, 'cycle_start', 'pending', $2,
                        $3, 'startup', 'idle',
                        $4, $5, $6, $7::jsonb,
                        $8, $9, $10,
                        $10, $10
                    )
                    RETURNING *
                    """,
                    zone_id,
                    idempotency_key,
                    topology,
                    intent_source,
                    intent_trigger,
                    intent_id,
                    normalized_meta,
                    normalized_scheduled_for,
                    normalized_due_at,
                    normalized_now,
                )
        except asyncpg.UniqueViolationError:
            return None
        return AutomationTask.from_row(row) if row is not None else None

    # ── Claim / release ─────────────────────────────────────────────

    async def claim_next_pending(self, *, owner: str, now: datetime) -> Optional[AutomationTask]:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    WITH candidate AS (
                        SELECT id
                        FROM ae_tasks
                        WHERE status = 'pending'
                          AND due_at <= $1
                        ORDER BY due_at ASC, created_at ASC, id ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE ae_tasks tasks
                    SET status = 'claimed',
                        claimed_by = $2,
                        claimed_at = $1,
                        updated_at = $1
                    FROM candidate
                    WHERE tasks.id = candidate.id
                    RETURNING tasks.*
                    """,
                    normalized_now,
                    owner,
                )
        return AutomationTask.from_row(row) if row is not None else None

    async def next_pending_due_at(self) -> Optional[datetime]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT due_at
                FROM ae_tasks
                WHERE status = 'pending'
                ORDER BY due_at ASC, created_at ASC, id ASC
                LIMIT 1
                """
            )
        if row is None:
            return None
        return row["due_at"]

    async def release_claim(self, *, task_id: int, owner: str, now: datetime) -> bool:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_tasks
                SET status = 'pending',
                    claimed_by = NULL,
                    claimed_at = NULL,
                    updated_at = $3
                WHERE id = $1
                  AND status = 'claimed'
                  AND claimed_by = $2
                RETURNING id
                """,
                task_id,
                owner,
                normalized_now,
            )
        return row is not None

    # ── Status transitions ──────────────────────────────────────────

    async def mark_running(self, *, task_id: int, owner: str, now: datetime) -> Optional[AutomationTask]:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_tasks
                SET status = 'running',
                    updated_at = $3
                WHERE id = $1
                  AND claimed_by = $2
                  AND status IN ('claimed', 'running')
                RETURNING *
                """,
                task_id,
                owner,
                normalized_now,
            )
        return AutomationTask.from_row(row) if row is not None else None

    async def resume_after_waiting_command(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
    ) -> Optional[AutomationTask]:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_tasks
                SET status = 'running',
                    updated_at = $3
                WHERE id = $1
                  AND claimed_by = $2
                  AND status = 'waiting_command'
                RETURNING *
                """,
                task_id,
                owner,
                normalized_now,
            )
        return AutomationTask.from_row(row) if row is not None else None

    async def mark_waiting_command(self, *, task_id: int, owner: str, now: datetime) -> Optional[AutomationTask]:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_tasks
                SET status = 'waiting_command',
                    updated_at = $3
                WHERE id = $1
                  AND claimed_by = $2
                  AND status IN ('claimed', 'running', 'waiting_command')
                RETURNING *
                """,
                task_id,
                owner,
                normalized_now,
            )
        return AutomationTask.from_row(row) if row is not None else None

    async def recover_waiting_command(self, *, task_id: int, now: datetime) -> Optional[AutomationTask]:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_tasks
                SET status = 'waiting_command',
                    updated_at = $2
                WHERE id = $1
                  AND status IN ('claimed', 'running', 'waiting_command')
                RETURNING *
                """,
                task_id,
                normalized_now,
            )
        return AutomationTask.from_row(row) if row is not None else None

    # ── Stage transition (replaces requeue_pending) ─────────────────

    async def update_stage(
        self,
        *,
        task_id: int,
        owner: str,
        workflow: WorkflowState,
        correction: Optional[CorrectionState],
        due_at: datetime,
        now: datetime,
    ) -> Optional[AutomationTask]:
        """Atomically update workflow + correction state and re-enqueue as pending."""
        pool = await get_pool()
        normalized_due_at = self._normalize_timestamp(due_at)
        normalized_now = self._normalize_timestamp(now)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_tasks
                SET status = 'pending',
                    current_stage         = $3,
                    workflow_phase        = $4,
                    stage_deadline_at     = $5,
                    stage_retry_count     = $6,
                    stage_entered_at      = $7,
                    clean_fill_cycle      = $8,
                    corr_step                 = $9,
                    corr_attempt              = $10,
                    corr_max_attempts         = $11,
                    corr_ec_attempt           = $12,
                    corr_ec_max_attempts      = $13,
                    corr_ph_attempt           = $14,
                    corr_ph_max_attempts      = $15,
                    corr_activated_here       = $16,
                    corr_stabilization_sec    = $17,
                    corr_return_stage_success = $18,
                    corr_return_stage_fail    = $19,
                    corr_outcome_success      = $20,
                    corr_needs_ec             = $21,
                    corr_ec_node_uid          = $22,
                    corr_ec_channel           = $23,
                    corr_ec_duration_ms       = $24,
                    corr_needs_ph_up          = $25,
                    corr_needs_ph_down        = $26,
                    corr_ph_node_uid          = $27,
                    corr_ph_channel           = $28,
                    corr_ph_duration_ms       = $29,
                    corr_wait_until           = $30,
                    due_at     = $31,
                    updated_at = $32
                WHERE id = $1
                  AND claimed_by = $2
                  AND status IN ('claimed', 'running')
                RETURNING *
                """,
                task_id,
                owner,
                workflow.current_stage,
                workflow.workflow_phase,
                workflow.stage_deadline_at,
                workflow.stage_retry_count,
                workflow.stage_entered_at,
                workflow.clean_fill_cycle,
                # correction (all None when correction is None)
                correction.corr_step if correction else None,
                correction.attempt if correction else None,
                correction.max_attempts if correction else None,
                correction.ec_attempt if correction else None,
                correction.ec_max_attempts if correction else None,
                correction.ph_attempt if correction else None,
                correction.ph_max_attempts if correction else None,
                correction.activated_here if correction else None,
                correction.stabilization_sec if correction else None,
                correction.return_stage_success if correction else None,
                correction.return_stage_fail if correction else None,
                correction.outcome_success if correction else None,
                correction.needs_ec if correction else None,
                correction.ec_node_uid if correction else None,
                correction.ec_channel if correction else None,
                correction.ec_duration_ms if correction else None,
                correction.needs_ph_up if correction else None,
                correction.needs_ph_down if correction else None,
                correction.ph_node_uid if correction else None,
                correction.ph_channel if correction else None,
                correction.ph_duration_ms if correction else None,
                correction.wait_until if correction else None,
                normalized_due_at,
                normalized_now,
            )
        return AutomationTask.from_row(row) if row is not None else None

    # ── Terminal transitions ────────────────────────────────────────

    async def mark_completed(self, *, task_id: int, owner: str, now: datetime) -> Optional[AutomationTask]:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_tasks
                SET status = 'completed',
                    updated_at = $3,
                    completed_at = $3,
                    error_code = NULL,
                    error_message = NULL
                WHERE id = $1
                  AND claimed_by = $2
                  AND status IN ('claimed', 'running', 'waiting_command')
                RETURNING *
                """,
                task_id,
                owner,
                normalized_now,
            )
        return AutomationTask.from_row(row) if row is not None else None

    async def mark_failed(
        self,
        *,
        task_id: int,
        owner: str,
        error_code: str,
        error_message: str,
        now: datetime,
    ) -> Optional[AutomationTask]:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_tasks
                SET status = 'failed',
                    error_code = $3,
                    error_message = $4,
                    updated_at = $5,
                    completed_at = $5
                WHERE id = $1
                  AND claimed_by = $2
                  AND status IN ('claimed', 'running', 'waiting_command')
                RETURNING *
                """,
                task_id,
                owner,
                error_code,
                error_message,
                normalized_now,
            )
        return AutomationTask.from_row(row) if row is not None else None

    async def fail_for_recovery(
        self,
        *,
        task_id: int,
        error_code: str,
        error_message: str,
        now: datetime,
    ) -> Optional[AutomationTask]:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_tasks
                SET status = 'failed',
                    error_code = $2,
                    error_message = $3,
                    updated_at = $4,
                    completed_at = $4
                WHERE id = $1
                  AND status IN ('claimed', 'running', 'waiting_command')
                RETURNING *
                """,
                task_id,
                error_code,
                error_message,
                normalized_now,
            )
        return AutomationTask.from_row(row) if row is not None else None

    # ── Audit trail ─────────────────────────────────────────────────

    async def record_transition(
        self,
        *,
        task_id: int,
        from_stage: Optional[str],
        to_stage: str,
        workflow_phase: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        now: datetime,
    ) -> None:
        """INSERT into ae_stage_transitions (append-only audit log)."""
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        normalized_meta = dict(metadata) if isinstance(metadata, Mapping) else {}
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ae_stage_transitions (
                    task_id, from_stage, to_stage, workflow_phase,
                    triggered_at, metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                """,
                task_id,
                from_stage,
                to_stage,
                workflow_phase,
                normalized_now,
                normalized_meta,
            )
