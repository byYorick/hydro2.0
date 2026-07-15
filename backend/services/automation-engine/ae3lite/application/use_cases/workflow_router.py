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
    encode_manual_hold_return_stage,
)
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.application.handlers.await_ready import AwaitReadyHandler
from ae3lite.application.handlers.clean_fill import CleanFillCheckHandler
from ae3lite.application.handlers.command import CommandHandler
from ae3lite.application.handlers.correction import CorrectionHandler
from ae3lite.application.handlers.decision_gate import DecisionGateHandler
from ae3lite.application.handlers.irrigation_check import IrrigationCheckHandler
from ae3lite.application.handlers.irrigation_recovery import IrrigationRecoveryCheckHandler
from ae3lite.application.handlers.manual_hold import ManualHoldHandler
from ae3lite.application.handlers.prepare_recirc import PrepareRecircCheckHandler
from ae3lite.application.handlers.prepare_recirc_window import PrepareRecircWindowHandler
from ae3lite.application.handlers.solution_fill import SolutionFillCheckHandler
from ae3lite.application.handlers.solution_topup import (
    SolutionTopupCheckHandler,
    SolutionTopupCompleteHandler,
    SolutionTopupGuardHandler,
)
from ae3lite.application.handlers.solution_change import (
    SolutionChangeCompleteHandler,
    SolutionChangeOperatorGateHandler,
    SolutionDrainCheckHandler,
)
from ae3lite.application.handlers.startup import StartupHandler
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.config.schema import RuntimePlan
from ae3lite.domain.entities.workflow_state import CorrectionState, WorkflowState
from ae3lite.domain.services.zone_node_availability import resolve_task_error_with_node_offline
from ae3lite.domain.errors import PlannerConfigurationError, TaskExecutionError
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


logger = logging.getLogger(__name__)


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
_DEFAULT_CORRECTION_SLACK_SEC: int = 900

#: Upper bound for any operator-configured correction slack. Two hours
#: is comfortably more than any correction cycle should take yet stops
#: config mistakes from silently extending a stage indefinitely.
_MAX_CORRECTION_SLACK_SEC: int = 7200

#: Absolute cap on total stage duration (base timeout + slack). One
#: calendar day is an invariant: tasks running longer are almost
#: certainly stuck and should be bounced by the scheduler instead.
_MAX_STAGE_TOTAL_SEC: int = 86400

#: Absolute cap on a single ``due_delay_sec`` value coming out of any
#: handler outcome. Audit F7: handlers that forget a bound or read a
#: broken config could schedule a task a week in the future, which
#: looks like a dead zone from the scheduler's point of view. Clamp
#: to the stage cap — anything larger is a bug, not a feature.
_MAX_DUE_DELAY_SEC: int = _MAX_STAGE_TOTAL_SEC

#: Bounded wait for flow-path manual_hold when prior stage left no deadline.
_DEFAULT_MANUAL_HOLD_TIMEOUT_SEC: int = 86400


def _clamp_due_delay_sec(raw: Any) -> int:
    """Clamp a handler-supplied ``due_delay_sec`` to ``[0, _MAX_DUE_DELAY_SEC]``.

    Treats non-numeric or negative values as 0 (immediate retry). Never
    raises — the scheduler should keep moving even if a handler returns
    something weird, and the value is also logged by the caller so
    observability surfaces the anomaly.
    """
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    if value < 0:
        return 0
    if value > _MAX_DUE_DELAY_SEC:
        logger.warning(
            "workflow_router: due_delay_sec=%s превышает верхний предел %ss; ограничиваю",
            value,
            _MAX_DUE_DELAY_SEC,
        )
        return _MAX_DUE_DELAY_SEC
    return value


