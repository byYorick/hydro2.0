"""PostgreSQL-репозиторий задач автоматизации AE3-Lite."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Mapping

import asyncpg

from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.entities.workflow_state import CorrectionState, WorkflowState
from ae3lite.infrastructure.metrics import (
    OLDEST_ACTIVE_TASK_AGE_SECONDS,
    OLDEST_PENDING_TASK_AGE_SECONDS,
    PENDING_TASKS,
    TASK_DURATION_SECONDS,
)
from common.db import execute, get_pool

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
    "snapshot_event_id",
    "snapshot_created_at",
    "snapshot_cmd_id",
    "snapshot_source_event_type",
)

class PgAutomationTaskRepository:
    """Атомарный CRUD задач и переходы состояния для AE3-Lite v2."""

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
            # Поддерживать согласованность NOT NULL колонок коррекции, когда коррекция неактивна.
            # Некоторые поля БД, например `corr_ec_current_seq_index`, имеют NOT NULL и default.
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
        """Возвращает самую свежую задачу зоны независимо от статуса."""
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

    async def list_for_startup_recovery(
        self,
        *,
        worker_owner: str | None = None,
        now: datetime | None = None,
    ) -> list[AutomationTask]:
        normalized_worker = str(worker_owner or "").strip()
        if normalized_worker and now is not None:
            normalized_now = self._normalize_timestamp(now)
            rows = await self._fetch(
                """
                SELECT tasks.*
                FROM ae_tasks AS tasks
                WHERE tasks.status = ANY($1::text[])
                  AND NOT (
                    tasks.claimed_by IS NOT NULL
                    AND tasks.claimed_by <> $2
                    AND EXISTS (
                        SELECT 1
                        FROM ae_zone_leases AS leases
                        WHERE leases.zone_id = tasks.zone_id
                          AND leases.owner IS NOT NULL
                          AND leases.owner <> $2
                          AND leases.leased_until > $3
                    )
                  )
                ORDER BY tasks.updated_at ASC, tasks.id ASC
                """,
                list(RUNNING_TASK_STATUSES),
                normalized_worker,
                normalized_now,
            )
        else:
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

    async def list_waiting_command_for_reconcile(self, *, limit: int = 32) -> list[AutomationTask]:
        """Возвращает `waiting_command` задачи для фонового reconcile (oldest first)."""
        bounded_limit = max(1, min(int(limit), 200))
        rows = await self._fetch(
            """
            SELECT *
            FROM ae_tasks
            WHERE status = 'waiting_command'
            ORDER BY updated_at ASC, id ASC
            LIMIT $1
            """,
            bounded_limit,
        )
        return [AutomationTask.from_row(row) for row in rows]

    async def list_stale_claimed_running_for_reconcile(
        self,
        *,
        now: datetime,
        stale_claimed_before: datetime,
        stale_running_before: datetime,
        limit: int = 16,
    ) -> list[AutomationTask]:
        """Stale claimed/running задачи для janitor (FOR UPDATE SKIP LOCKED, batch ≤16)."""
        normalized_claimed_before = self._normalize_timestamp(stale_claimed_before)
        normalized_running_before = self._normalize_timestamp(stale_running_before)
        bounded_limit = max(1, min(int(limit), 16))
        async with self._connection() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    WITH stale AS (
                        SELECT id
                        FROM ae_tasks
                        WHERE (
                            status = 'claimed'
                            AND claimed_at IS NOT NULL
                            AND claimed_at < $1
                        ) OR (
                            status = 'running'
                            AND updated_at < $2
                        )
                        ORDER BY updated_at ASC, id ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT $3
                    )
                    SELECT tasks.*
                    FROM ae_tasks AS tasks
                    INNER JOIN stale ON stale.id = tasks.id
                    ORDER BY tasks.updated_at ASC, tasks.id ASC
                    """,
                    normalized_claimed_before,
                    normalized_running_before,
                    bounded_limit,
                )
        return [AutomationTask.from_row(row) for row in rows]

    async def task_has_ae_commands(self, *, task_id: int) -> bool:
        row = await self._fetchrow(
            """
            SELECT EXISTS(
                SELECT 1
                FROM ae_commands
                WHERE task_id = $1
            ) AS has_commands
            """,
            task_id,
        )
        return bool(row["has_commands"]) if row is not None else False

    async def fetch_pending_with_idle_zone_workflow_rows(self) -> list[Any]:
        """Pending-задачи при workflow_phase=idle (часто после терминального stop в payload)."""
        return await self._fetch(
            """
            SELECT t.*, zws.payload->>'ae3_cycle_start_stage' AS snapshot_stage
            FROM ae_tasks t
            INNER JOIN zone_workflow_state zws ON zws.zone_id = t.zone_id
            WHERE t.status = 'pending'
              AND zws.workflow_phase = 'idle'
            ORDER BY t.id ASC
            """,
        )

    # ── Создание ────────────────────────────────────────────────────

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
        task = self._task_from_row(row)
        if task is not None:
            self._log_fsm_success(
                action="claim",
                task=task,
                from_status="pending",
                to_status="claimed",
                owner=owner,
            )
        return task

    async def refresh_pending_queue_metrics(self, *, now: datetime) -> None:
        """Обновляет gauge метрики очереди pending одним SQL-запросом."""
        normalized_now = self._normalize_timestamp(now)
        row = await self._fetchrow(
            """
            SELECT
                COUNT(*)::double precision AS pending_count,
                COALESCE(
                    EXTRACT(EPOCH FROM ($1 - MIN(created_at))),
                    0
                )::double precision AS oldest_age_sec
            FROM ae_tasks
            WHERE status = 'pending'
            """,
            normalized_now,
        )
        if row is None:
            PENDING_TASKS.set(0)
            OLDEST_PENDING_TASK_AGE_SECONDS.set(0)
            return
        PENDING_TASKS.set(float(row["pending_count"] or 0))
        OLDEST_PENDING_TASK_AGE_SECONDS.set(max(0.0, float(row["oldest_age_sec"] or 0)))

    async def refresh_active_task_age_metrics(self, *, now: datetime) -> None:
        """Обновляет gauge возраста самой старой активной задачи по статусу."""
        normalized_now = self._normalize_timestamp(now)
        for status in ("claimed", "running", "waiting_command"):
            OLDEST_ACTIVE_TASK_AGE_SECONDS.labels(status=status).set(0.0)
        rows = await self._fetch(
            """
            SELECT
                status,
                COALESCE(
                    EXTRACT(EPOCH FROM ($1 - MIN(updated_at))),
                    0
                )::double precision AS oldest_age_sec
            FROM ae_tasks
            WHERE status IN ('claimed', 'running', 'waiting_command')
            GROUP BY status
            """,
            normalized_now,
        )
        for row in rows:
            status = str(row["status"] or "").strip()
            if not status:
                continue
            OLDEST_ACTIVE_TASK_AGE_SECONDS.labels(status=status).set(
                max(0.0, float(row["oldest_age_sec"] or 0))
            )

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

    async def requeue_unpublished_execution(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
    ) -> AutomationTask | None:
        """Откатывает `claimed|running` без `ae_commands` в `pending` для graceful shutdown."""
        normalized_now = self._normalize_timestamp(now)
        row = await self._fetchrow(
            """
            UPDATE ae_tasks AS tasks
            SET status = 'pending',
                claimed_by = NULL,
                claimed_at = NULL,
                updated_at = $3
            WHERE tasks.id = $1
              AND tasks.status IN ('claimed', 'running')
              AND tasks.claimed_by = $2
              AND NOT EXISTS (
                  SELECT 1
                  FROM ae_commands AS commands
                  WHERE commands.task_id = tasks.id
              )
            RETURNING tasks.*
            """,
            task_id,
            owner,
            normalized_now,
        )
        task = self._task_from_row(row)
        if task is not None:
            self._log_fsm_success(
                action="requeue",
                task=task,
                from_status="claimed|running",
                to_status="pending",
                owner=owner,
            )
        else:
            await self._log_fsm_cas_miss(
                action="requeue",
                task_id=task_id,
                to_status="pending",
                owner=owner,
            )
        return task

    async def list_claimed_by_owner(self, *, owner: str) -> list[AutomationTask]:
        rows = await self._fetch(
            """
            SELECT *
            FROM ae_tasks
            WHERE status = 'claimed'
              AND claimed_by = $1
            ORDER BY claimed_at ASC NULLS LAST, id ASC
            """,
            owner,
        )
        return [self._task_from_row(row) for row in rows]

    async def list_unpublished_execution_by_owner(self, *, owner: str) -> list[AutomationTask]:
        rows = await self._fetch(
            """
            SELECT tasks.*
            FROM ae_tasks AS tasks
            WHERE tasks.claimed_by = $1
              AND tasks.status IN ('claimed', 'running')
              AND NOT EXISTS (
                  SELECT 1
                  FROM ae_commands AS commands
                  WHERE commands.task_id = tasks.id
              )
            ORDER BY tasks.claimed_at ASC NULLS LAST, tasks.id ASC
            """,
            owner,
        )
        return [self._task_from_row(row) for row in rows]

    # ── Status transitions ──────────────────────────────────────────

    async def mark_start_event_emitted(self, *, task_id: int) -> None:
        """Помечает задачу как уже получившую AE_TASK_STARTED событие (идемпотентно)."""
        await self._execute(
            """
            UPDATE ae_tasks
            SET start_event_emitted = TRUE
            WHERE id = $1
            """,
            task_id,
        )

    async def increment_irr_probe_failure_streak(self, *, task_id: int) -> int:
        """Инкрементирует счётчик подряд идущих deferred probe IRR state и возвращает новое значение."""
        row = await self._fetchrow(
            """
            UPDATE ae_tasks
            SET irr_probe_failure_streak = irr_probe_failure_streak + 1
            WHERE id = $1
            RETURNING irr_probe_failure_streak
            """,
            task_id,
        )
        return int(row["irr_probe_failure_streak"]) if row is not None else 0

    async def reset_irr_probe_failure_streak(self, *, task_id: int) -> None:
        """Сбрасывает счётчик deferred probe после успешного probe или transition."""
        await self._execute(
            """
            UPDATE ae_tasks
            SET irr_probe_failure_streak = 0
            WHERE id = $1
              AND irr_probe_failure_streak <> 0
            """,
            task_id,
        )

    async def mark_running(self, *, task_id: int, owner: str, now: datetime) -> AutomationTask | None:
        return await self._update_task_status(
            task_id=task_id,
            owner=owner,
            next_status="running",
            allowed_statuses=("claimed", "running"),
            now=now,
            action="mark_running",
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
            action="resume_after_waiting_command",
        )

    async def mark_waiting_command(self, *, task_id: int, owner: str, now: datetime) -> AutomationTask | None:
        return await self._update_task_status(
            task_id=task_id,
            owner=owner,
            next_status="waiting_command",
            allowed_statuses=("claimed", "running", "waiting_command"),
            now=now,
            action="mark_waiting_command",
        )

    async def recover_waiting_command(
        self,
        *,
        task_id: int,
        now: datetime,
        owner: str,
    ) -> AutomationTask | None:
        """Переводит task в `waiting_command` после reconcile legacy-команды.

        Требует ``owner`` (``task.claimed_by``): guard ``claimed_by = owner`` защищает
        от split-brain, когда другой worker уже держит lease на зону.
        """
        normalized_now = self._normalize_timestamp(now)
        normalized_owner = str(owner or "").strip()
        if not normalized_owner:
            return None
        row = await self._fetchrow(
            """
            UPDATE ae_tasks
            SET status = 'waiting_command',
                updated_at = $2
            WHERE id = $1
              AND status = ANY($3::text[])
              AND claimed_by = $4
            RETURNING *
            """,
            task_id,
            normalized_now,
            list(RUNNING_TASK_STATUSES),
            normalized_owner,
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
                corr_snapshot_event_id    = $38,
                corr_snapshot_created_at  = $39,
                corr_snapshot_cmd_id      = $40,
                corr_snapshot_source_event_type = $41,
                corr_limit_policy_logged  = $42,
                due_at     = $43,
                updated_at = $44
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
        task = self._task_from_row(row)
        if task is not None:
            self._log_fsm_success(
                action="requeue",
                task=task,
                from_status="claimed|running|waiting_command",
                to_status="pending",
                owner=owner,
            )
            await self._sync_intent_after_task_requeue(task=task, now=normalized_now)
        else:
            await self._log_fsm_cas_miss(
                action="update_stage",
                task_id=task_id,
                to_status="pending",
                owner=owner,
            )
        return task

    async def _sync_intent_after_task_requeue(self, *, task: AutomationTask, now: datetime) -> None:
        """Обновляет intent.updated_at при штатном requeue ae_task → pending (multi-stage workflow)."""
        intent_id = int(getattr(task, "intent_id", 0) or 0)
        if intent_id <= 0:
            return
        try:
            await execute(
                """
                UPDATE zone_automation_intents
                SET updated_at = $2
                WHERE id = $1
                  AND status = 'running'
                """,
                intent_id,
                now,
            )
        except Exception:
            logger.warning(
                "AE3 не смог синхронизировать intent после requeue: intent_id=%s task_id=%s",
                intent_id,
                getattr(task, "id", None),
                exc_info=True,
            )

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
                SET control_mode_snapshot = $2::varchar,
                    pending_manual_step = CASE
                        WHEN $2::text = 'auto' THEN NULL
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
        task = self._task_from_row(row)
        if task is not None:
            self._observe_task_duration(row=row, outcome="completed")
            self._log_fsm_success(
                action="terminal",
                task=task,
                from_status="claimed|running|waiting_command",
                to_status="completed",
                owner=owner,
            )
        else:
            await self._log_fsm_cas_miss(
                action="terminal",
                task_id=task_id,
                to_status="completed",
                owner=owner,
            )
        return task

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

    async def fail_pending_or_active_for_recovery(
        self,
        *,
        task_id: int,
        error_code: str,
        error_message: str,
        now: datetime,
    ) -> AutomationTask | None:
        """Переводит задачу в failed для recovery/reconcile, включая pending (см. fail_for_recovery)."""
        normalized_now = self._normalize_timestamp(now)
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
            list(ACTIVE_TASK_STATUSES),
        )
        return self._task_from_row(row)

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
        action: str,
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
        task = self._task_from_row(row)
        if task is not None:
            self._log_fsm_success(
                action=action,
                task=task,
                from_status="|".join(allowed_statuses),
                to_status=next_status,
                owner=owner,
            )
            return task
        await self._log_fsm_cas_miss(
            action=action,
            task_id=task_id,
            to_status=next_status,
            owner=owner,
        )
        return None

    @staticmethod
    def _observe_task_duration(*, row: asyncpg.Record | None, outcome: str) -> None:
        if row is None:
            return
        created_at = row.get("created_at")
        completed_at = row.get("completed_at") or row.get("updated_at")
        if created_at is None or completed_at is None:
            return
        duration_sec = max(0.0, (completed_at - created_at).total_seconds())
        topology = str(row.get("topology") or "unknown").strip() or "unknown"
        TASK_DURATION_SECONDS.labels(topology=topology, outcome=outcome).observe(duration_sec)

    @staticmethod
    def _log_fsm_success(
        *,
        action: str,
        task: AutomationTask,
        from_status: str,
        to_status: str,
        owner: str,
    ) -> None:
        logger.info(
            "AE3 task FSM %s",
            action,
            extra={
                "task_id": int(task.id),
                "zone_id": int(task.zone_id),
                "from_status": from_status,
                "to_status": to_status,
                "owner": owner,
            },
        )

    async def _log_fsm_cas_miss(
        self,
        *,
        action: str,
        task_id: int,
        to_status: str,
        owner: str,
    ) -> None:
        current = await self.get_by_id(task_id=task_id)
        from_status = str(current.status if current is not None else "missing")
        zone_id = int(current.zone_id) if current is not None else None
        logger.warning(
            "AE3 task FSM CAS miss %s",
            action,
            extra={
                "task_id": int(task_id),
                "zone_id": zone_id,
                "from_status": from_status,
                "to_status": to_status,
                "owner": owner,
            },
        )

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

        task = self._task_from_row(row)
        if task is not None:
            self._observe_task_duration(row=row, outcome="failed")
            self._log_fsm_success(
                action="terminal",
                task=task,
                from_status="claimed|running|waiting_command",
                to_status="failed",
                owner=str(owner or task.claimed_by or ""),
            )
        elif require_owner and owner is not None:
            await self._log_fsm_cas_miss(
                action="terminal",
                task_id=task_id,
                to_status="failed",
                owner=owner,
            )
        return task
