"""PgAutomationTaskRepository stage transitions: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

import asyncpg

from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.entities.workflow_state import CorrectionState, WorkflowState
from ae3lite.infrastructure.repositories.task_persistence_shared import (
    ACTIVE_TASK_STATUSES,
    RUNNING_TASK_STATUSES,
    logger,
)


@dataclass(frozen=True)
class TaskPersistenceStageTransitionsPorts:
    correction_values: Callable[..., Any]
    execute: Callable[..., Awaitable[Any]]
    fetchrow: Callable[..., Awaitable[Any]]
    log_fsm_cas_miss: Callable[..., Awaitable[Any]]
    log_fsm_success: Callable[..., Any]
    normalize_meta: Callable[..., Any]
    normalize_timestamp: Callable[..., Any]
    task_from_row: Callable[..., Any]
    update_task_status: Callable[..., Awaitable[Any]]


class TaskPersistenceStageTransitions:
    def __init__(self, ports: TaskPersistenceStageTransitionsPorts) -> None:
        self._ports = ports

    async def mark_start_event_emitted(self, *, task_id: int) -> None:
        """Помечает задачу как уже получившую AE_TASK_STARTED событие (идемпотентно)."""
        await self._ports.execute(
            """
            UPDATE ae_tasks
            SET start_event_emitted = TRUE
            WHERE id = $1
            """,
            task_id,
        )

    async def increment_irr_probe_failure_streak(self, *, task_id: int) -> int:
        """Инкрементирует счётчик подряд идущих deferred probe IRR state и возвращает новое значение."""
        row = await self._ports.fetchrow(
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
        await self._ports.execute(
            """
            UPDATE ae_tasks
            SET irr_probe_failure_streak = 0
            WHERE id = $1
              AND irr_probe_failure_streak <> 0
            """,
            task_id,
        )

    async def mark_running(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        return await self._ports.update_task_status(
            task_id=task_id,
            owner=owner,
            next_status="running",
            allowed_statuses=("claimed", "running"),
            now=now,
            action="mark_running",
            claim_generation=claim_generation,
        )

    async def resume_after_waiting_command(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        return await self._ports.update_task_status(
            task_id=task_id,
            owner=owner,
            next_status="running",
            allowed_statuses=("waiting_command",),
            now=now,
            action="resume_after_waiting_command",
            claim_generation=claim_generation,
        )

    async def mark_waiting_command(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        return await self._ports.update_task_status(
            task_id=task_id,
            owner=owner,
            next_status="waiting_command",
            allowed_statuses=("claimed", "running", "waiting_command"),
            now=now,
            action="mark_waiting_command",
            claim_generation=claim_generation,
        )

    async def recover_waiting_command(
        self,
        *,
        task_id: int,
        now: datetime,
        owner: str,
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        """Переводит task в `waiting_command` после reconcile legacy-команды.

        Требует ``owner`` и ``claim_generation`` исходного claim.
        """
        normalized_now = self._ports.normalize_timestamp(now)
        normalized_owner = str(owner or "").strip()
        if not normalized_owner:
            return None
        row = await self._ports.fetchrow(
            """
            UPDATE ae_tasks
            SET status = 'waiting_command',
                updated_at = $2
            WHERE id = $1
              AND status = ANY($3::text[])
              AND claimed_by = $4
              AND claim_generation = $5
            RETURNING *
            """,
            task_id,
            normalized_now,
            list(RUNNING_TASK_STATUSES),
            normalized_owner,
            int(claim_generation),
        )
        return self._ports.task_from_row(row)

    async def update_stage(
        self,
        *,
        task_id: int,
        owner: str,
        workflow: WorkflowState,
        correction: CorrectionState | None,
        due_at: datetime,
        now: datetime,
        preserve_pending_manual_step: bool = False,
        claim_generation: int = 0,
        conn: asyncpg.Connection | None = None,
    ) -> AutomationTask | None:
        """Atomically update workflow + correction state and re-enqueue as pending.

        ``preserve_pending_manual_step=True`` keeps a concurrently injected
        operator step (POST /manual-step) that may have landed in DB while this
        tick was already in-flight with a stale in-memory workflow snapshot.
        """
        normalized_due_at = self._ports.normalize_timestamp(due_at)
        normalized_now = self._ports.normalize_timestamp(now)

        row = await self._ports.fetchrow(
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
                pending_manual_step   = CASE
                    WHEN $54::boolean THEN pending_manual_step
                    ELSE $9
                END,
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
                corr_pipeline_phase       = $42,
                corr_active_component     = $43,
                corr_water_ec             = $44,
                corr_water_ph             = $45,
                corr_nutrient_budget      = $46,
                corr_component_targets_json = $47,
                corr_dilute_attempts      = $48,
                corr_ec_pid_frozen        = $49,
                corr_baseline_id          = $50,
                corr_limit_policy_logged  = $51,
                due_at     = $52,
                process_run_id = NULL,
                updated_at = $53
            WHERE id = $1
              AND claimed_by = $2
              AND claim_generation = $55
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
            *self._ports.correction_values(correction),
            normalized_due_at,
            normalized_now,
            bool(preserve_pending_manual_step),
            int(claim_generation),
            conn=conn,
        )
        task = self._ports.task_from_row(row)
        if task is not None:
            self._ports.log_fsm_success(
                action="requeue",
                task=task,
                from_status="claimed|running|waiting_command",
                to_status="pending",
                owner=owner,
            )
            await self.sync_intent_after_task_requeue(task=task, now=normalized_now, conn=conn)
        else:
            await self._ports.log_fsm_cas_miss(
                action="update_stage",
                task_id=task_id,
                to_status="pending",
                owner=owner,
                conn=conn,
            )
        return task

    async def sync_intent_after_task_requeue(
        self,
        *,
        task: AutomationTask,
        now: datetime,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        """Обновляет intent.updated_at при штатном requeue ae_task → pending (multi-stage workflow)."""
        intent_id = int(getattr(task, "intent_id", 0) or 0)
        if intent_id <= 0:
            return
        try:
            await self._ports.execute(
                """
                UPDATE zone_automation_intents
                SET updated_at = $2
                WHERE id = $1
                  AND status = 'running'
                """,
                intent_id,
                now,
                conn=conn,
            )
        except Exception:
            if conn is not None:
                # An error in the shared transaction must roll back task progress.
                raise
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
        normalized_now = self._ports.normalize_timestamp(now)
        row = await self._ports.fetchrow(
            """
            UPDATE ae_tasks
            SET pending_manual_step = $2,
                due_at = $3,
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
        return self._ports.task_from_row(row)

    async def update_control_mode_snapshot_for_zone(
        self,
        *,
        zone_id: int,
        control_mode: str,
        now: datetime,
    ) -> AutomationTask | None:
        normalized_now = self._ports.normalize_timestamp(now)
        row = await self._ports.fetchrow(
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
        return self._ports.task_from_row(row)

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
        normalized_now = self._ports.normalize_timestamp(now)
        normalized_meta = self._ports.normalize_meta(metadata)
        result = await self._ports.execute(
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
        # asyncpg execute() возвращает PostgreSQL CommandStatus: "INSERT oid rows".
        # rows == 0 означает, что task row был удалён cleanup-ом (FK guard).
        status = str(result).strip()
        if status.startswith("INSERT") and status.split()[-1] == "0":
            logger.warning(
                "AE3 record_transition skipped because task row was missing: task_id=%s from=%s to=%s",
                task_id,
                from_stage,
                to_stage,
            )
