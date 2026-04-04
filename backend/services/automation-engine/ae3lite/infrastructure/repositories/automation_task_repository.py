"""PostgreSQL repository for AE3-Lite automation tasks."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Mapping

import asyncpg

from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.entities.workflow_state import CorrectionState, WorkflowState
from common.db import get_pool

logger = logging.getLogger(__name__)

ACTIVE_TASK_STATUSES = ("pending", "claimed", "running", "waiting_command")
RUNNING_TASK_STATUSES = ("claimed", "running", "waiting_command")
CORRECTION_OPTIONAL_FIELDS = (
    "corr_step",
    "attempt",
    "max_attempts",
    "ec_attempt",
    "ec_max_attempts",
    "ph_attempt",
    "ph_max_attempts",
    "activated_here",
    "stabilization_sec",
    "return_stage_success",
    "return_stage_fail",
    "outcome_success",
    "needs_ec",
    "ec_node_uid",
    "ec_channel",
    "ec_duration_ms",
    "needs_ph_up",
    "needs_ph_down",
    "ph_node_uid",
    "ph_channel",
    "ph_duration_ms",
    "wait_until",
    "ec_component",
    "ec_amount_ml",
    "ec_dose_sequence_json",
    "ec_current_seq_index",
    "ph_amount_ml",
)

class PgAutomationTaskRepository:
    """Atomic task CRUD / state transitions for AE3-Lite v2."""

    def _normalize_timestamp(self, value: datetime) -> datetime:
        normalized = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo is not None else value
        return normalized.replace(microsecond=0)

    def _normalize_meta(self, value: Mapping[str, Any] | None) -> dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    def _normalize_json_mapping(self, value: Mapping[str, Any] | None) -> dict[str, Any] | None:
        return dict(value) if isinstance(value, Mapping) else None

    def _task_from_row(self, row: asyncpg.Record | None) -> AutomationTask | None:
        return AutomationTask.from_row(row) if row is not None else None

    def _correction_values(self, correction: CorrectionState | None) -> tuple[Any, ...]:
        if correction is None:
            # Keep NOT NULL correction columns consistent when correction is inactive.
            # Some DB columns (e.g. corr_ec_current_seq_index) are NOT NULL with defaults.
            values: list[Any] = [None] * len(CORRECTION_OPTIONAL_FIELDS)
            try:
                idx = CORRECTION_OPTIONAL_FIELDS.index("ec_current_seq_index")
                values[idx] = 0
            except ValueError:
                pass
            return (*tuple(values), False)

        values = tuple(getattr(correction, field_name) for field_name in CORRECTION_OPTIONAL_FIELDS)
        return (*values, bool(correction.limit_policy_logged))

    @asynccontextmanager
    async def _connection(self, conn: asyncpg.Connection | None = None) -> AsyncIterator[asyncpg.Connection]:
        if conn is not None:
            yield conn
            return

        pool = await get_pool()
        async with pool.acquire() as acquired_conn:
            yield acquired_conn

    async def _fetchrow(
        self,
        query: str,
        *args: Any,
        conn: asyncpg.Connection | None = None,
    ) -> asyncpg.Record | None:
        async with self._connection(conn) as db_conn:
            return await db_conn.fetchrow(query, *args)

    async def _fetch(
        self,
        query: str,
        *args: Any,
        conn: asyncpg.Connection | None = None,
    ) -> list[asyncpg.Record]:
        async with self._connection(conn) as db_conn:
            return await db_conn.fetch(query, *args)

    async def _execute(
        self,
        query: str,
        *args: Any,
        conn: asyncpg.Connection | None = None,
    ) -> str:
        async with self._connection(conn) as db_conn:
            return await db_conn.execute(query, *args)

    # ── Reads ───────────────────────────────────────────────────────

    async def get_by_idempotency_key(self, *, zone_id: int, idempotency_key: str) -> AutomationTask | None:
        normalized_key = str(idempotency_key or "").strip()
        if normalized_key == "":
            return None

        row = await self._fetchrow(
            """
            SELECT *
            FROM ae_tasks
            WHERE zone_id = $1
              AND idempotency_key = $2
            LIMIT 1
            """,
            zone_id,
            normalized_key,
        )
        return self._task_from_row(row)

    async def get_active_for_zone(self, *, zone_id: int) -> AutomationTask | None:
        return await self.get_active_for_zone_with_conn(zone_id=zone_id)

    async def get_active_for_zone_with_conn(
        self,
        *,
        zone_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> AutomationTask | None:
        row = await self._fetchrow(
            """
            SELECT *
            FROM ae_tasks
            WHERE zone_id = $1
              AND status = ANY($2::text[])
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            zone_id,
            list(ACTIVE_TASK_STATUSES),
            conn=conn,
        )
        return self._task_from_row(row)

    async def get_last_for_zone(self, *, zone_id: int) -> AutomationTask | None:
        """Return the most recent task for a zone regardless of status."""
        row = await self._fetchrow(
            """
            SELECT *
            FROM ae_tasks
            WHERE zone_id = $1
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            zone_id,
        )
        return self._task_from_row(row)

    async def get_by_id(self, *, task_id: int) -> AutomationTask | None:
        row = await self._fetchrow(
            """
            SELECT *
            FROM ae_tasks
            WHERE id = $1
            LIMIT 1
            """,
            task_id,
        )
        return self._task_from_row(row)

    async def list_for_startup_recovery(self) -> list[AutomationTask]:
        rows = await self._fetch(
            """
            SELECT *
            FROM ae_tasks
            WHERE status = ANY($1::text[])
            ORDER BY updated_at ASC, id ASC
            """,
            list(RUNNING_TASK_STATUSES),
        )
        return [AutomationTask.from_row(row) for row in rows]

    # ── Create ──────────────────────────────────────────────────────

    async def create_pending(
        self,
        *,
        zone_id: int,
        idempotency_key: str,
        task_type: str,
        topology: str,
        current_stage: str,
        workflow_phase: str,
        intent_source: str | None = None,
        intent_trigger: str | None = None,
        intent_id: int | None = None,
        intent_meta: Mapping[str, Any] | None = None,
        scheduled_for: datetime,
        due_at: datetime,
        now: datetime,
        irrigation_mode: str | None = None,
        irrigation_requested_duration_sec: int | None = None,
        irrigation_decision_strategy: str | None = None,
        irrigation_decision_config: Mapping[str, Any] | None = None,
        irrigation_bundle_revision: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> AutomationTask | None:
        normalized_scheduled_for = self._normalize_timestamp(scheduled_for)
        normalized_due_at = self._normalize_timestamp(due_at)
        normalized_now = self._normalize_timestamp(now)
        normalized_meta = self._normalize_meta(intent_meta)
        normalized_decision_config = self._normalize_json_mapping(irrigation_decision_config)

        try:
            row = await self._fetchrow(
                """
                INSERT INTO ae_tasks (
                    zone_id, task_type, status, idempotency_key,
                    topology, current_stage, workflow_phase,
                    control_mode_snapshot,
                    irrigation_mode, irrigation_requested_duration_sec,
                    irrigation_decision_strategy, irrigation_decision_config, irrigation_bundle_revision,
                    intent_source, intent_trigger, intent_id, intent_meta,
                    scheduled_for, due_at, stage_entered_at,
                    created_at, updated_at
                )
                VALUES (
                    $1, $2, 'pending', $3,
                    $4, $5, $6,
                    (SELECT control_mode FROM zones WHERE id = $1),
                    $7, $8, $9, $10::jsonb, $11,
                    $12, $13, $14, $15::jsonb,
                    $16, $17, $18,
                    $18, $18
                )
                RETURNING *
                """,
                zone_id,
                task_type,
                idempotency_key,
                topology,
                current_stage,
                workflow_phase,
                irrigation_mode,
                irrigation_requested_duration_sec,
                irrigation_decision_strategy,
                normalized_decision_config,
                irrigation_bundle_revision,
                intent_source,
                intent_trigger,
                intent_id,
                normalized_meta,
                normalized_scheduled_for,
                normalized_due_at,
                normalized_now,
                conn=conn,
            )
        except asyncpg.UniqueViolationError:
            return None

        return self._task_from_row(row)

    async def update_irrigation_runtime(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
        irrigation_mode: str | None = None,
        irrigation_requested_duration_sec: int | None = None,
        irrigation_decision_strategy: str | None = None,
        irrigation_decision_config: Mapping[str, Any] | None = None,
        irrigation_bundle_revision: str | None = None,
        irrigation_decision_outcome: str | None = None,
        irrigation_decision_reason_code: str | None = None,
        irrigation_decision_degraded: bool | None = None,
        irrigation_replay_count: int | None = None,
        irrigation_wait_ready_deadline_at: datetime | None = None,
        irrigation_setup_deadline_at: datetime | None = None,
    ) -> AutomationTask | None:
        normalized_now = self._normalize_timestamp(now)
        normalized_wait_ready_deadline_at = (
            self._normalize_timestamp(irrigation_wait_ready_deadline_at)
            if irrigation_wait_ready_deadline_at is not None
            else None
        )
        normalized_setup_deadline_at = (
            self._normalize_timestamp(irrigation_setup_deadline_at)
            if irrigation_setup_deadline_at is not None
            else None
        )
        normalized_decision_config = self._normalize_json_mapping(irrigation_decision_config)
        row = await self._fetchrow(
            """
            UPDATE ae_tasks
            SET irrigation_mode = COALESCE($3, irrigation_mode),
                irrigation_requested_duration_sec = COALESCE($4, irrigation_requested_duration_sec),
                irrigation_decision_strategy = COALESCE($5, irrigation_decision_strategy),
                irrigation_decision_config = COALESCE($6::jsonb, irrigation_decision_config),
                irrigation_bundle_revision = COALESCE($7, irrigation_bundle_revision),
                irrigation_decision_outcome = COALESCE($8, irrigation_decision_outcome),
                irrigation_decision_reason_code = COALESCE($9, irrigation_decision_reason_code),
                irrigation_decision_degraded = CASE
                    WHEN $10::boolean IS NULL THEN irrigation_decision_degraded
                    ELSE $10
                END,
                irrigation_replay_count = COALESCE($11, irrigation_replay_count),
                irrigation_wait_ready_deadline_at = CASE
                    WHEN $12::timestamptz IS NULL THEN irrigation_wait_ready_deadline_at
                    ELSE $12
                END,
                irrigation_setup_deadline_at = CASE
                    WHEN $13::timestamptz IS NULL THEN irrigation_setup_deadline_at
                    ELSE $13
                END,
                updated_at = $14
            WHERE id = $1
              AND claimed_by = $2
              AND status IN ('claimed', 'running', 'waiting_command')
            RETURNING *
            """,
            task_id,
            owner,
            irrigation_mode,
            irrigation_requested_duration_sec,
            irrigation_decision_strategy,
            normalized_decision_config,
            irrigation_bundle_revision,
            irrigation_decision_outcome,
            irrigation_decision_reason_code,
            irrigation_decision_degraded,
            irrigation_replay_count,
            normalized_wait_ready_deadline_at,
            normalized_setup_deadline_at,
            normalized_now,
        )
        return self._task_from_row(row)

    # ── Claim / release ─────────────────────────────────────────────

    async def claim_next_pending(self, *, owner: str, now: datetime) -> AutomationTask | None:
        normalized_now = self._normalize_timestamp(now)
        async with self._connection() as conn:
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
        return self._task_from_row(row)

    async def next_pending_due_at(self) -> datetime | None:
        row = await self._fetchrow(
            """
            SELECT due_at
            FROM ae_tasks
            WHERE status = 'pending'
            ORDER BY due_at ASC, created_at ASC, id ASC
            LIMIT 1
            """
        )
        return None if row is None else row["due_at"]

    async def release_claim(self, *, task_id: int, owner: str, now: datetime) -> bool:
        normalized_now = self._normalize_timestamp(now)
        row = await self._fetchrow(
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

    async def mark_running(self, *, task_id: int, owner: str, now: datetime) -> AutomationTask | None:
        return await self._update_task_status(
            task_id=task_id,
            owner=owner,
            next_status="running",
            allowed_statuses=("claimed", "running"),
            now=now,
        )

    async def resume_after_waiting_command(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
    ) -> AutomationTask | None:
        return await self._update_task_status(
            task_id=task_id,
            owner=owner,
            next_status="running",
            allowed_statuses=("waiting_command",),
            now=now,
        )

    async def mark_waiting_command(self, *, task_id: int, owner: str, now: datetime) -> AutomationTask | None:
        return await self._update_task_status(
            task_id=task_id,
            owner=owner,
            next_status="waiting_command",
            allowed_statuses=("claimed", "running", "waiting_command"),
            now=now,
        )

    async def recover_waiting_command(self, *, task_id: int, now: datetime) -> AutomationTask | None:
        normalized_now = self._normalize_timestamp(now)
        row = await self._fetchrow(
            """
            UPDATE ae_tasks
            SET status = 'waiting_command',
                updated_at = $2
            WHERE id = $1
              AND status = ANY($3::text[])
            RETURNING *
            """,
            task_id,
            normalized_now,
            list(RUNNING_TASK_STATUSES),
        )
        return self._task_from_row(row)

    # ── Stage transition (replaces requeue_pending) ─────────────────

    async def update_stage(
        self,
        *,
        task_id: int,
        owner: str,
        workflow: WorkflowState,
        correction: CorrectionState | None,
        due_at: datetime,
        now: datetime,
    ) -> AutomationTask | None:
        """Atomically update workflow + correction state and re-enqueue as pending."""
        normalized_due_at = self._normalize_timestamp(due_at)
        normalized_now = self._normalize_timestamp(now)

        row = await self._fetchrow(
            """
            UPDATE ae_tasks
            SET status = 'pending',
                claimed_by            = NULL,
                claimed_at            = NULL,
                current_stage         = $3,
                workflow_phase        = $4,
                stage_deadline_at     = $5,
                stage_retry_count     = $6,
                stage_entered_at      = $7,
                clean_fill_cycle      = $8,
                pending_manual_step   = $9,
                control_mode_snapshot = $10,
                corr_step                 = $11,
                corr_attempt              = $12,
                corr_max_attempts         = $13,
                corr_ec_attempt           = $14,
                corr_ec_max_attempts      = $15,
                corr_ph_attempt           = $16,
                corr_ph_max_attempts      = $17,
                corr_activated_here       = $18,
                corr_stabilization_sec    = $19,
                corr_return_stage_success = $20,
                corr_return_stage_fail    = $21,
                corr_outcome_success      = $22,
                corr_needs_ec             = $23,
                corr_ec_node_uid          = $24,
                corr_ec_channel           = $25,
                corr_ec_duration_ms       = $26,
                corr_needs_ph_up          = $27,
                corr_needs_ph_down        = $28,
                corr_ph_node_uid          = $29,
                corr_ph_channel           = $30,
                corr_ph_duration_ms       = $31,
                corr_wait_until           = $32,
                corr_ec_component         = $33,
                corr_ec_amount_ml         = $34,
                corr_ec_dose_sequence_json = $35,
                corr_ec_current_seq_index  = $36,
                corr_ph_amount_ml         = $37,
                corr_limit_policy_logged  = $38,
                due_at     = $39,
                updated_at = $40
            WHERE id = $1
              AND claimed_by = $2
              AND status IN ('claimed', 'running', 'waiting_command')
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
            workflow.pending_manual_step,
            workflow.control_mode,
            *self._correction_values(correction),
            normalized_due_at,
            normalized_now,
        )
        return self._task_from_row(row)

    async def set_pending_manual_step(
        self,
        *,
        task_id: int,
        manual_step: str,
        now: datetime,
    ) -> AutomationTask | None:
        normalized_now = self._normalize_timestamp(now)
        row = await self._fetchrow(
            """
            UPDATE ae_tasks
            SET pending_manual_step = $2,
                updated_at = $3
            WHERE id = $1
              AND status = ANY($4::text[])
            RETURNING *
            """,
            task_id,
            manual_step,
            normalized_now,
            list(ACTIVE_TASK_STATUSES),
        )
        return self._task_from_row(row)

    async def update_control_mode_snapshot_for_zone(
        self,
        *,
        zone_id: int,
        control_mode: str,
        now: datetime,
    ) -> AutomationTask | None:
        normalized_now = self._normalize_timestamp(now)
        row = await self._fetchrow(
            """
            WITH updated AS (
                UPDATE ae_tasks
                SET control_mode_snapshot = $2,
                    pending_manual_step = CASE
                        WHEN $2 = 'auto' THEN NULL
                        ELSE pending_manual_step
                    END,
                    updated_at = $3
                WHERE zone_id = $1
                  AND status IN ('pending', 'claimed', 'running', 'waiting_command')
                RETURNING *
            )
            SELECT *
            FROM updated
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            zone_id,
            control_mode,
            normalized_now,
        )
        return self._task_from_row(row)

    # ── Terminal transitions ────────────────────────────────────────

    async def mark_completed(self, *, task_id: int, owner: str, now: datetime) -> AutomationTask | None:
        normalized_now = self._normalize_timestamp(now)
        row = await self._fetchrow(
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
        return self._task_from_row(row)

    async def mark_failed(
        self,
        *,
        task_id: int,
        owner: str,
        error_code: str,
        error_message: str,
        now: datetime,
    ) -> AutomationTask | None:
        return await self._mark_failed_row(
            task_id=task_id,
            error_code=error_code,
            error_message=error_message,
            now=now,
            owner=owner,
            require_owner=True,
        )

    async def fail_for_recovery(
        self,
        *,
        task_id: int,
        error_code: str,
        error_message: str,
        now: datetime,
    ) -> AutomationTask | None:
        return await self._mark_failed_row(
            task_id=task_id,
            error_code=error_code,
            error_message=error_message,
            now=now,
            owner=None,
            require_owner=False,
        )

    # ── Audit trail ─────────────────────────────────────────────────

    async def get_transitions_for_task(self, *, task_id: int, limit: int = 50) -> list[dict]:
        """Return stage transitions for a task ordered chronologically."""
        rows = await self._fetch(
            """
            SELECT from_stage, to_stage, workflow_phase, triggered_at, metadata
            FROM ae_stage_transitions
            WHERE task_id = $1
            ORDER BY triggered_at ASC, id ASC
            LIMIT $2
            """,
            task_id,
            limit,
        )
        return [dict(row) for row in rows]

    async def record_transition(
        self,
        *,
        task_id: int,
        from_stage: str | None,
        to_stage: str,
        workflow_phase: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        now: datetime,
    ) -> None:
        """INSERT into ae_stage_transitions (append-only audit log).

        If the task was already removed by cleanup, skip the transition silently.
        This keeps the audit trail best-effort and avoids FK races during teardown.
        """
        normalized_now = self._normalize_timestamp(now)
        normalized_meta = self._normalize_meta(metadata)
        result = await self._execute(
            """
            INSERT INTO ae_stage_transitions (
                task_id, from_stage, to_stage, workflow_phase,
                triggered_at, metadata
            )
            SELECT
                $1, $2, $3, $4, $5, $6::jsonb
            FROM ae_tasks
            WHERE id = $1
            """,
            task_id,
            from_stage,
            to_stage,
            workflow_phase,
            normalized_now,
            normalized_meta,
        )
        if str(result).strip().endswith("0 0"):
            logger.warning(
                "AE3 record_transition skipped because task row was missing: task_id=%s from=%s to=%s",
                task_id,
                from_stage,
                to_stage,
            )

    async def _update_task_status(
        self,
        *,
        task_id: int,
        owner: str,
        next_status: str,
        allowed_statuses: tuple[str, ...],
        now: datetime,
    ) -> AutomationTask | None:
        normalized_now = self._normalize_timestamp(now)
        row = await self._fetchrow(
            """
            UPDATE ae_tasks
            SET status = $3,
                updated_at = $4
            WHERE id = $1
              AND claimed_by = $2
              AND status = ANY($5::text[])
            RETURNING *
            """,
            task_id,
            owner,
            next_status,
            normalized_now,
            list(allowed_statuses),
        )
        return self._task_from_row(row)

    async def _mark_failed_row(
        self,
        *,
        task_id: int,
        error_code: str,
        error_message: str,
        now: datetime,
        owner: str | None,
        require_owner: bool,
    ) -> AutomationTask | None:
        normalized_now = self._normalize_timestamp(now)

        if require_owner:
            row = await self._fetchrow(
                """
                UPDATE ae_tasks
                SET status = 'failed',
                    error_code = $3,
                    error_message = $4,
                    updated_at = $5,
                    completed_at = $5
                WHERE id = $1
                  AND claimed_by = $2
                  AND status = ANY($6::text[])
                RETURNING *
                """,
                task_id,
                owner,
                error_code,
                error_message,
                normalized_now,
                list(RUNNING_TASK_STATUSES),
            )
        else:
            row = await self._fetchrow(
                """
                UPDATE ae_tasks
                SET status = 'failed',
                    error_code = $2,
                    error_message = $3,
                    updated_at = $4,
                    completed_at = $4
                WHERE id = $1
                  AND status = ANY($5::text[])
                RETURNING *
                """,
                task_id,
                error_code,
                error_message,
                normalized_now,
                list(RUNNING_TASK_STATUSES),
            )

        return self._task_from_row(row)
