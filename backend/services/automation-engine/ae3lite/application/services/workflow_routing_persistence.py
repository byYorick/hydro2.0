"""WorkflowRouter persistence: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.services.workflow_routing_shared import _StageUpdateNotApplied, logger
from ae3lite.domain.entities.workflow_state import CorrectionState, WorkflowState
from ae3lite.infrastructure.metrics import (
    inc_observability_write_failed,
)


@dataclass(frozen=True)
class WorkflowRoutingPersistencePorts:
    resolve_inactive_terminal_task: Callable[..., Awaitable[Any]]
    task_repo: Callable[[], Any]
    transitions: Callable[[], Any]
    workflow_repo: Callable[[], Any]


class WorkflowRoutingPersistence:
    def __init__(self, ports: WorkflowRoutingPersistencePorts) -> None:
        self._ports = ports

    async def update_stage_and_workflow_phase_atomic(
        self,
        *,
        task: Any,
        owner: str,
        claim_generation: int,
        workflow: WorkflowState,
        correction: CorrectionState | None,
        due_at: datetime,
        workflow_phase: str,
        now: datetime,
        stage: str | None = None,
        preserve_pending_manual_step: bool = False,
        error_code: str,
        error_message: str,
        expected_stage: str | None = None,
        expected_corr_step: str | None = None,
    ) -> tuple[Any, bool]:
        """Persist ae_tasks and zone_workflow_state in one PostgreSQL transaction."""
        try:
            updated_task = await self._ports.transitions().requeue(
                task=task,
                owner=owner,
                claim_generation=claim_generation,
                workflow=workflow,
                correction=correction,
                due_at=due_at,
                now=now,
                workflow_phase=workflow_phase,
                stage=stage,
                preserve_pending_manual_step=preserve_pending_manual_step,
            )
            if updated_task is None:
                raise _StageUpdateNotApplied()
            return updated_task, True
        except _StageUpdateNotApplied:
            resolved_task = await self._ports.resolve_inactive_terminal_task(
                task_id=task.id,
                updated_task=None,
                error_code=error_code,
                error_message=error_message,
                expected_stage=expected_stage,
                expected_corr_step=expected_corr_step,
            )
            return resolved_task, False

    async def complete_task_and_workflow_phase_atomic(
        self,
        *,
        task: Any,
        owner: str,
        claim_generation: int,
        now: datetime,
    ) -> tuple[Any, bool]:
        try:
            completed = await self._ports.transitions().complete(
                task=task,
                owner=owner,
                claim_generation=claim_generation,
                now=now,
            )
            if completed is None:
                raise _StageUpdateNotApplied()
            return completed, True
        except _StageUpdateNotApplied:
            resolved_task = await self._ports.resolve_inactive_terminal_task(
                task_id=task.id,
                updated_task=None,
                error_code="ae3_complete_transition_failed",
                error_message=f"Не удалось перевести задачу {task.id} в completed",
            )
            return resolved_task, False

    async def upsert_workflow_phase(
        self,
        *,
        task: Any,
        workflow_phase: str,
        stage: str | None = None,
        now: datetime,
    ) -> None:
        """Обновляет состояние zone workflow для внешней видимости.

        Параметр ``stage`` подменяет stage, который будет записан в payload
        во время перехода, когда `task.current_stage` ещё содержит старое значение.
        """
        if self._ports.workflow_repo() is not None:
            await self._ports.workflow_repo().upsert_phase(
                zone_id=task.zone_id,
                workflow_phase=workflow_phase,
                payload={"ae3_cycle_start_stage": stage if stage is not None else task.current_stage},
                scheduler_task_id=str(task.id),
                now=now,
            )

    async def safe_upsert_workflow_phase(
        self,
        *,
        task: Any,
        workflow_phase: str,
        stage: str | None = None,
        now: datetime,
    ) -> None:
        if self._ports.workflow_repo() is None:
            return
        from ae3lite.domain.services.workflow_state_sync import upsert_workflow_phase_task_error

        payload = {
            "ae3_cycle_start_stage": stage if stage is not None else str(getattr(task, "current_stage", "") or ""),
        }
        scheduler_task_id = str(getattr(task, "id", "") or "") or None
        await upsert_workflow_phase_task_error(
            self._ports.workflow_repo(),
            zone_id=int(getattr(task, "zone_id", 0) or 0),
            workflow_phase=workflow_phase,
            payload=payload,
            scheduler_task_id=scheduler_task_id,
            now=now,
        )

    async def safe_record_transition(
        self,
        *,
        task_id: int,
        from_stage: str | None,
        to_stage: str,
        workflow_phase: str | None,
        now: datetime,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        try:
            await self._ports.task_repo().record_transition(
                task_id=task_id,
                from_stage=from_stage,
                to_stage=to_stage,
                workflow_phase=workflow_phase,
                metadata=metadata,
                now=now,
            )
        except Exception:
            inc_observability_write_failed(kind="zone_event")
            logger.warning(
                "AE3 не смог записать переход stage task_id=%s from=%s to=%s",
                task_id,
                from_stage,
                to_stage,
                exc_info=True,
            )