class WorkflowRouter:
    """Оркестратор topology-driven workflow: dispatch → handler → apply outcome → requeue.

    Этот класс не содержит доменную логику. Все чтения сенсоров, проверки
    уровней и расчёты коррекции живут в handler-классах.
    """

    # Соответствие handler key → handler class
    HANDLER_MAP: dict[str, type[BaseStageHandler]] = {
        "startup": StartupHandler,
        "await_ready": AwaitReadyHandler,
        "decision_gate": DecisionGateHandler,
        "command": CommandHandler,
        "clean_fill": CleanFillCheckHandler,
        "solution_fill": SolutionFillCheckHandler,
        "solution_topup_guard": SolutionTopupGuardHandler,
        "solution_topup_check": SolutionTopupCheckHandler,
        "solution_topup_complete": SolutionTopupCompleteHandler,
        "solution_change_gate": SolutionChangeOperatorGateHandler,
        "solution_drain_check": SolutionDrainCheckHandler,
        "solution_change_complete": SolutionChangeCompleteHandler,
        "irrigation_check": IrrigationCheckHandler,
        "irrigation_recovery": IrrigationRecoveryCheckHandler,
        "prepare_recirc": PrepareRecircCheckHandler,
        "prepare_recirc_window": PrepareRecircWindowHandler,
        "manual_hold": ManualHoldHandler,
        "correction": CorrectionHandler,
    }

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
        self._registry = topology_registry or TopologyRegistry()
        self._runtime_monitor = runtime_monitor
        self._command_gateway = command_gateway

        # Предсоздать handler'ы
        self._handlers: dict[str, BaseStageHandler] = {}
        for key, cls in self.HANDLER_MAP.items():
            kwargs: dict[str, Any] = {
                "runtime_monitor": runtime_monitor,
                "command_gateway": command_gateway,
                # Phase 5: включаем live-mode hot-reload checkpoint в production.
                # Tests, создающие handlers напрямую, оставляют default False.
                "live_reload_enabled": True,
            }
            if key in {"await_ready", "decision_gate", "irrigation_check", "irrigation_recovery", "prepare_recirc"}:
                kwargs["task_repository"] = task_repository
            if key == "decision_gate":
                kwargs["decision_controller"] = decision_controller
            if key == "correction":
                if correction_planner is not None:
                    kwargs["planner"] = correction_planner
                kwargs["pid_state_repository"] = pid_state_repository
            if key == "prepare_recirc":
                kwargs["pid_state_repository"] = pid_state_repository
            if key == "prepare_recirc_window":
                kwargs["alert_repository"] = alert_repository
            self._handlers[key] = cls(**kwargs)

    async def run(self, *, task: Any, plan: Any, now: datetime) -> Any:
        """Выполняет один stage workflow и возвращает обновлённую задачу.

        Вызывается из ExecuteTaskUseCase после claim и перевода задачи в running.
        """
        topology = task.topology
        current_stage = task.current_stage

        with log_context_scope(stage=current_stage):
            # Подмашина коррекции имеет приоритет
            if task.correction is not None:
                handler = self._handlers["correction"]
                stage_def = self._registry.get(topology, current_stage)
                outcome = await handler.run(
                    task=task, plan=plan, stage_def=stage_def, now=now,
                )
                return await self._apply_outcome(
                    task=task, plan=plan, outcome=outcome, now=now,
                )

            # Обычный dispatch stage
            stage_def = self._registry.get(topology, current_stage)
            handler_key = stage_def.handler

            # Терминальные ready-stage обрабатываются централизованно
            if current_stage == "complete_ready" and str(getattr(task, "task_type", "") or "") == "irrigation_start":
                if int(getattr(task, "irrigation_replay_count", 0) or 0) > 0:
                    runtime = getattr(plan, "runtime", None)
                    recovery = getattr(runtime, "irrigation_recovery", None) if runtime is not None else None
                    auto_replay = bool(getattr(recovery, "auto_replay_after_setup", True))
                    if auto_replay:
                        return await self._apply_transition(
                            task=task,
                            plan=plan,
                            outcome=StageOutcome(kind="transition", next_stage="irrigation_start"),
                            now=now,
                        )
                return await self._complete_task(task=task, now=now)
            if handler_key == "ready":
                return await self._complete_task(task=task, now=now)
            if handler_key == "solution_topup_complete":
                handler = self._handlers.get("solution_topup_complete")
                if handler is not None:
                    outcome = await handler.run(
                        task=task, plan=plan, stage_def=stage_def, now=now,
                    )
                    return await self._apply_outcome(
                        task=task, plan=plan, outcome=outcome, now=now,
                    )
            if current_stage == "complete_ready" and str(getattr(task, "task_type", "") or "").strip().lower() == "solution_change":
                handler = self._handlers.get("solution_change_complete")
                if handler is not None:
                    outcome = await handler.run(
                        task=task, plan=plan, stage_def=stage_def, now=now,
                    )
                    return await self._apply_outcome(
                        task=task, plan=plan, outcome=outcome, now=now,
                    )

            handler = self._handlers.get(handler_key)
            if handler is None:
                raise TaskExecutionError(
                    "ae3_unknown_handler",
                    f"Не найден handler для key={handler_key!r} (stage={current_stage})",
                )

            try:
                outcome = await handler.run(
                    task=task, plan=plan, stage_def=stage_def, now=now,
                )
            except TaskExecutionError as exc:
                code, message = await self._remap_execution_error_for_task(
                    task=task,
                    error_code=str(exc.code),
                    error_message=str(exc),
                    node_uid=self._extract_irrig_node_uid_from_plan(plan=plan),
                )
                remapped = TaskExecutionError(code, message)
                # Preserve attributes used by correction stage-deadline interrupt.
                deadline_kind = getattr(exc, "deadline_kind", None)
                if deadline_kind is not None:
                    remapped.deadline_kind = str(deadline_kind)
                raise remapped from exc
            return await self._apply_outcome(
                task=task, plan=plan, outcome=outcome, now=now,
            )

    # ── Outcome application ─────────────────────────────────────────

    async def _apply_outcome(
        self,
        *,
        task: Any,
        plan: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        current_task = outcome.task_override or task

        if outcome.kind == "poll":
            return await self._apply_poll(task=current_task, outcome=outcome, now=now)

        if outcome.kind == "transition":
            return await self._apply_transition(
                task=current_task, plan=plan, outcome=outcome, now=now,
            )

        if outcome.kind == "enter_correction":
            return await self._apply_enter_correction(
                task=current_task, outcome=outcome, now=now,
            )

        if outcome.kind == "exit_correction":
            return await self._apply_exit_correction(
                task=current_task, plan=plan, outcome=outcome, now=now,
            )

        if outcome.kind == "complete":
            return await self._complete_task(task=current_task, now=now)

        if outcome.kind == "fail":
            irr_uid = self._extract_irrig_node_uid_from_plan(plan=plan)
            error_code, error_message = await self._remap_execution_error_for_task(
                task=current_task,
                error_code=outcome.error_code or "ae3_stage_failed",
                error_message=outcome.error_message or "Этап завершился ошибкой",
                node_uid=irr_uid,
            )
            return await self._fail_task(
                task=current_task, now=now,
                error_code=error_code,
                error_message=error_message,
            )

        raise TaskExecutionError(
            "ae3_unknown_outcome_kind",
            f"Неизвестный StageOutcome.kind={outcome.kind!r}",
        )

    async def _resolve_stage_owner(self, *, task: Any) -> str:
        """Возвращает актуальный claimed_by для CAS update_stage.

        После command reconcile / janitor requeue in-memory task может держать
        stale owner. Без reload CAS miss превращается в ae3_*_apply_failed.
        """
        owner = str(getattr(task, "claimed_by", None) or "").strip()
        get_task_by_id = getattr(self._task_repo, "get_by_id", None)
        if not callable(get_task_by_id):
            return owner
        try:
            fresh = await get_task_by_id(task_id=int(task.id))
        except Exception:
            logger.warning(
                "AE3 не смог перечитать claimed_by перед update_stage task_id=%s",
                getattr(task, "id", None),
                exc_info=True,
            )
            return owner
        if fresh is None:
            return owner
        fresh_owner = str(getattr(fresh, "claimed_by", None) or "").strip()
        if fresh_owner and fresh_owner != owner:
            logger.info(
                "AE3 owner reload before update_stage: task_id=%s stale=%s fresh=%s",
                getattr(task, "id", None),
                owner or "<empty>",
                fresh_owner,
            )
            return fresh_owner
        return fresh_owner or owner

    async def _apply_poll(
        self, *, task: Any, outcome: StageOutcome, now: datetime,
    ) -> Any:
        """Оставляет задачу в том же stage и ставит повторный запуск с задержкой."""
        workflow = task.workflow
        due_at = now + timedelta(seconds=_clamp_due_delay_sec(outcome.due_delay_sec))
        owner = await self._resolve_stage_owner(task=task)

        updated_task = await self._task_repo.update_stage(
            task_id=task.id,
            owner=owner,
            workflow=workflow,
            correction=task.correction,
            due_at=due_at,
            now=now,
            # Operator may inject pending_manual_step via POST /manual-step while
            # this poll tick already holds a stale in-memory workflow snapshot.
            preserve_pending_manual_step=True,
        )
        resolved_task = await self._resolve_inactive_terminal_task(
            task_id=task.id,
            updated_task=updated_task,
            error_code="ae3_poll_apply_failed",
            error_message=f"Не удалось сохранить poll outcome для задачи {task.id}",
            expected_stage=str(task.current_stage or ""),
        )
        # await_ready reads zone_workflow_state to decide whether the fill cycle
        # completed and irrigation is safe (via plan.runtime.zone_workflow_phase).
        # Writing "ready" back into zone_workflow_state on each poll tick would
        # create a self-fulfilling loop: on the very next tick the handler sees
        # "ready" written by *itself* and starts irrigation even when tanks are
        # still empty — for example after a failed irrigation_check that left
        # zone_workflow_state="idle" due to a level-sensor error.  Only the fill
        # cycle tasks (prepare_recirculation_stop_to_ready etc.) are allowed to
        # set zone_workflow_state="ready"; await_ready must leave it untouched.
        if task.current_stage != "await_ready":
            await self._safe_upsert_workflow_phase(
                task=resolved_task,
                workflow_phase=workflow.workflow_phase,
                now=now,
            )
        return resolved_task

    async def _apply_transition(
        self,
        *,
        task: Any,
        plan: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        """Переходит в новый stage, очищает correction state и вычисляет дедлайн."""
        next_stage = outcome.next_stage
        if next_stage is None:
            raise TaskExecutionError(
                "ae3_transition_no_next_stage",
                "Для transition outcome требуется next_stage",
            )

        topology = task.topology
        next_def = self._registry.get(topology, next_stage)
        # Audit F8: same-stage transitions are intentional — handlers like
        # ``CorrectionHandler._interrupt_for_imminent_retry_then_probe_deadline``
        # and ``_correction_exhausted`` use them to schedule a retry of the
        # current stage without resetting ``stage_entered_at`` or the existing
        # deadline. When this branch fires we skip ``_record_stage_duration``
        # (the stage is not actually ending) and reuse the prior deadline; the
        # caller is expected to bump ``stage_retry_count`` explicitly if the
        # retry should count against an attempt budget.
        same_stage = next_stage == task.current_stage

        # Записать метрики завершённого stage
        if not same_stage:
            self._record_stage_duration(task=task, now=now)
            STAGE_ENTERED.labels(topology=topology, stage=next_stage).inc()
        if (outcome.stage_retry_count or 0) > 0:
            STAGE_RETRY.labels(topology=topology, stage=next_stage).inc()

        # Вычислить новое состояние workflow
        runtime = plan.runtime if isinstance(getattr(plan, "runtime", None), RuntimePlan) else None
        if runtime is None:
            raise TaskExecutionError(
                "runtime_plan_missing",
                "Отсутствует typed RuntimePlan в command plan",
            )
        irrigation_start_entered_at = (
            task.workflow.stage_entered_at
            if not same_stage and str(task.current_stage or "").strip().lower() == "irrigation_start"
            else None
        )
        clean_fill_cycle = (
            outcome.clean_fill_cycle
            if outcome.clean_fill_cycle is not None
            else task.workflow.clean_fill_cycle
        )
        stage_retry_count = (
            outcome.stage_retry_count
            if outcome.stage_retry_count is not None
            else (task.workflow.stage_retry_count if same_stage else 0)
        )
        stage_entered_at = task.workflow.stage_entered_at if same_stage else now

        if next_stage == MANUAL_HOLD_STAGE:
            workflow_phase = task.workflow.workflow_phase
            deadline = task.workflow.stage_deadline_at
            if deadline is None or self._deadline_reached(now=now, deadline=deadline):
                computed = self._compute_deadline(
                    task=task,
                    stage_def=next_def,
                    runtime=runtime,
                    now=now,
                    plan=plan,
                )
                deadline = computed if computed is not None else now + timedelta(
                    seconds=_DEFAULT_MANUAL_HOLD_TIMEOUT_SEC
                )
        else:
            workflow_phase = next_def.workflow_phase
            deadline = (
                task.workflow.stage_deadline_at
                if same_stage
                else self._compute_deadline(
                    task=task,
                    stage_def=next_def,
                    runtime=runtime,
                    now=now,
                    plan=plan,
                    irrigation_start_entered_at=irrigation_start_entered_at,
                )
            )

        pending_manual_step = None
        if outcome.flow_hold_return_stage:
            pending_manual_step = encode_manual_hold_return_stage(outcome.flow_hold_return_stage)
        elif next_stage == MANUAL_HOLD_STAGE:
            pending_manual_step = encode_manual_hold_return_stage(str(task.current_stage or ""))
        elif str(task.current_stage or "").strip() == MANUAL_HOLD_STAGE:
            operator_step = decode_manual_hold_operator_step(
                getattr(task.workflow, "pending_manual_step", None)
            )
            if operator_step:
                pending_manual_step = operator_step

        new_workflow = WorkflowState(
            current_stage=next_stage,
            workflow_phase=workflow_phase,
            stage_deadline_at=deadline,
            stage_retry_count=stage_retry_count,
            stage_entered_at=stage_entered_at,
            clean_fill_cycle=clean_fill_cycle,
            control_mode=task.workflow.control_mode,
            pending_manual_step=pending_manual_step,
        )

        due_at = now + timedelta(seconds=_clamp_due_delay_sec(outcome.due_delay_sec))
        owner = await self._resolve_stage_owner(task=task)
        prior_workflow = task.workflow
        prior_correction = task.correction
        prior_due_at = task.due_at
        updated_task = await self._task_repo.update_stage(
            task_id=task.id,
            owner=owner,
            workflow=new_workflow,
            correction=None,  # Очистить correction state при переходе
            due_at=due_at,
            now=now,
        )
        resolved_task = await self._resolve_inactive_terminal_task(
            task_id=task.id,
            updated_task=updated_task,
            error_code="ae3_transition_apply_failed",
            error_message=f"Не удалось перевести задачу {task.id} в stage {next_stage}",
            expected_stage=next_stage,
        )
        await self._safe_record_transition(
            task_id=task.id,
            from_stage=task.current_stage,
            to_stage=next_stage,
            workflow_phase=next_def.workflow_phase,
            now=now,
        )
        await self._safe_emit_irrigation_lifecycle_event(
            task=task,
            from_stage=task.current_stage,
            to_stage=next_stage,
        )
        await self._persist_workflow_phase_sync(
            task=resolved_task,
            owner=owner,
            rollback_workflow=prior_workflow,
            rollback_correction=prior_correction,
            rollback_due_at=prior_due_at,
            workflow_phase=next_def.workflow_phase,
            stage=next_stage,
            now=now,
        )
        return resolved_task

    async def _apply_enter_correction(
        self,
        *,
        task: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        """Входит в подмашину коррекции или продолжает её в рамках текущего stage."""
        corr = outcome.correction
        if corr is None:
            raise TaskExecutionError(
                "ae3_enter_correction_no_state",
                "Для enter_correction outcome требуется correction state",
            )

        # Записать метрики при первом входе
        if task.correction is None:
            CORRECTION_STARTED.labels(topology=task.topology).inc()

        workflow = task.workflow
        due_at = now + timedelta(seconds=_clamp_due_delay_sec(outcome.due_delay_sec))
        owner = await self._resolve_stage_owner(task=task)
        prior_workflow = task.workflow
        prior_correction = task.correction
        prior_due_at = task.due_at
        updated_task = await self._task_repo.update_stage(
            task_id=task.id,
            owner=owner,
            workflow=workflow,
            correction=corr,
            due_at=due_at,
            now=now,
        )
        resolved_task = await self._resolve_inactive_terminal_task(
            task_id=task.id,
            updated_task=updated_task,
            error_code="ae3_correction_apply_failed",
            error_message=f"Не удалось сохранить correction state для задачи {task.id}",
            expected_corr_step=str(getattr(corr, "corr_step", "") or ""),
        )
        await self._persist_workflow_phase_sync(
            task=resolved_task,
            owner=owner,
            rollback_workflow=prior_workflow,
            rollback_correction=prior_correction,
            rollback_due_at=prior_due_at,
            workflow_phase=workflow.workflow_phase,
            stage=str(task.current_stage or ""),
            now=now,
        )
        return resolved_task

    async def _apply_exit_correction(
        self,
        *,
        task: Any,
        plan: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        """Коррекция завершена: перейти в stage возврата."""
        final_corr = outcome.correction if outcome.correction is not None else task.correction
        success = (
            final_corr.outcome_success
            if final_corr and final_corr.outcome_success is not None
            else False
        )
        CORRECTION_COMPLETED.labels(
            topology=task.topology,
            outcome="success" if success else "fail",
        ).inc()

        if (
            str(outcome.next_stage or "").strip().lower() == "irrigation_check"
            and str(task.current_stage or "").strip().lower() == "irrigation_check"
        ):
            try:
                await create_zone_event(
                    int(task.zone_id),
                    "IRRIGATION_CORRECTION_COMPLETED",
                    {
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "stage": "irrigation_check",
                        "topology": str(getattr(task, "topology", "") or ""),
                        "success": bool(success),
                    },
                )
            except Exception:
                inc_observability_write_failed(kind="zone_event")
                logger.warning(
                    "AE3 не смог записать IRRIGATION_CORRECTION_COMPLETED zone_id=%s task_id=%s",
                    int(getattr(task, "zone_id", 0) or 0),
                    int(getattr(task, "id", 0) or 0),
                    exc_info=True,
                )

        # Делегировать обычному переходу
        return await self._apply_transition(
            task=task, plan=plan, outcome=outcome, now=now,
        )

    # ── Terminal states ─────────────────────────────────────────────

    async def _complete_task(self, *, task: Any, now: datetime) -> Any:
        TASK_COMPLETED.labels(topology=task.topology).inc()
        owner = await self._resolve_stage_owner(task=task)
        completed = await self._task_repo.mark_completed(
            task_id=task.id, owner=owner, now=now,
        )
        resolved_task = await self._resolve_inactive_terminal_task(
            task_id=task.id,
            updated_task=completed,
            error_code="ae3_complete_transition_failed",
            error_message=f"Не удалось перевести задачу {task.id} в completed",
        )
        await self._safe_upsert_workflow_phase(
            task=resolved_task, workflow_phase="ready", now=now,
        )
        return resolved_task

    async def _fail_task(
        self, *, task: Any, now: datetime, error_code: str, error_message: str,
    ) -> Any:
        TASK_FAILED.labels(topology=task.topology, error_code=error_code).inc()
        raise TaskExecutionError(error_code, error_message)

    async def _remap_execution_error_for_task(
        self,
        *,
        task: Any,
        error_code: str,
        error_message: str,
        node_uid: str | None = None,
    ) -> tuple[str, str]:
        offline = await resolve_task_error_with_node_offline(
            zone_id=int(getattr(task, "zone_id", 0) or 0),
            topology=str(getattr(task, "topology", "") or ""),
            error_code=error_code,
            error_message=error_message,
            node_uid=node_uid,
            runtime_monitor=self._runtime_monitor,
        )
        if offline is not None:
            return offline.code, offline.message
        return error_code, error_message

    @staticmethod
    def _extract_irrig_node_uid_from_plan(*, plan: Any) -> str | None:
        if plan is None:
            return None
        named_plans = getattr(plan, "named_plans", None) or {}
        if isinstance(named_plans, Mapping):
            probe_cmds = named_plans.get("irr_state_probe", ())
            for step in probe_cmds or ():
                uid = str(getattr(step, "node_uid", "") or "").strip()
                if uid:
                    return uid
            for commands in named_plans.values():
                for step in commands or ():
                    uid = str(getattr(step, "node_uid", "") or "").strip()
                    if uid:
                        return uid
        for step in getattr(plan, "steps", ()) or ():
            uid = str(getattr(step, "node_uid", "") or "").strip()
            if uid:
                return uid
        return None

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
        """Вычисляет `stage_deadline_at` по timeout-ключам из runtime-конфига."""
        if stage_def.name == "irrigation_check":
            irrigation_runtime = runtime.irrigation_execution
            requested_duration_sec = getattr(task, "irrigation_requested_duration_sec", None)
            if requested_duration_sec is None:
                requested_duration_sec = getattr(runtime, "irrigation_requested_duration_sec", None)
            if requested_duration_sec is None:
                requested_duration_sec = irrigation_runtime.duration_sec
            if requested_duration_sec is not None:
                try:
                    total_sec = min(
                        max(1, int(requested_duration_sec)),
                        _MAX_STAGE_TOTAL_SEC,
                    )
                except (TypeError, ValueError):
                    total_sec = None
                else:
                    if isinstance(irrigation_start_entered_at, datetime):
                        anchor = self._normalize_utc_naive(irrigation_start_entered_at)
                        deadline = anchor + timedelta(seconds=total_sec)
                    else:
                        deadline = now + timedelta(seconds=total_sec)
                    if now.tzinfo is not None:
                        return deadline.replace(tzinfo=timezone.utc)
                    return deadline

            explicit_timeout = irrigation_runtime.stage_timeout_sec
            if explicit_timeout is not None:
                try:
                    return now + timedelta(seconds=max(1, int(explicit_timeout)))
                except (TypeError, ValueError):
                    pass
            raise PlannerConfigurationError(
                "irrigation_check deadline не задан: отсутствуют "
                "irrigation_requested_duration_sec, irrigation_execution.duration_sec "
                "и irrigation_execution.stage_timeout_sec.",
                code="irrigation_check_deadline_unconfigured",
            )
        if stage_def.name == "solution_fill_check":
            base_raw = runtime.solution_fill_timeout_sec
            if base_raw is None:
                return None
            try:
                base_sec = max(1, int(base_raw))
            except (TypeError, ValueError):
                return None
            slack_raw = getattr(runtime, "solution_fill_correction_slack_sec", None)
            if slack_raw is None:
                slack = _DEFAULT_CORRECTION_SLACK_SEC
            else:
                try:
                    slack = max(0, min(_MAX_CORRECTION_SLACK_SEC, int(slack_raw)))
                except (TypeError, ValueError):
                    slack = _DEFAULT_CORRECTION_SLACK_SEC
            total_sec = min(base_sec + slack, _MAX_STAGE_TOTAL_SEC)
            return now + timedelta(seconds=total_sec)
        if stage_def.name in {"solution_topup_check", "solution_topup_start"}:
            base_raw = getattr(runtime, "solution_topup_timeout_sec", None) or runtime.solution_fill_timeout_sec
            if base_raw is None:
                return None
            try:
                base_sec = max(1, int(base_raw))
            except (TypeError, ValueError):
                return None
            return now + timedelta(seconds=min(base_sec, _MAX_STAGE_TOTAL_SEC))
        if stage_def.name in {"solution_drain_check", "solution_drain_start"}:
            base_raw = getattr(runtime, "solution_drain_timeout_sec", None) or runtime.solution_fill_timeout_sec
            if base_raw is None:
                return None
            try:
                base_sec = max(1, int(base_raw))
            except (TypeError, ValueError):
                return None
            return now + timedelta(seconds=min(base_sec, _MAX_STAGE_TOTAL_SEC))
        if stage_def.name in {"await_operator_drain_confirm", "await_operator_refill_confirm"}:
            base_raw = getattr(runtime, "solution_change_operator_confirm_timeout_sec", None)
            if base_raw is None:
                return None
            try:
                base_sec = max(60, int(base_raw))
            except (TypeError, ValueError):
                return None
            return now + timedelta(seconds=min(base_sec, _MAX_STAGE_TOTAL_SEC))
        if stage_def.name == MANUAL_HOLD_STAGE:
            return now + timedelta(seconds=min(_DEFAULT_MANUAL_HOLD_TIMEOUT_SEC, _MAX_STAGE_TOTAL_SEC))
        if stage_def.name == "prepare_recirculation_check":
            # Базовое окно берётся из retry-конфига; inline EC/pH-коррекциям нужно
            # дополнительное wall time на реальном пути HL→MQTT→node.
            base_raw = runtime.prepare_recirculation_timeout_sec
            if base_raw is None:
                return None
            try:
                base_sec = max(1, int(base_raw))
            except (TypeError, ValueError):
                return None
            slack_raw = getattr(runtime, "prepare_recirculation_correction_slack_sec", None)
            if slack_raw is None:
                slack = _DEFAULT_CORRECTION_SLACK_SEC
            else:
                try:
                    slack = max(0, min(_MAX_CORRECTION_SLACK_SEC, int(slack_raw)))
                except (TypeError, ValueError):
                    slack = _DEFAULT_CORRECTION_SLACK_SEC
            total_sec = min(base_sec + slack, _MAX_STAGE_TOTAL_SEC)
            return now + timedelta(seconds=total_sec)
        if stage_def.name == "irrigation_recovery_check":
            # Базовое окно — irrigation_recovery.timeout_sec; inline EC/pH-коррекциям
            # нужен correction slack (как у solution_fill / prepare_recirculation).
            recovery_runtime = runtime.irrigation_recovery
            timeout_sec = recovery_runtime.timeout_sec
            if timeout_sec is None and stage_def.timeout_key is not None:
                timeout_sec = getattr(runtime, stage_def.timeout_key, None)
            if timeout_sec is None:
                return None
            try:
                base_sec = max(1, int(timeout_sec))
            except (TypeError, ValueError):
                return None
            slack_raw = getattr(runtime, "irrigation_recovery_correction_slack_sec", None)
            if slack_raw is None:
                slack = _DEFAULT_CORRECTION_SLACK_SEC
            else:
                try:
                    slack = max(0, min(_MAX_CORRECTION_SLACK_SEC, int(slack_raw)))
                except (TypeError, ValueError):
                    slack = _DEFAULT_CORRECTION_SLACK_SEC
            total_sec = min(base_sec + slack, _MAX_STAGE_TOTAL_SEC)
            return now + timedelta(seconds=total_sec)
        if stage_def.timeout_key is None:
            return None
        timeout_sec = getattr(runtime, stage_def.timeout_key, None)
        if timeout_sec is None:
            # Audit F13: a missing timeout_key in runtime config is almost
            # always a config error, not a "stage has no deadline" intent.
            # Log it once so ops see the anomaly in the scheduler log rather
            # than silently getting an unbounded stage duration.
            logger.warning(
                "workflow_router: timeout_key=%r для stage=%s отсутствует в runtime; "
                "stage будет без deadline до исправления конфига",
                stage_def.timeout_key,
                stage_def.name,
            )
            return None
        return now + timedelta(seconds=int(timeout_sec))

    def _record_stage_duration(self, *, task: Any, now: datetime) -> None:
        entered = task.workflow.stage_entered_at
        if entered is not None:
            now_cmp = self._normalize_utc_naive(now)
            entered_cmp = self._normalize_utc_naive(entered)
            duration = (now_cmp - entered_cmp).total_seconds()
            STAGE_DURATION.labels(
                topology=task.topology, stage=task.current_stage,
            ).observe(max(0, duration))

    def _normalize_utc_naive(self, value: datetime) -> datetime:
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo is not None else value

    def _deadline_reached(self, *, now: datetime, deadline: datetime | None) -> bool:
        if deadline is None:
            return False
        return self._normalize_utc_naive(now) >= self._normalize_utc_naive(deadline)

    async def _upsert_workflow_phase(
        self, *, task: Any, workflow_phase: str, stage: str | None = None, now: datetime,
    ) -> None:
        """Обновляет состояние zone workflow для внешней видимости.

        Параметр ``stage`` подменяет stage, который будет записан в payload
        во время перехода, когда `task.current_stage` ещё содержит старое значение.
        """
        if self._workflow_repo is not None:
            await self._workflow_repo.upsert_phase(
                zone_id=task.zone_id,
                workflow_phase=workflow_phase,
                payload={"ae3_cycle_start_stage": stage if stage is not None else task.current_stage},
                scheduler_task_id=str(task.id),
                now=now,
            )

    async def _safe_upsert_workflow_phase(
        self, *, task: Any, workflow_phase: str, stage: str | None = None, now: datetime,
    ) -> None:
        if self._workflow_repo is None:
            return
        from ae3lite.domain.services.workflow_state_sync import upsert_workflow_phase_task_error

        payload = {
            "ae3_cycle_start_stage": stage if stage is not None else str(getattr(task, "current_stage", "") or ""),
        }
        scheduler_task_id = str(getattr(task, "id", "") or "") or None
        await upsert_workflow_phase_task_error(
            self._workflow_repo,
            zone_id=int(getattr(task, "zone_id", 0) or 0),
            workflow_phase=workflow_phase,
            payload=payload,
            scheduler_task_id=scheduler_task_id,
            now=now,
        )

    async def _persist_workflow_phase_sync(
        self,
        *,
        task: Any,
        owner: str,
        rollback_workflow: Any,
        rollback_correction: Any,
        rollback_due_at: datetime,
        workflow_phase: str,
        stage: str | None,
        now: datetime,
    ) -> None:
        """Sync zone_workflow_state; rollback ae_tasks stage if sync fail-closed."""
        try:
            await self._safe_upsert_workflow_phase(
                task=task,
                workflow_phase=workflow_phase,
                stage=stage,
                now=now,
            )
        except TaskExecutionError:
            rolled_back = await self._task_repo.update_stage(
                task_id=task.id,
                owner=owner,
                workflow=rollback_workflow,
                correction=rollback_correction,
                due_at=rollback_due_at,
                now=now,
            )
            if rolled_back is None:
                logger.error(
                    "AE3 не смог откатить ae_tasks после сбоя sync zone_workflow_state "
                    "task_id=%s zone_id=%s",
                    getattr(task, "id", None),
                    getattr(task, "zone_id", None),
                )
            raise

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
        try:
            await self._task_repo.record_transition(
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

    # Переходы, для которых создаётся zone_event (полив: старт/стоп/пропуск)
    _IRRIGATION_LIFECYCLE_EVENTS: dict[tuple[str | None, str], tuple[str, str]] = {
        ("complete_ready", "irrigation_start"): ("IRRIGATION_CYCLE_STARTED", "Полив запущен"),
        ("decision_gate", "irrigation_start"): ("IRRIGATION_CYCLE_STARTED", "Полив запущен"),
        ("irrigation_start", "irrigation_check"): ("IRRIGATION_CYCLE_STARTED", "Полив запущен"),
        ("irrigation_check", "irrigation_stop_to_ready"): ("IRRIGATION_CYCLE_FINISHED", "Полив завершён"),
        ("irrigation_check", "irrigation_stop_to_recovery"): ("IRRIGATION_CYCLE_FINISHED", "Полив завершён, запуск recovery"),
        ("irrigation_check", "irrigation_stop_to_setup"): ("IRRIGATION_CYCLE_STOPPED", "Полив остановлен: низкий уровень раствора"),
        ("decision_gate", "completed_skip"): ("IRRIGATION_CYCLE_SKIPPED", "Полив пропущен"),
    }

    async def _safe_emit_irrigation_lifecycle_event(
        self,
        *,
        task: Any,
        from_stage: str | None,
        to_stage: str,
    ) -> None:
        key = (from_stage, to_stage)
        entry = self._IRRIGATION_LIFECYCLE_EVENTS.get(key)
        if entry is None:
            return
        event_type, label = entry
        try:
            await create_zone_event(
                int(task.zone_id),
                event_type,
                {
                    "task_id": task.id,
                    "from_stage": from_stage,
                    "to_stage": to_stage,
                    "label": label,
                },
            )
        except Exception:
            inc_observability_write_failed(kind="zone_event")
            logger.warning(
                "AE3 не смог записать %s zone_id=%s task_id=%s",
                event_type,
                task.zone_id,
                task.id,
                exc_info=True,
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
        if updated_task is not None:
            return updated_task
        get_task_by_id = getattr(self._task_repo, "get_by_id", None)
        if callable(get_task_by_id):
            current_task = await get_task_by_id(task_id=task_id)
            if current_task is not None:
                if not bool(getattr(current_task, "is_active", False)):
                    return current_task
                status = str(getattr(current_task, "status", "") or "").strip().lower()
                if expected_stage is not None:
                    current_stage = str(getattr(current_task, "current_stage", "") or "").strip()
                    if current_stage == expected_stage and status == "pending":
                        logger.info(
                            "AE3 stage apply idempotent: task_id=%s already pending at stage=%s",
                            task_id,
                            expected_stage,
                        )
                        return current_task
                if expected_corr_step is not None:
                    current_corr = getattr(current_task, "correction", None)
                    current_corr_step = str(
                        getattr(current_corr, "corr_step", "") or ""
                    ).strip()
                    if current_corr_step == expected_corr_step and status == "pending":
                        logger.info(
                            "AE3 correction apply idempotent: task_id=%s already pending with corr_step=%s",
                            task_id,
                            expected_corr_step,
                        )
                        return current_task
        raise TaskExecutionError(error_code, error_message)
