"""PostgreSQL-репозиторий задач автоматизации AE3-Lite."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Mapping

import asyncpg

from ae3lite.domain.entities import AutomationTask, ZoneLease
from ae3lite.domain.entities.workflow_state import CorrectionState, WorkflowState
from ae3lite.infrastructure.metrics import (
    OLDEST_ACTIVE_TASK_AGE_SECONDS,
    OLDEST_PENDING_TASK_AGE_SECONDS,
    PENDING_TASKS,
    TASK_DURATION_SECONDS,
)
from common.db import get_pool


from ae3lite.infrastructure.repositories.task_persistence_shared import (
    logger,
    _ZoneLeaseNotAcquired,
    ACTIVE_TASK_STATUSES,
    RUNNING_TASK_STATUSES,
    CORRECTION_OPTIONAL_FIELDS,
)

from ae3lite.infrastructure.repositories.task_persistence_mapping import (
    TaskPersistenceMapping,
    TaskPersistenceMappingPorts,
)
from ae3lite.infrastructure.repositories.task_persistence_connection import (
    TaskPersistenceConnection,
    TaskPersistenceConnectionPorts,
)
from ae3lite.infrastructure.repositories.task_persistence_queries import (
    TaskPersistenceQueries,
    TaskPersistenceQueriesPorts,
)
from ae3lite.infrastructure.repositories.task_persistence_creation import (
    TaskPersistenceCreation,
    TaskPersistenceCreationPorts,
)
from ae3lite.infrastructure.repositories.task_persistence_claim import TaskPersistenceClaim, TaskPersistenceClaimPorts
from ae3lite.infrastructure.repositories.task_persistence_stage_transitions import (
    TaskPersistenceStageTransitions,
    TaskPersistenceStageTransitionsPorts,
)
from ae3lite.infrastructure.repositories.task_persistence_terminal_transitions import (
    TaskPersistenceTerminalTransitions,
    TaskPersistenceTerminalTransitionsPorts,
)
from ae3lite.infrastructure.repositories.task_persistence_metrics import (
    TaskPersistenceMetrics,
    TaskPersistenceMetricsPorts,
)


class PgAutomationTaskRepository:
    """Атомарный CRUD задач и переходы состояния для AE3-Lite v2."""

    def __init__(self) -> None:
        self._task_persistence_mapping = TaskPersistenceMapping(TaskPersistenceMappingPorts())
        self._task_persistence_connection = TaskPersistenceConnection(
            TaskPersistenceConnectionPorts(
                global_get_pool=lambda *args, **kwargs: get_pool(*args, **kwargs),
            )
        )
        self._task_persistence_queries = TaskPersistenceQueries(
            TaskPersistenceQueriesPorts(
                connection=lambda *args, **kwargs: self._connection(*args, **kwargs),
                fetch=lambda *args, **kwargs: self._fetch(*args, **kwargs),
                fetchrow=lambda *args, **kwargs: self._fetchrow(*args, **kwargs),
                normalize_timestamp=lambda *args, **kwargs: self._normalize_timestamp(*args, **kwargs),
                task_from_row=lambda *args, **kwargs: self._task_from_row(*args, **kwargs),
            )
        )
        self._task_persistence_creation = TaskPersistenceCreation(
            TaskPersistenceCreationPorts(
                fetchrow=lambda *args, **kwargs: self._fetchrow(*args, **kwargs),
                normalize_json_mapping=lambda *args, **kwargs: self._normalize_json_mapping(*args, **kwargs),
                normalize_meta=lambda *args, **kwargs: self._normalize_meta(*args, **kwargs),
                normalize_timestamp=lambda *args, **kwargs: self._normalize_timestamp(*args, **kwargs),
                task_from_row=lambda *args, **kwargs: self._task_from_row(*args, **kwargs),
            )
        )
        self._task_persistence_claim = TaskPersistenceClaim(
            TaskPersistenceClaimPorts(
                connection=lambda *args, **kwargs: self._connection(*args, **kwargs),
                fetchrow=lambda *args, **kwargs: self._fetchrow(*args, **kwargs),
                log_fsm_cas_miss=lambda *args, **kwargs: self._log_fsm_cas_miss(*args, **kwargs),
                log_fsm_success=lambda *args, **kwargs: self._log_fsm_success(*args, **kwargs),
                normalize_timestamp=lambda *args, **kwargs: self._normalize_timestamp(*args, **kwargs),
                task_from_row=lambda *args, **kwargs: self._task_from_row(*args, **kwargs),
            )
        )
        self._task_persistence_stage_transitions = TaskPersistenceStageTransitions(
            TaskPersistenceStageTransitionsPorts(
                correction_values=lambda *args, **kwargs: self._correction_values(*args, **kwargs),
                execute=lambda *args, **kwargs: self._execute(*args, **kwargs),
                fetchrow=lambda *args, **kwargs: self._fetchrow(*args, **kwargs),
                log_fsm_cas_miss=lambda *args, **kwargs: self._log_fsm_cas_miss(*args, **kwargs),
                log_fsm_success=lambda *args, **kwargs: self._log_fsm_success(*args, **kwargs),
                normalize_meta=lambda *args, **kwargs: self._normalize_meta(*args, **kwargs),
                normalize_timestamp=lambda *args, **kwargs: self._normalize_timestamp(*args, **kwargs),
                task_from_row=lambda *args, **kwargs: self._task_from_row(*args, **kwargs),
                update_task_status=lambda *args, **kwargs: self._update_task_status(*args, **kwargs),
            )
        )
        self._task_persistence_terminal_transitions = TaskPersistenceTerminalTransitions(
            TaskPersistenceTerminalTransitionsPorts(
                fetchrow=lambda *args, **kwargs: self._fetchrow(*args, **kwargs),
                log_fsm_cas_miss=lambda *args, **kwargs: self._log_fsm_cas_miss(*args, **kwargs),
                log_fsm_success=lambda *args, **kwargs: self._log_fsm_success(*args, **kwargs),
                normalize_timestamp=lambda *args, **kwargs: self._normalize_timestamp(*args, **kwargs),
                observe_task_duration=lambda *args, **kwargs: self._observe_task_duration(*args, **kwargs),
                task_from_row=lambda *args, **kwargs: self._task_from_row(*args, **kwargs),
            )
        )
        self._task_persistence_metrics = TaskPersistenceMetrics(
            TaskPersistenceMetricsPorts(
                fetch=lambda *args, **kwargs: self._fetch(*args, **kwargs),
                fetchrow=lambda *args, **kwargs: self._fetchrow(*args, **kwargs),
                normalize_timestamp=lambda *args, **kwargs: self._normalize_timestamp(*args, **kwargs),
                task_from_row=lambda *args, **kwargs: self._task_from_row(*args, **kwargs),
            )
        )

    def _normalize_timestamp(self, value: datetime) -> datetime:
        return self._task_persistence_mapping.normalize_timestamp(value=value)

    def _normalize_meta(self, value: Mapping[str, Any] | None) -> dict[str, Any]:
        return self._task_persistence_mapping.normalize_meta(value=value)

    def _normalize_json_mapping(self, value: Mapping[str, Any] | None) -> dict[str, Any] | None:
        return self._task_persistence_mapping.normalize_json_mapping(value=value)

    def _task_from_row(self, row: asyncpg.Record | None) -> AutomationTask | None:
        return self._task_persistence_mapping.task_from_row(row=row)

    _db_axis_max_attempts = staticmethod(TaskPersistenceMapping.db_axis_max_attempts)

    def _correction_values(self, correction: CorrectionState | None) -> tuple[Any, ...]:
        return self._task_persistence_mapping.correction_values(correction=correction)

    def _connection(self, conn: asyncpg.Connection | None = None) -> AsyncIterator[asyncpg.Connection]:
        return self._task_persistence_connection.connection(conn=conn)

    async def _fetchrow(
        self,
        query: str,
        *args: Any,
        conn: asyncpg.Connection | None = None,
    ) -> asyncpg.Record | None:
        return await self._task_persistence_connection.fetchrow(query, *args, conn=conn)

    async def _fetch(
        self,
        query: str,
        *args: Any,
        conn: asyncpg.Connection | None = None,
    ) -> list[asyncpg.Record]:
        return await self._task_persistence_connection.fetch(query, *args, conn=conn)

    async def _execute(
        self,
        query: str,
        *args: Any,
        conn: asyncpg.Connection | None = None,
    ) -> str:
        return await self._task_persistence_connection.execute(query, *args, conn=conn)

    def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        return self._task_persistence_connection.transaction()

    # ── Reads ───────────────────────────────────────────────────────

    async def get_by_idempotency_key(self, *, zone_id: int, idempotency_key: str) -> AutomationTask | None:
        return await self._task_persistence_queries.get_by_idempotency_key(
            zone_id=zone_id, idempotency_key=idempotency_key
        )

    async def get_active_for_zone(self, *, zone_id: int) -> AutomationTask | None:
        return await self._task_persistence_queries.get_active_for_zone(zone_id=zone_id)

    async def get_active_for_zone_with_conn(
        self,
        *,
        zone_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> AutomationTask | None:
        return await self._task_persistence_queries.get_active_for_zone_with_conn(zone_id=zone_id, conn=conn)

    async def get_last_for_zone(self, *, zone_id: int) -> AutomationTask | None:
        return await self._task_persistence_queries.get_last_for_zone(zone_id=zone_id)

    async def get_last_irrigation_for_zone(self, *, zone_id: int) -> AutomationTask | None:
        return await self._task_persistence_queries.get_last_irrigation_for_zone(zone_id=zone_id)

    async def get_by_id(self, *, task_id: int) -> AutomationTask | None:
        return await self._task_persistence_queries.get_by_id(task_id=task_id)

    async def list_for_startup_recovery(
        self,
        *,
        worker_owner: str | None = None,
        now: datetime | None = None,
    ) -> list[AutomationTask]:
        return await self._task_persistence_queries.list_for_startup_recovery(worker_owner=worker_owner, now=now)

    async def list_waiting_command_for_reconcile(self, *, limit: int = 32) -> list[AutomationTask]:
        return await self._task_persistence_queries.list_waiting_command_for_reconcile(limit=limit)

    async def list_stale_claimed_running_for_reconcile(
        self,
        *,
        now: datetime,
        stale_claimed_before: datetime,
        stale_running_before: datetime,
        stale_waiting_command_before: datetime | None = None,
        stale_unconfirmed_before: datetime | None = None,
        limit: int = 16,
    ) -> list[AutomationTask]:
        return await self._task_persistence_queries.list_stale_claimed_running_for_reconcile(
            now=now,
            stale_claimed_before=stale_claimed_before,
            stale_running_before=stale_running_before,
            stale_waiting_command_before=stale_waiting_command_before,
            stale_unconfirmed_before=stale_unconfirmed_before,
            limit=limit,
        )

    async def task_has_unconfirmed_ae_commands(self, *, task_id: int) -> bool:
        return await self._task_persistence_queries.task_has_unconfirmed_ae_commands(task_id=task_id)

    async def task_has_ae_commands(self, *, task_id: int) -> bool:
        return await self._task_persistence_queries.task_has_ae_commands(task_id=task_id)

    async def fetch_pending_with_idle_zone_workflow_rows(self) -> list[Any]:
        return await self._task_persistence_queries.fetch_pending_with_idle_zone_workflow_rows()

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
        return await self._task_persistence_creation.create_pending(
            zone_id=zone_id,
            idempotency_key=idempotency_key,
            task_type=task_type,
            topology=topology,
            current_stage=current_stage,
            workflow_phase=workflow_phase,
            intent_source=intent_source,
            intent_trigger=intent_trigger,
            intent_id=intent_id,
            intent_meta=intent_meta,
            scheduled_for=scheduled_for,
            due_at=due_at,
            now=now,
            irrigation_mode=irrigation_mode,
            irrigation_requested_duration_sec=irrigation_requested_duration_sec,
            irrigation_decision_strategy=irrigation_decision_strategy,
            irrigation_decision_config=irrigation_decision_config,
            irrigation_bundle_revision=irrigation_bundle_revision,
            conn=conn,
        )

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
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        return await self._task_persistence_creation.update_irrigation_runtime(
            task_id=task_id,
            owner=owner,
            now=now,
            irrigation_mode=irrigation_mode,
            irrigation_requested_duration_sec=irrigation_requested_duration_sec,
            irrigation_decision_strategy=irrigation_decision_strategy,
            irrigation_decision_config=irrigation_decision_config,
            irrigation_bundle_revision=irrigation_bundle_revision,
            irrigation_decision_outcome=irrigation_decision_outcome,
            irrigation_decision_reason_code=irrigation_decision_reason_code,
            irrigation_decision_degraded=irrigation_decision_degraded,
            irrigation_replay_count=irrigation_replay_count,
            irrigation_wait_ready_deadline_at=irrigation_wait_ready_deadline_at,
            irrigation_setup_deadline_at=irrigation_setup_deadline_at,
            claim_generation=claim_generation,
        )

    # ── Claim / release ─────────────────────────────────────────────

    async def claim_next_with_zone_lease(
        self,
        *,
        owner: str,
        process_run_id: str,
        now: datetime,
        lease_ttl_sec: int,
        overall_deadline_sec: int = 604800,
    ) -> tuple[AutomationTask, ZoneLease] | None:
        return await self._task_persistence_claim.claim_next_with_zone_lease(
            owner=owner,
            process_run_id=process_run_id,
            now=now,
            lease_ttl_sec=lease_ttl_sec,
            overall_deadline_sec=overall_deadline_sec,
        )

    async def claim_pending_task_with_zone_lease(
        self,
        *,
        task_id: int,
        owner: str,
        process_run_id: str,
        now: datetime,
        lease_ttl_sec: int,
        overall_deadline_sec: int = 604800,
        conn: asyncpg.Connection | None = None,
    ) -> tuple[AutomationTask, ZoneLease] | None:
        return await self._task_persistence_claim.claim_pending_task_with_zone_lease(
            task_id=task_id,
            owner=owner,
            process_run_id=process_run_id,
            now=now,
            lease_ttl_sec=lease_ttl_sec,
            overall_deadline_sec=overall_deadline_sec,
            conn=conn,
        )

    async def _claim_with_zone_lease(
        self,
        *,
        owner: str,
        process_run_id: str,
        now: datetime,
        lease_ttl_sec: int,
        overall_deadline_sec: int,
        task_id: int | None,
        conn: asyncpg.Connection | None = None,
    ) -> tuple[AutomationTask, ZoneLease] | None:
        return await self._task_persistence_claim.claim_with_zone_lease(
            owner=owner,
            process_run_id=process_run_id,
            now=now,
            lease_ttl_sec=lease_ttl_sec,
            overall_deadline_sec=overall_deadline_sec,
            task_id=task_id,
            conn=conn,
        )

    async def refresh_pending_queue_metrics(self, *, now: datetime) -> None:
        return await self._task_persistence_metrics.refresh_pending_queue_metrics(now=now)

    async def refresh_active_task_age_metrics(self, *, now: datetime) -> None:
        return await self._task_persistence_metrics.refresh_active_task_age_metrics(now=now)

    async def next_pending_due_at(self) -> datetime | None:
        return await self._task_persistence_queries.next_pending_due_at()

    async def release_claim(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
        claim_generation: int = 0,
    ) -> bool:
        return await self._task_persistence_claim.release_claim(
            task_id=task_id, owner=owner, now=now, claim_generation=claim_generation
        )

    async def requeue_unpublished_execution(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        return await self._task_persistence_claim.requeue_unpublished_execution(
            task_id=task_id, owner=owner, now=now, claim_generation=claim_generation
        )

    async def list_claimed_by_owner(self, *, owner: str) -> list[AutomationTask]:
        return await self._task_persistence_queries.list_claimed_by_owner(owner=owner)

    async def list_unpublished_execution_by_owner(self, *, owner: str) -> list[AutomationTask]:
        return await self._task_persistence_queries.list_unpublished_execution_by_owner(owner=owner)

    # ── Status transitions ──────────────────────────────────────────

    async def mark_start_event_emitted(self, *, task_id: int) -> None:
        return await self._task_persistence_stage_transitions.mark_start_event_emitted(task_id=task_id)

    async def increment_irr_probe_failure_streak(self, *, task_id: int) -> int:
        return await self._task_persistence_stage_transitions.increment_irr_probe_failure_streak(task_id=task_id)

    async def reset_irr_probe_failure_streak(self, *, task_id: int) -> None:
        return await self._task_persistence_stage_transitions.reset_irr_probe_failure_streak(task_id=task_id)

    async def mark_running(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        return await self._task_persistence_stage_transitions.mark_running(
            task_id=task_id, owner=owner, now=now, claim_generation=claim_generation
        )

    async def resume_after_waiting_command(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        return await self._task_persistence_stage_transitions.resume_after_waiting_command(
            task_id=task_id, owner=owner, now=now, claim_generation=claim_generation
        )

    async def mark_waiting_command(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        return await self._task_persistence_stage_transitions.mark_waiting_command(
            task_id=task_id, owner=owner, now=now, claim_generation=claim_generation
        )

    async def recover_waiting_command(
        self,
        *,
        task_id: int,
        now: datetime,
        owner: str,
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        return await self._task_persistence_stage_transitions.recover_waiting_command(
            task_id=task_id, now=now, owner=owner, claim_generation=claim_generation
        )

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
        preserve_pending_manual_step: bool = False,
        claim_generation: int = 0,
        conn: asyncpg.Connection | None = None,
    ) -> AutomationTask | None:
        return await self._task_persistence_stage_transitions.update_stage(
            task_id=task_id,
            owner=owner,
            workflow=workflow,
            correction=correction,
            due_at=due_at,
            now=now,
            preserve_pending_manual_step=preserve_pending_manual_step,
            claim_generation=claim_generation,
            conn=conn,
        )

    async def _sync_intent_after_task_requeue(
        self,
        *,
        task: AutomationTask,
        now: datetime,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        return await self._task_persistence_stage_transitions.sync_intent_after_task_requeue(
            task=task, now=now, conn=conn
        )

    async def set_pending_manual_step(
        self,
        *,
        task_id: int,
        manual_step: str,
        now: datetime,
    ) -> AutomationTask | None:
        return await self._task_persistence_stage_transitions.set_pending_manual_step(
            task_id=task_id, manual_step=manual_step, now=now
        )

    async def update_control_mode_snapshot_for_zone(
        self,
        *,
        zone_id: int,
        control_mode: str,
        now: datetime,
    ) -> AutomationTask | None:
        return await self._task_persistence_stage_transitions.update_control_mode_snapshot_for_zone(
            zone_id=zone_id, control_mode=control_mode, now=now
        )

    # ── Terminal transitions ────────────────────────────────────────

    async def mark_completed(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
        claim_generation: int = 0,
        conn: asyncpg.Connection | None = None,
    ) -> AutomationTask | None:
        return await self._task_persistence_terminal_transitions.mark_completed(
            task_id=task_id, owner=owner, now=now, claim_generation=claim_generation, conn=conn
        )

    async def mark_failed(
        self,
        *,
        task_id: int,
        owner: str,
        error_code: str,
        error_message: str,
        now: datetime,
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        return await self._task_persistence_terminal_transitions.mark_failed(
            task_id=task_id,
            owner=owner,
            error_code=error_code,
            error_message=error_message,
            now=now,
            claim_generation=claim_generation,
        )

    async def fail_for_recovery(
        self,
        *,
        task_id: int,
        error_code: str,
        error_message: str,
        now: datetime,
        owner: str,
        claim_generation: int,
    ) -> AutomationTask | None:
        return await self._task_persistence_terminal_transitions.fail_for_recovery(
            task_id=task_id,
            error_code=error_code,
            error_message=error_message,
            now=now,
            owner=owner,
            claim_generation=claim_generation,
        )

    async def fail_pending_or_active_for_recovery(
        self,
        *,
        task_id: int,
        error_code: str,
        error_message: str,
        now: datetime,
        claim_generation: int,
    ) -> AutomationTask | None:
        return await self._task_persistence_terminal_transitions.fail_pending_or_active_for_recovery(
            task_id=task_id,
            error_code=error_code,
            error_message=error_message,
            now=now,
            claim_generation=claim_generation,
        )

    # ── Audit trail ─────────────────────────────────────────────────

    async def get_transitions_for_task(self, *, task_id: int, limit: int = 50) -> list[dict]:
        return await self._task_persistence_queries.get_transitions_for_task(task_id=task_id, limit=limit)

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
        return await self._task_persistence_stage_transitions.record_transition(
            task_id=task_id,
            from_stage=from_stage,
            to_stage=to_stage,
            workflow_phase=workflow_phase,
            metadata=metadata,
            now=now,
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
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        return await self._task_persistence_terminal_transitions.update_task_status(
            task_id=task_id,
            owner=owner,
            next_status=next_status,
            allowed_statuses=allowed_statuses,
            now=now,
            action=action,
            claim_generation=claim_generation,
        )

    _observe_task_duration = staticmethod(TaskPersistenceMetrics.observe_task_duration)

    _log_fsm_success = staticmethod(TaskPersistenceMetrics.log_fsm_success)

    async def _log_fsm_cas_miss(
        self,
        *,
        action: str,
        task_id: int,
        to_status: str,
        owner: str,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        return await self._task_persistence_metrics.log_fsm_cas_miss(
            action=action, task_id=task_id, to_status=to_status, owner=owner, conn=conn
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
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        return await self._task_persistence_terminal_transitions.mark_failed_row(
            task_id=task_id,
            error_code=error_code,
            error_message=error_message,
            now=now,
            owner=owner,
            require_owner=require_owner,
            claim_generation=claim_generation,
        )
