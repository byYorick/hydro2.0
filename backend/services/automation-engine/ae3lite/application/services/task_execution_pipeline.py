"""ExecuteTaskUseCase pipeline: explicit collaborators and invocation context."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.services.task_execution_shared import (
    TASK_EXECUTION_LEASE_LOST_CANCEL_MSG,
    TASK_EXECUTION_OVERALL_DEADLINE_CANCEL_MSG,
    TASK_EXECUTION_TIMEOUT_CANCEL_MSG,
    logger,
)
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.domain.errors import (
    ErrorCodes,
    PlannerConfigurationError,
    SnapshotBuildError,
    TaskExecutionError,
    TaskFinalizeError,
    TaskTerminalStateReached,
)
from ae3lite.domain.task_deadline import ensure_overall_deadline_active
from ae3lite.infrastructure.metrics import TASK_RUNNING_TRANSITION_MISSED


@dataclass(frozen=True)
class TaskExecutionPipelinePorts:
    apply_terminal_task_side_effects: Callable[..., Awaitable[Any]]
    clear_failure_guards: Callable[..., Any]
    command_gateway: Callable[[], Any]
    emit_start_readiness_confirmed: Callable[..., Awaitable[Any]]
    emit_start_readiness_failed: Callable[..., Any]
    emit_task_completed_event: Callable[..., Awaitable[Any]]
    extract_irrig_node_uid: Callable[..., Any]
    fail_closed: Callable[..., Awaitable[Any]]
    finalize_task_use_case: Callable[[], Any]
    is_lease_lost_cancellation: Callable[..., Any]
    is_overall_deadline_cancellation: Callable[..., Any]
    is_timeout_cancellation: Callable[..., Any]
    load_terminal_task_or_none: Callable[..., Awaitable[Any]]
    lock_irrigation_decision_snapshot_if_needed: Callable[..., Awaitable[Any]]
    mark_correction_config_applied_if_needed: Callable[..., Awaitable[Any]]
    planner: Callable[[], Any]
    preflight_required_nodes_online: Callable[..., Awaitable[Any]]
    resolve_offline_failure_instead_of_guard: Callable[..., Awaitable[Any]]
    retry_transient_command_send_failure: Callable[..., Awaitable[Any]]
    retry_transient_snapshot_gap: Callable[..., Awaitable[Any]]
    shutdown_terminal_flow_if_needed: Callable[..., Awaitable[Any]]
    task_repository: Callable[[], Any]
    verify_topology_required_node_types: Callable[..., Any]
    workflow_router: Callable[[], Any]
    zone_snapshot_read_model: Callable[[], Any]
    complete_execution_failure: Callable[..., Awaitable[Any]]
    global_publish_upward_reports: Callable[..., Any]


class TaskExecutionPipeline:
    def __init__(self, ports: TaskExecutionPipelinePorts) -> None:
        self._ports = ports

    async def run(self, *, task: Any, now: datetime) -> Any:
        owner = str(task.claimed_by or "").strip()
        if owner == "":
            raise TaskExecutionError("ae3_task_missing_owner", f"У задачи {task.id} отсутствует claimed_by owner")

        first_run = str(getattr(task, "status", "")).strip().lower() == "claimed"
        # AE_TASK_STARTED должен эмититься ровно один раз за жизнь задачи.
        # После реквея (running→pending→claimed) статус снова "claimed",
        # поэтому используем персистентный флаг start_event_emitted.
        emit_start_event = first_run and not bool(getattr(task, "start_event_emitted", False))

        running_task = await self._ports.task_repository().mark_running(
            task_id=task.id,
            owner=owner,
            now=now,
            claim_generation=int(getattr(task, "claim_generation", 0) or 0),
        )
        if running_task is None:
            logger.warning(
                "AE3 mark_running CAS miss: fail-closed zone_id=%s task_id=%s owner=%s",
                task.zone_id,
                task.id,
                owner,
            )
            TASK_RUNNING_TRANSITION_MISSED.inc()
            return await self._ports.fail_closed(
                task=task,
                owner=owner,
                error_code="ae3_running_transition_cas_miss",
                error_message=(
                    f"mark_running CAS miss для задачи {task.id} (owner={owner}); "
                    "статус задачи изменился до перехода в running"
                ),
                now=now,
            )

        snapshot = None
        plan = None
        start_observability_emitted = False
        self._ports.clear_failure_guards(running_task)
        try:
            ensure_overall_deadline_active(task=running_task, now=now)
            await self._ports.preflight_required_nodes_online(task=running_task)
            snapshot = await self._ports.zone_snapshot_read_model().load(zone_id=running_task.zone_id)
            self._ports.verify_topology_required_node_types(task=running_task, snapshot=snapshot)
            plan = self._ports.planner().build(task=running_task, snapshot=snapshot)
            running_task = await self._ports.lock_irrigation_decision_snapshot_if_needed(
                task=running_task,
                snapshot=snapshot,
                plan=plan,
                owner=owner,
                now=now,
                emit_observability=emit_start_event,
            )
            if emit_start_event:
                await self._ports.emit_start_readiness_confirmed(
                    task=running_task,
                    snapshot=snapshot,
                    plan=plan,
                )
                try:
                    await self._ports.task_repository().mark_start_event_emitted(task_id=running_task.id)
                except Exception:
                    logger.warning(
                        "AE3 не смог выставить start_event_emitted для task_id=%s",
                        running_task.id,
                        exc_info=True,
                    )
                start_observability_emitted = True

            # Workflow-пакеты идут через WorkflowRouter. Tick и diagnostics — command batch.
            topology = running_task.topology
            pack = TopologyRegistry().try_pack(str(topology or ""))
            if pack is not None and pack.execution_mode == "workflow":
                final_task = await self._ports.workflow_router().run(task=running_task, plan=plan, now=now)
                await self._ports.mark_correction_config_applied_if_needed(
                    task=final_task,
                    snapshot=snapshot,
                    plan=plan,
                    now=now,
                )
                if final_task is not None and not bool(getattr(final_task, "is_active", False)):
                    await self._ports.apply_terminal_task_side_effects(task=final_task, now=now)
                    if str(getattr(final_task, "status", "")).strip().lower() == "completed":
                        await self._ports.emit_task_completed_event(task=final_task)
                    return final_task
                if str(getattr(final_task, "status", "")).strip().lower() == "completed":
                    await self._ports.emit_task_completed_event(task=final_task)
                return final_task

            # Fallback для не-two_tank topology: generic single-batch
            if len(plan.steps) < 1:
                raise TaskExecutionError(
                    "unsupported_command_plan_steps",
                    f"AE3-Lite требует хотя бы один command step, получено {len(plan.steps)} для task_id={running_task.id}",
                )
            result = await self._ports.command_gateway().run_batch(task=running_task, commands=plan.steps, now=now)
            if not result["success"]:
                raise TaskExecutionError(str(result["error_code"]), str(result["error_message"]))
            completed_task = await self._ports.finalize_task_use_case().complete(
                task=result["task"],
                owner=owner,
                now=now,
            )
            return completed_task
        except TaskTerminalStateReached as exc:
            terminal_task = await self._ports.load_terminal_task_or_none(
                task_id=int(getattr(exc.task, "id", 0) or getattr(running_task, "id", 0) or 0),
                fallback_task=exc.task,
            )
            if terminal_task is not None:
                await self._ports.shutdown_terminal_flow_if_needed(
                    terminal_task=terminal_task,
                    snapshot=snapshot,
                    plan=plan,
                    now=now,
                )
                await self._ports.apply_terminal_task_side_effects(task=terminal_task, now=now)
                logger.info(
                    "AE3 execution задачи остановлено после внешнего terminal transition: zone_id=%s task_id=%s status=%s",
                    getattr(terminal_task, "zone_id", None),
                    getattr(terminal_task, "id", None),
                    getattr(terminal_task, "status", None),
                )
                return terminal_task
            raise
        except asyncio.CancelledError as exc:
            timeout_cancelled = self._ports.is_timeout_cancellation(exc)
            lease_lost_cancelled = self._ports.is_lease_lost_cancellation(exc)
            overall_deadline_cancelled = self._ports.is_overall_deadline_cancellation(exc)
            if not timeout_cancelled and not lease_lost_cancelled and not overall_deadline_cancelled:
                raise

            timeout_now = datetime.now(timezone.utc)
            if overall_deadline_cancelled:
                error_code = TASK_EXECUTION_OVERALL_DEADLINE_CANCEL_MSG
                error_message = "Общий deadline задачи истёк во время выполнения"
            elif timeout_cancelled:
                error_code = TASK_EXECUTION_TIMEOUT_CANCEL_MSG
                error_message = "Выполнение задачи превысило runtime timeout"
            else:
                error_code = TASK_EXECUTION_LEASE_LOST_CANCEL_MSG
                error_message = "Во время выполнения задачи был потерян zone lease"
            guard_extra_details: dict[str, object] | None = None
            offline_failure = await self._ports.resolve_offline_failure_instead_of_guard(
                task=running_task,
                original_error_code=error_code,
                original_error_message=error_message,
            )
            if offline_failure is not None:
                error_code = offline_failure.code
                error_message = offline_failure.message
                guard_extra_details = offline_failure.details
            logger.error(
                "AE3 execution задачи отменено runtime guard: zone_id=%s task_id=%s stage=%s error_code=%s",
                running_task.zone_id,
                running_task.id,
                getattr(running_task, "current_stage", None),
                error_code,
            )
            return await self._ports.complete_execution_failure(
                task=running_task,
                snapshot=snapshot,
                plan=plan,
                now=timeout_now,
                owner=owner,
                error_code=error_code,
                error_message=error_message,
                extra_details=guard_extra_details,
            )
        except SnapshotBuildError as exc:
            snapshot_error_code = str(
                getattr(exc, "code", ErrorCodes.AE3_SNAPSHOT_BUILD_FAILED) or ErrorCodes.AE3_SNAPSHOT_BUILD_FAILED
            )
            snapshot_details = exc.details if isinstance(getattr(exc, "details", None), Mapping) else {}
            if first_run and not start_observability_emitted:
                self._ports.emit_start_readiness_failed(
                    task=running_task,
                    snapshot=snapshot,
                    error_code=snapshot_error_code,
                    error=exc,
                )
            terminal_task = await self._ports.load_terminal_task_or_none(
                task_id=int(getattr(running_task, "id", 0) or 0),
                fallback_task=running_task,
            )
            if terminal_task is not None:
                await self._ports.shutdown_terminal_flow_if_needed(
                    terminal_task=terminal_task,
                    snapshot=snapshot,
                    plan=plan,
                    now=now,
                )
                logger.info(
                    "AE3 execution задачи остановлено после внешнего terminal transition: zone_id=%s task_id=%s status=%s reason=%s",
                    getattr(terminal_task, "zone_id", None),
                    getattr(terminal_task, "id", None),
                    getattr(terminal_task, "status", None),
                    type(exc).__name__,
                )
                return terminal_task

            persistent_uids = list(snapshot_details.get("persistently_offline_uids") or [])
            if snapshot_error_code == ErrorCodes.AE3_SNAPSHOT_NO_ONLINE_ACTUATOR_CHANNELS and persistent_uids:
                logger.error(
                    "AE3 snapshot persistent dead nodes (no retry): zone_id=%s task_id=%s persistently_offline_uids=%s",
                    running_task.zone_id,
                    running_task.id,
                    persistent_uids,
                )
                return await self._ports.complete_execution_failure(
                    task=running_task,
                    snapshot=snapshot,
                    plan=plan,
                    now=now,
                    owner=owner,
                    error_code=ErrorCodes.AE3_SNAPSHOT_REQUIRED_NODE_PERSISTENTLY_OFFLINE,
                    error_message=str(exc),
                    extra_details=dict(snapshot_details),
                )

            retried_task = await self._ports.retry_transient_snapshot_gap(
                task=running_task,
                owner=owner,
                error=exc,
                now=now,
            )
            if retried_task is not None:
                return retried_task

            logger.error(
                "AE3 domain error при выполнении задачи: zone_id=%s task_id=%s stage=%s error_type=%s error_code=%s error=%s",
                running_task.zone_id,
                running_task.id,
                getattr(running_task, "current_stage", None),
                type(exc).__name__,
                snapshot_error_code,
                exc,
            )
            return await self._ports.complete_execution_failure(
                task=running_task,
                snapshot=snapshot,
                plan=plan,
                now=now,
                owner=owner,
                error_code=snapshot_error_code,
                error_message=str(exc),
                extra_details=dict(snapshot_details) if snapshot_details else None,
            )
        except (PlannerConfigurationError, TaskExecutionError, TaskFinalizeError) as exc:
            reports = tuple(getattr(exc, "upward_reports", ()) or ())
            if first_run and not start_observability_emitted and isinstance(exc, PlannerConfigurationError):
                self._ports.emit_start_readiness_failed(
                    task=running_task,
                    snapshot=snapshot,
                    error_code=str(getattr(exc, "code", "ae3_task_execution_failed") or "ae3_task_execution_failed"),
                    error=exc,
                )
            terminal_task = await self._ports.load_terminal_task_or_none(
                task_id=int(getattr(running_task, "id", 0) or 0),
                fallback_task=running_task,
            )
            if terminal_task is not None:
                await self._ports.shutdown_terminal_flow_if_needed(
                    terminal_task=terminal_task,
                    snapshot=snapshot,
                    plan=plan,
                    now=now,
                )
                await self._ports.global_publish_upward_reports(reports)
                logger.info(
                    "AE3 execution задачи остановлено после внешнего terminal transition: zone_id=%s task_id=%s status=%s reason=%s",
                    getattr(terminal_task, "zone_id", None),
                    getattr(terminal_task, "id", None),
                    getattr(terminal_task, "status", None),
                    getattr(exc, "code", type(exc).__name__),
                )
                return terminal_task
            error_code = getattr(exc, "code", "ae3_task_execution_failed")
            error_message = str(exc)
            execution_extra_details: dict[str, object] | None = None
            if str(error_code or "").strip().lower() == "command_send_failed":
                retried_task = await self._ports.retry_transient_command_send_failure(
                    task=running_task,
                    owner=owner,
                    error=exc,
                    now=now,
                    snapshot=snapshot,
                    plan=plan,
                )
                if retried_task is not None:
                    return retried_task
            offline_failure = await self._ports.resolve_offline_failure_instead_of_guard(
                task=running_task,
                original_error_code=str(error_code or ""),
                original_error_message=error_message,
                node_uid=self._ports.extract_irrig_node_uid(snapshot),
            )
            if offline_failure is not None:
                error_code = offline_failure.code
                error_message = offline_failure.message
                execution_extra_details = offline_failure.details
            logger.error(
                "AE3 domain error при выполнении задачи: zone_id=%s task_id=%s stage=%s error_type=%s error_code=%s error=%s",
                running_task.zone_id,
                running_task.id,
                getattr(running_task, "current_stage", None),
                type(exc).__name__,
                error_code,
                exc,
            )
            return await self._ports.complete_execution_failure(
                task=running_task,
                snapshot=snapshot,
                plan=plan,
                now=now,
                owner=owner,
                error_code=error_code,
                error_message=error_message,
                extra_details=execution_extra_details,
                upward_reports=reports,
            )
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            logger.error(
                "Необработанное исключение при выполнении задачи AE3: zone_id=%s task_id=%s stage=%s error_type=%s error=%s",
                running_task.zone_id,
                running_task.id,
                getattr(running_task, "current_stage", None),
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return await self._ports.complete_execution_failure(
                task=running_task,
                snapshot=snapshot,
                plan=plan,
                now=now,
                owner=owner,
                error_code="ae3_task_execution_unhandled_exception",
                error_message=message,
            )
