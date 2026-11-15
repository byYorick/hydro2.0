"""WorkflowRouter: чистый оркестратор topology-driven workflow в AE3-Lite v2.

Маршрутизирует выполнение по ``StageDef.handler``, интерпретирует возвращённый
``StageOutcome``, обновляет состояние задачи через repository, записывает
переходы в audit trail и обновляет workflow phase зоны.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.flow_path_guard import (
    MANUAL_HOLD_STAGE,
    decode_manual_hold_operator_step,
    decode_manual_hold_return_stage,
    encode_manual_hold_return_stage,
)
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.hydraulics.dispatch import assert_stage_dispatch
from ae3lite.hydraulics.failure_report import (
    close_upward_capture,
    drain_upward_reports,
    open_upward_capture,
    publish_upward_reports,
)
from ae3lite.hydraulics.registry import handler_dependency_map, hydraulic_handler_classes
from ae3lite.config.schema import RuntimePlan
from ae3lite.domain.entities.workflow_state import CorrectionState, WorkflowState
from ae3lite.domain.services.zone_node_availability import resolve_task_error_with_node_offline
from ae3lite.domain.claim_fence import claim_generation, claim_owner, same_claim_token
from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError, TaskExecutionError
from ae3lite.infrastructure.log_context import log_context_scope
from ae3lite.infrastructure.metrics import (
    COMMAND_TERMINAL,
    CORRECTION_COMPLETED,
    CORRECTION_STARTED,
    STAGE_DURATION,
    STAGE_ENTERED,
    STAGE_RETRY,
    TASK_COMPLETED,
    TASK_FAILED,
    TICK_DURATION,
    inc_observability_write_failed,
)
from common.db import create_zone_event


# ── Stage deadline slack constants (extracted per audit F1) ──────────
#
# These were previously hardcoded inline 4 times across _compute_deadline
# (irrigation_check, solution_fill_check, prepare_recirculation_check) and
# changing them required editing several sites in lockstep. Centralised
# here so deadline semantics can be reasoned about as one table.

#: Default slack added to base stage deadline when inline correction is
#: enabled but no explicit ``*_correction_slack_sec`` value is supplied.
#: 15 minutes (900s) leaves room for an observation window retry and a
#: follow-up probe before the stage is force-terminated.


#: Upper bound for any operator-configured correction slack. Two hours
#: is comfortably more than any correction cycle should take yet stops
#: config mistakes from silently extending a stage indefinitely.


#: Absolute cap on total stage duration (base timeout + slack). One
#: calendar day is an invariant: tasks running longer are almost
#: certainly stuck and should be bounced by the scheduler instead.


#: Absolute cap on a single ``due_delay_sec`` value coming out of any
#: handler outcome. Audit F7: handlers that forget a bound or read a
#: broken config could schedule a task a week in the future, which
#: looks like a dead zone from the scheduler's point of view. Clamp
#: to the stage cap — anything larger is a bug, not a feature.


#: Bounded wait for flow-path manual_hold when prior stage left no deadline.


from ae3lite.application.services.task_workflow_transition import TaskWorkflowTransition


from ae3lite.application.services.workflow_routing_shared import (
    logger,
    _StageUpdateNotApplied,
    _DEFAULT_CORRECTION_SLACK_SEC,
    _MAX_CORRECTION_SLACK_SEC,
    _MAX_STAGE_TOTAL_SEC,
    _MAX_DUE_DELAY_SEC,
    _DEFAULT_MANUAL_HOLD_TIMEOUT_SEC,
    _clamp_due_delay_sec,
)

from ae3lite.application.services.workflow_routing_coordination import (
    WorkflowRoutingCoordination,
    WorkflowRoutingCoordinationPorts,
)
from ae3lite.application.services.workflow_routing_claim_guard import (
    WorkflowRoutingClaimGuard,
    WorkflowRoutingClaimGuardPorts,
)
from ae3lite.application.services.workflow_routing_stage_outcomes import (
    WorkflowRoutingStageOutcomes,
    WorkflowRoutingStageOutcomesPorts,
)
from ae3lite.application.services.workflow_routing_handler_boundary import (
    WorkflowRoutingHandlerBoundary,
    WorkflowRoutingHandlerBoundaryPorts,
)
from ae3lite.application.services.workflow_routing_deadlines import (
    WorkflowRoutingDeadlines,
    WorkflowRoutingDeadlinesPorts,
)
from ae3lite.application.services.workflow_routing_persistence import (
    WorkflowRoutingPersistence,
    WorkflowRoutingPersistencePorts,
)
from ae3lite.application.services.workflow_routing_observability import (
    WorkflowRoutingObservability,
    WorkflowRoutingObservabilityPorts,
)


class WorkflowRouter:
    """Оркестратор topology-driven workflow: dispatch → handler → apply outcome → requeue.

    Этот класс не содержит доменную логику. Все чтения сенсоров, проверки
    уровней и расчёты коррекции живут в handler-классах.
    """

    # Ключи собраны из трёх модулей гидравлики плюс общий command/manual_hold.
    HANDLER_MAP: dict[str, type[BaseStageHandler]] = hydraulic_handler_classes()

    def __init__(
        self,
        *,
        task_repository: Any,
        workflow_repository: Any,
        topology_registry: Optional[TopologyRegistry] = None,
        runtime_monitor: Any,
        command_gateway: Any,
        correction_planner: Any = None,
        alert_repository: Any = None,
        pid_state_repository: Any = None,
        decision_controller: Any = None,
    ) -> None:
        self._task_repo = task_repository
        self._workflow_repo = workflow_repository
        self._transitions = TaskWorkflowTransition(
            task_repository=task_repository, workflow_repository=workflow_repository
        )
        self._registry = topology_registry or TopologyRegistry()
        self._runtime_monitor = runtime_monitor
        self._command_gateway = command_gateway

        # Зависимости объявляет модуль подсистемы (handler_deps), не роутер.
        dependency_pool: dict[str, Any] = {
            "task_repository": task_repository,
            "decision_controller": decision_controller,
            "planner": correction_planner,
            "pid_state_repository": pid_state_repository,
            "alert_repository": alert_repository,
        }
        declared_deps = handler_dependency_map()
        self._handlers: dict[str, BaseStageHandler] = {}
        for key, cls in self.HANDLER_MAP.items():
            kwargs: dict[str, Any] = {
                "runtime_monitor": runtime_monitor,
                "command_gateway": command_gateway,
                # Phase 5: включаем live-mode hot-reload checkpoint в production.
                # Tests, создающие handlers напрямую, оставляют default False.
                "live_reload_enabled": True,
            }
            for dep_name in declared_deps.get(key, ()):
                if dep_name == "planner" and dependency_pool["planner"] is None:
                    continue
                kwargs[dep_name] = dependency_pool[dep_name]
            self._handlers[key] = cls(**kwargs)
        self._workflow_routing_coordination = WorkflowRoutingCoordination(
            WorkflowRoutingCoordinationPorts(
                apply_enter_correction=lambda *args, **kwargs: self._apply_enter_correction(*args, **kwargs),
                apply_exit_correction=lambda *args, **kwargs: self._apply_exit_correction(*args, **kwargs),
                apply_poll=lambda *args, **kwargs: self._apply_poll(*args, **kwargs),
                apply_transition=lambda *args, **kwargs: self._apply_transition(*args, **kwargs),
                complete_task=lambda *args, **kwargs: self._complete_task(*args, **kwargs),
                extract_irrig_node_uid_from_plan=lambda *args, **kwargs: self._extract_irrig_node_uid_from_plan(
                    *args, **kwargs
                ),
                fail_task=lambda *args, **kwargs: self._fail_task(*args, **kwargs),
                handlers=lambda: self._handlers,
                invoke_handler=lambda *args, **kwargs: self._invoke_handler(*args, **kwargs),
                registry=lambda: self._registry,
                remap_execution_error_for_task=lambda *args, **kwargs: self._remap_execution_error_for_task(
                    *args, **kwargs
                ),
            )
        )
        self._workflow_routing_claim_guard = WorkflowRoutingClaimGuard(
            WorkflowRoutingClaimGuardPorts(
                task_repo=lambda: self._task_repo,
            )
        )
        self._workflow_routing_stage_outcomes = WorkflowRoutingStageOutcomes(
            WorkflowRoutingStageOutcomesPorts(
                correction_completed_metric=lambda: CORRECTION_COMPLETED,
                complete_task_and_workflow_phase_atomic=lambda *args, **kwargs: (
                    self._complete_task_and_workflow_phase_atomic(*args, **kwargs)
                ),
                compute_deadline=lambda *args, **kwargs: self._compute_deadline(*args, **kwargs),
                deadline_reached=lambda *args, **kwargs: self._deadline_reached(*args, **kwargs),
                record_stage_duration=lambda *args, **kwargs: self._record_stage_duration(*args, **kwargs),
                registry=lambda: self._registry,
                require_original_claim=lambda *args, **kwargs: self._require_original_claim(*args, **kwargs),
                resolve_inactive_terminal_task=lambda *args, **kwargs: self._resolve_inactive_terminal_task(
                    *args, **kwargs
                ),
                safe_emit_irrigation_lifecycle_event=lambda *args, **kwargs: self._safe_emit_irrigation_lifecycle_event(
                    *args, **kwargs
                ),
                safe_record_transition=lambda *args, **kwargs: self._safe_record_transition(*args, **kwargs),
                task_repo=lambda: self._task_repo,
                update_stage_and_workflow_phase_atomic=lambda *args, **kwargs: (
                    self._update_stage_and_workflow_phase_atomic(*args, **kwargs)
                ),
                global_create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
            )
        )
        self._workflow_routing_handler_boundary = WorkflowRoutingHandlerBoundary(
            WorkflowRoutingHandlerBoundaryPorts(
                runtime_monitor=lambda: self._runtime_monitor,
            )
        )
        self._workflow_routing_deadlines = WorkflowRoutingDeadlines(WorkflowRoutingDeadlinesPorts())
        self._workflow_routing_persistence = WorkflowRoutingPersistence(
            WorkflowRoutingPersistencePorts(
                resolve_inactive_terminal_task=lambda *args, **kwargs: self._resolve_inactive_terminal_task(
                    *args, **kwargs
                ),
                task_repo=lambda: self._task_repo,
                transitions=lambda: self._transitions,
                workflow_repo=lambda: self._workflow_repo,
            )
        )
        self._workflow_routing_observability = WorkflowRoutingObservability(
            WorkflowRoutingObservabilityPorts(
                irrigation_lifecycle_events=lambda: self._IRRIGATION_LIFECYCLE_EVENTS,
                normalize_utc_naive=lambda *args, **kwargs: self._normalize_utc_naive(*args, **kwargs),
                global_create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
            )
        )

    async def run(self, *, task: Any, plan: Any, now: datetime) -> Any:
        return await self._workflow_routing_coordination.run(task=task, plan=plan, now=now)

    # ── Outcome application ─────────────────────────────────────────

    async def _apply_outcome(
        self,
        *,
        task: Any,
        plan: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        return await self._workflow_routing_coordination.apply_outcome(task=task, plan=plan, outcome=outcome, now=now)

    async def _require_original_claim(self, *, task: Any) -> tuple[str, int]:
        return await self._workflow_routing_claim_guard.require_original_claim(task=task)

    async def _apply_poll(
        self,
        *,
        task: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        return await self._workflow_routing_stage_outcomes.apply_poll(task=task, outcome=outcome, now=now)

    async def _apply_transition(
        self,
        *,
        task: Any,
        plan: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        return await self._workflow_routing_stage_outcomes.apply_transition(
            task=task, plan=plan, outcome=outcome, now=now
        )

    async def _apply_enter_correction(
        self,
        *,
        task: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        return await self._workflow_routing_stage_outcomes.apply_enter_correction(task=task, outcome=outcome, now=now)

    async def _apply_exit_correction(
        self,
        *,
        task: Any,
        plan: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        return await self._workflow_routing_stage_outcomes.apply_exit_correction(
            task=task, plan=plan, outcome=outcome, now=now
        )

    # ── Terminal states ─────────────────────────────────────────────

    async def _complete_task(self, *, task: Any, now: datetime) -> Any:
        return await self._workflow_routing_stage_outcomes.complete_task(task=task, now=now)

    async def _invoke_handler(
        self,
        *,
        handler: BaseStageHandler,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> Any:
        return await self._workflow_routing_handler_boundary.invoke_handler(
            handler=handler, task=task, plan=plan, stage_def=stage_def, now=now
        )

    async def _fail_task(
        self,
        *,
        task: Any,
        now: datetime,
        error_code: str,
        error_message: str,
        upward_reports: tuple[Any, ...] = (),
    ) -> Any:
        return await self._workflow_routing_handler_boundary.fail_task(
            task=task, now=now, error_code=error_code, error_message=error_message, upward_reports=upward_reports
        )

    async def _remap_execution_error_for_task(
        self,
        *,
        task: Any,
        error_code: str,
        error_message: str,
        node_uid: str | None = None,
    ) -> tuple[str, str]:
        return await self._workflow_routing_handler_boundary.remap_execution_error_for_task(
            task=task, error_code=error_code, error_message=error_message, node_uid=node_uid
        )

    _extract_irrig_node_uid_from_plan = staticmethod(WorkflowRoutingHandlerBoundary.extract_irrig_node_uid_from_plan)

    # ── Helpers ─────────────────────────────────────────────────────

    def _compute_deadline(
        self,
        *,
        task: Any,
        stage_def: Any,
        runtime: RuntimePlan,
        now: datetime,
        plan: Any = None,
        irrigation_start_entered_at: datetime | None = None,
    ) -> Optional[datetime]:
        return self._workflow_routing_deadlines.compute_deadline(
            task=task,
            stage_def=stage_def,
            runtime=runtime,
            now=now,
            plan=plan,
            irrigation_start_entered_at=irrigation_start_entered_at,
        )

    def _record_stage_duration(self, *, task: Any, now: datetime) -> None:
        return self._workflow_routing_observability.record_stage_duration(task=task, now=now)

    def _normalize_utc_naive(self, value: datetime) -> datetime:
        return self._workflow_routing_deadlines.normalize_utc_naive(value=value)

    def _deadline_reached(self, *, now: datetime, deadline: datetime | None) -> bool:
        return self._workflow_routing_deadlines.deadline_reached(now=now, deadline=deadline)

    async def _update_stage_and_workflow_phase_atomic(
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
        return await self._workflow_routing_persistence.update_stage_and_workflow_phase_atomic(
            task=task,
            owner=owner,
            claim_generation=claim_generation,
            workflow=workflow,
            correction=correction,
            due_at=due_at,
            workflow_phase=workflow_phase,
            now=now,
            stage=stage,
            preserve_pending_manual_step=preserve_pending_manual_step,
            error_code=error_code,
            error_message=error_message,
            expected_stage=expected_stage,
            expected_corr_step=expected_corr_step,
        )

    async def _complete_task_and_workflow_phase_atomic(
        self,
        *,
        task: Any,
        owner: str,
        claim_generation: int,
        now: datetime,
    ) -> tuple[Any, bool]:
        return await self._workflow_routing_persistence.complete_task_and_workflow_phase_atomic(
            task=task, owner=owner, claim_generation=claim_generation, now=now
        )

    async def _upsert_workflow_phase(
        self,
        *,
        task: Any,
        workflow_phase: str,
        stage: str | None = None,
        now: datetime,
    ) -> None:
        return await self._workflow_routing_persistence.upsert_workflow_phase(
            task=task, workflow_phase=workflow_phase, stage=stage, now=now
        )

    async def _safe_upsert_workflow_phase(
        self,
        *,
        task: Any,
        workflow_phase: str,
        stage: str | None = None,
        now: datetime,
    ) -> None:
        return await self._workflow_routing_persistence.safe_upsert_workflow_phase(
            task=task, workflow_phase=workflow_phase, stage=stage, now=now
        )

    async def _safe_record_transition(
        self,
        *,
        task_id: int,
        from_stage: str | None,
        to_stage: str,
        workflow_phase: str | None,
        now: datetime,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        return await self._workflow_routing_persistence.safe_record_transition(
            task_id=task_id,
            from_stage=from_stage,
            to_stage=to_stage,
            workflow_phase=workflow_phase,
            now=now,
            metadata=metadata,
        )

    # Переходы, для которых создаётся zone_event (полив: старт/стоп/пропуск)
    _IRRIGATION_LIFECYCLE_EVENTS: dict[tuple[str | None, str], tuple[str, str]] = {
        ("complete_ready", "irrigation_start"): ("IRRIGATION_CYCLE_STARTED", "Полив запущен"),
        ("decision_gate", "irrigation_start"): ("IRRIGATION_CYCLE_STARTED", "Полив запущен"),
        ("irrigation_start", "irrigation_check"): ("IRRIGATION_CYCLE_STARTED", "Полив запущен"),
        ("irrigation_check", "irrigation_stop_to_ready"): ("IRRIGATION_CYCLE_FINISHED", "Полив завершён"),
        ("irrigation_check", "irrigation_stop_to_setup"): (
            "IRRIGATION_CYCLE_STOPPED",
            "Полив остановлен: низкий уровень раствора",
        ),
        ("decision_gate", "completed_skip"): ("IRRIGATION_CYCLE_SKIPPED", "Полив пропущен"),
    }

    async def _safe_emit_irrigation_lifecycle_event(
        self,
        *,
        task: Any,
        from_stage: str | None,
        to_stage: str,
    ) -> None:
        return await self._workflow_routing_observability.safe_emit_irrigation_lifecycle_event(
            task=task, from_stage=from_stage, to_stage=to_stage
        )

    async def _resolve_inactive_terminal_task(
        self,
        *,
        task_id: int,
        updated_task: Any,
        error_code: str,
        error_message: str,
        expected_stage: str | None = None,
        expected_corr_step: str | None = None,
    ) -> Any:
        return await self._workflow_routing_claim_guard.resolve_inactive_terminal_task(
            task_id=task_id,
            updated_task=updated_task,
            error_code=error_code,
            error_message=error_message,
            expected_stage=expected_stage,
            expected_corr_step=expected_corr_step,
        )
