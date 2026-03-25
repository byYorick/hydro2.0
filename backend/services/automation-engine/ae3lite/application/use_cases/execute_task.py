"""Execute one claimed AE3-Lite task to next safe state (v2)."""

from __future__ import annotations

import asyncio
import logging
from datetime import timezone
from datetime import datetime
from typing import Any

from ae3lite.application.use_cases.finalize_task import FinalizeTaskUseCase
from common.db import create_zone_event
from ae3lite.domain.entities import PlannedCommand
from ae3lite.domain.errors import (
    PlannerConfigurationError,
    SnapshotBuildError,
    TaskFinalizeError,
    TaskExecutionError,
    TaskTerminalStateReached,
)

logger = logging.getLogger(__name__)


TASK_EXECUTION_TIMEOUT_CANCEL_MSG = "ae3_task_execution_timeout"


class ExecuteTaskUseCase:
    """Runs one AE3 cycle_start stage and returns terminal or safely requeued task."""

    FAIL_SAFE_SHUTDOWN_CHANNELS = (
        "valve_clean_fill",
        "valve_clean_supply",
        "valve_solution_fill",
        "valve_solution_supply",
        "valve_irrigation",
        "pump_main",
    )

    def __init__(
        self,
        *,
        task_repository: Any,
        zone_snapshot_read_model: Any,
        planner: Any,
        command_gateway: Any,
        workflow_router: Any,
        workflow_repository: Any | None = None,
        correction_authority_repository: Any | None = None,
        alert_repository: Any | None = None,
        finalize_task_use_case: Any | None = None,
    ) -> None:
        self._task_repository = task_repository
        self._zone_snapshot_read_model = zone_snapshot_read_model
        self._planner = planner
        self._command_gateway = command_gateway
        self._workflow_router = workflow_router
        self._workflow_repository = workflow_repository
        self._correction_authority_repository = correction_authority_repository
        self._alert_repository = alert_repository
        self._finalize_task_use_case = finalize_task_use_case or FinalizeTaskUseCase(task_repository=task_repository)

    async def run(self, *, task: Any, now: datetime) -> Any:
        owner = str(task.claimed_by or "").strip()
        if owner == "":
            raise TaskExecutionError("ae3_task_missing_owner", f"Task {task.id} has no claimed_by owner")

        first_run = str(getattr(task, "status", "")).strip().lower() == "claimed"
        running_task = await self._task_repository.mark_running(task_id=task.id, owner=owner, now=now)
        if running_task is None:
            raise TaskExecutionError("ae3_task_running_transition_failed", f"Unable to mark task {task.id} running")

        if first_run:
            try:
                await create_zone_event(running_task.zone_id, "AE_TASK_STARTED", {
                    "task_id": running_task.id,
                    "topology": str(getattr(running_task, "topology", "") or ""),
                    "stage": str(getattr(running_task, "current_stage", "") or ""),
                    "intent_trigger": str(getattr(running_task, "intent_trigger", "") or "") or None,
                })
            except Exception:
                logger.warning(
                    "AE3 failed to log AE_TASK_STARTED event zone_id=%s task_id=%s",
                    running_task.zone_id,
                    running_task.id,
                    exc_info=True,
                )

        snapshot = None
        plan = None
        try:
            snapshot = await self._zone_snapshot_read_model.load(zone_id=running_task.zone_id)
            plan = self._planner.build(task=running_task, snapshot=snapshot)

            # v2: all two_tank tasks go through WorkflowRouter
            topology = running_task.topology
            if topology in ("two_tank", "two_tank_drip_substrate_trays"):
                final_task = await self._workflow_router.run(task=running_task, plan=plan, now=now)
                if final_task is not None and not bool(getattr(final_task, "is_active", False)):
                    return final_task
                await self._mark_correction_config_applied_if_needed(
                    task=final_task,
                    snapshot=snapshot,
                    plan=plan,
                    now=now,
                )
                if str(getattr(final_task, "status", "")).strip().lower() == "completed":
                    try:
                        await create_zone_event(final_task.zone_id, "AE_TASK_COMPLETED", {
                            "task_id": final_task.id,
                            "topology": str(getattr(final_task, "topology", "") or ""),
                            "stage": str(getattr(final_task, "current_stage", "") or ""),
                        })
                    except Exception:
                        logger.warning(
                            "AE3 failed to log AE_TASK_COMPLETED event zone_id=%s task_id=%s",
                            final_task.zone_id,
                            final_task.id,
                            exc_info=True,
                        )
                return final_task

            # Fallback for non-two-tank topologies (generic single-batch)
            if len(plan.steps) < 1:
                raise TaskExecutionError(
                    "unsupported_command_plan_steps",
                    f"AE3-Lite requires at least one command step, got {len(plan.steps)} for task_id={running_task.id}",
                )
            result = await self._command_gateway.run_batch(task=running_task, commands=plan.steps, now=now)
            if not result["success"]:
                raise TaskExecutionError(str(result["error_code"]), str(result["error_message"]))
            completed_task = await self._finalize_task_use_case.complete(
                task=result["task"],
                owner=owner,
                now=now,
            )
            return completed_task
        except TaskTerminalStateReached as exc:
            terminal_task = await self._load_terminal_task_or_none(
                task_id=int(getattr(exc.task, "id", 0) or getattr(running_task, "id", 0) or 0),
                fallback_task=exc.task,
            )
            if terminal_task is not None:
                logger.info(
                    "AE3 task execution stopped after external terminal transition: zone_id=%s task_id=%s status=%s",
                    getattr(terminal_task, "zone_id", None),
                    getattr(terminal_task, "id", None),
                    getattr(terminal_task, "status", None),
                )
                return terminal_task
            raise
        except asyncio.CancelledError as exc:
            if not self._is_timeout_cancellation(exc):
                raise

            timeout_now = datetime.now(timezone.utc)
            logger.error(
                "AE3 task execution cancelled by runtime timeout: zone_id=%s task_id=%s stage=%s error_code=%s",
                running_task.zone_id,
                running_task.id,
                getattr(running_task, "current_stage", None),
                TASK_EXECUTION_TIMEOUT_CANCEL_MSG,
            )
            await self._attempt_fail_safe_shutdown(
                task=running_task,
                snapshot=snapshot,
                plan=plan,
                now=timeout_now,
            )
            return await self._fail_closed(
                task=running_task,
                owner=owner,
                error_code=TASK_EXECUTION_TIMEOUT_CANCEL_MSG,
                error_message="Task execution exceeded runtime timeout",
                now=timeout_now,
            )
        except (SnapshotBuildError, PlannerConfigurationError, TaskExecutionError, TaskFinalizeError) as exc:
            terminal_task = await self._load_terminal_task_or_none(
                task_id=int(getattr(running_task, "id", 0) or 0),
                fallback_task=running_task,
            )
            if terminal_task is not None:
                logger.info(
                    "AE3 task execution stopped after external terminal transition: zone_id=%s task_id=%s status=%s reason=%s",
                    getattr(terminal_task, "zone_id", None),
                    getattr(terminal_task, "id", None),
                    getattr(terminal_task, "status", None),
                    getattr(exc, "code", type(exc).__name__),
                )
                return terminal_task
            error_code = getattr(exc, "code", "ae3_task_execution_failed")
            logger.error(
                "AE3 task execution domain error: zone_id=%s task_id=%s stage=%s error_type=%s error_code=%s error=%s",
                running_task.zone_id,
                running_task.id,
                getattr(running_task, "current_stage", None),
                type(exc).__name__,
                error_code,
                exc,
            )
            await self._attempt_fail_safe_shutdown(
                task=running_task,
                snapshot=snapshot,
                plan=plan,
                now=now,
            )
            return await self._fail_closed(
                task=running_task,
                owner=owner,
                error_code=error_code,
                error_message=str(exc),
                now=now,
            )
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            logger.error(
                "AE3 task execution unhandled exception: zone_id=%s task_id=%s stage=%s error_type=%s error=%s",
                running_task.zone_id,
                running_task.id,
                getattr(running_task, "current_stage", None),
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            await self._attempt_fail_safe_shutdown(
                task=running_task,
                snapshot=snapshot,
                plan=plan,
                now=now,
            )
            return await self._fail_closed(
                task=running_task,
                owner=owner,
                error_code="ae3_task_execution_unhandled_exception",
                error_message=message,
                now=now,
            )

    async def _fail_closed(
        self,
        *,
        task: Any,
        owner: str,
        error_code: str,
        error_message: str,
        now: datetime,
    ) -> Any:
        await self._sync_workflow_failure_state(task=task, now=now)
        await self._emit_task_failed_alert(
            task=task,
            error_code=error_code,
            error_message=error_message,
            now=now,
        )
        try:
            await create_zone_event(
                int(getattr(task, "zone_id", 0) or 0),
                "AE_TASK_FAILED",
                {
                    "task_id": int(getattr(task, "id", 0) or 0),
                    "error_code": str(error_code),
                    "error_message": str(error_message),
                    "stage": str(getattr(task, "current_stage", "") or ""),
                    "topology": str(getattr(task, "topology", "") or ""),
                },
            )
        except Exception:
            logger.warning(
                "AE3 failed to log AE_TASK_FAILED event zone_id=%s task_id=%s error_code=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                error_code,
                exc_info=True,
            )
        return await self._finalize_task_use_case.fail_closed(
            task=task,
            owner=owner,
            error_code=error_code,
            error_message=error_message,
            now=now,
            )

    async def _sync_workflow_failure_state(self, *, task: Any, now: datetime) -> None:
        if self._workflow_repository is None:
            return
        try:
            await self._workflow_repository.upsert_phase(
                zone_id=int(getattr(task, "zone_id", 0) or 0),
                workflow_phase="idle",
                payload={"ae3_cycle_start_stage": str(getattr(task, "current_stage", "") or "")},
                scheduler_task_id=str(getattr(task, "id", "") or ""),
                now=now,
            )
        except Exception:
            logger.warning(
                "AE3 failed to sync zone_workflow_state on fail-closed zone_id=%s task_id=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                exc_info=True,
            )

    async def _emit_task_failed_alert(
        self,
        *,
        task: Any,
        error_code: str,
        error_message: str,
        now: datetime,
    ) -> None:
        repository = self._alert_repository
        if repository is None:
            return

        try:
            task_status = "failed"
            task_id = int(getattr(task, "id", 0) or 0)
            zone_id = int(getattr(task, "zone_id", 0) or 0)
            workflow = getattr(task, "workflow", None)
            now_utc = now.astimezone(timezone.utc) if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
            details: dict[str, Any] = {
                "task_id": task_id,
                "task_type": str(getattr(task, "task_type", "") or "").strip().lower(),
                "task_status": task_status,
                "error_code": str(error_code),
                "error_message": str(error_message),
                "message": str(error_message),
                "stage": str(getattr(task, "current_stage", "") or "").strip(),
                "workflow_phase": str(getattr(task, "workflow_phase", "") or "").strip(),
                "stage_retry_count": int(getattr(workflow, "stage_retry_count", 0) or 0),
                "topology": str(getattr(task, "topology", "") or "").strip().lower(),
                "failed_at": now_utc.isoformat(),
            }
            corr = getattr(task, "correction", None)
            if corr is not None:
                details["corr_step"] = str(getattr(corr, "corr_step", "") or "").strip()

            alert_code = "biz_ae3_task_failed"
            alert_severity = "error"
            if str(error_code).strip().lower() == "zone_correction_config_missing_critical":
                alert_code = "biz_zone_correction_config_missing"
                alert_severity = "critical"
            if str(error_code).strip().lower() == "zone_dosing_calibration_missing_critical":
                alert_code = "biz_zone_dosing_calibration_missing"
                alert_severity = "critical"
            if str(error_code).strip().lower() == "zone_pid_config_missing_critical":
                alert_code = "biz_zone_pid_config_missing"
                alert_severity = "critical"
            if str(error_code).strip().lower() == "zone_recipe_phase_targets_missing_critical":
                alert_code = "biz_zone_recipe_phase_targets_missing"
                alert_severity = "critical"

            await repository.create_or_update_active(
                zone_id=zone_id,
                code=alert_code,
                details=details,
                now=now,
                category="operations",
                severity=alert_severity,
            )
        except Exception:
            logger.warning(
                "AE3 failed to write task-failed alert: task_id=%s zone_id=%s code=%s",
                getattr(task, "id", None),
                getattr(task, "zone_id", None),
                error_code,
                exc_info=True,
            )

    async def _attempt_fail_safe_shutdown(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
        now: datetime,
    ) -> None:
        topology = str(getattr(plan, "topology", "") or getattr(task, "topology", "")).strip().lower()
        if topology not in {"two_tank", "two_tank_drip_substrate_trays"}:
            return
        get_task_by_id = getattr(self._task_repository, "get_by_id", None)
        if callable(get_task_by_id):
            try:
                current_task = await get_task_by_id(task_id=int(getattr(task, "id", 0) or 0))
            except Exception:
                logger.warning(
                    "AE3 fail-safe shutdown preflight failed to load task state: task_id=%s zone_id=%s",
                    getattr(task, "id", None),
                    getattr(task, "zone_id", None),
                    exc_info=True,
                )
                current_task = None
            if current_task is None or not bool(getattr(current_task, "is_active", False)):
                self._log_skip_fail_safe_shutdown(task=task, reason="task_missing_or_inactive")
                return
        actuators = getattr(snapshot, "actuators", ()) if snapshot is not None else ()
        if not actuators:
            return

        planned_commands: list[PlannedCommand] = []
        seen_pairs: set[tuple[str, str]] = set()
        for channel in self.FAIL_SAFE_SHUTDOWN_CHANNELS:
            for actuator in actuators:
                node_uid = str(getattr(actuator, "node_uid", "") or "").strip()
                node_type = str(getattr(actuator, "node_type", "") or "").strip().lower()
                actuator_channel = str(getattr(actuator, "channel", "") or "").strip().lower()
                if node_uid == "" or node_type != "irrig" or actuator_channel != channel:
                    continue
                pair = (node_uid, actuator_channel)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                planned_commands.append(
                    PlannedCommand(
                        step_no=len(planned_commands) + 1,
                        node_uid=node_uid,
                        channel=actuator_channel,
                        payload={
                            "name": "fail_safe_shutdown",
                            "cmd": "set_relay",
                            "params": {"state": False},
                            "allow_no_effect": True,
                            "dedupe_bypass": True,
                        },
                    )
                )

        if not planned_commands:
            return
        try:
            result = await self._command_gateway.run_batch(
                task=task,
                commands=tuple(planned_commands),
                now=now,
                track_task_state=False,
            )
            if not bool(result.get("success")):
                logger.error(
                    "AE3 fail-safe shutdown batch reported non-success: task_id=%s zone_id=%s error_code=%s",
                    getattr(task, "id", None),
                    getattr(task, "zone_id", None),
                    result.get("error_code"),
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "AE3 fail-safe shutdown batch failed: task_id=%s zone_id=%s",
                getattr(task, "id", None),
                getattr(task, "zone_id", None),
            )

    def _log_skip_fail_safe_shutdown(self, *, task: Any, reason: str) -> None:
        logger.info(
            "AE3 skipping fail-safe shutdown: task_id=%s zone_id=%s reason=%s",
            getattr(task, "id", None),
            getattr(task, "zone_id", None),
            reason,
        )

    async def _mark_correction_config_applied_if_needed(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
        now: datetime,
    ) -> None:
        repository = self._correction_authority_repository
        if repository is None:
            return

        topology = str(getattr(plan, "topology", "") or getattr(task, "topology", "")).strip().lower()
        if topology not in {"two_tank", "two_tank_drip_substrate_trays"}:
            return

        correction_config = getattr(snapshot, "correction_config", None)
        if not isinstance(correction_config, dict):
            return
        meta = correction_config.get("meta")
        if not isinstance(meta, dict):
            return
        version = meta.get("version")
        try:
            version_int = int(version)
        except (TypeError, ValueError):
            return
        if version_int <= 0:
            return
        await repository.mark_applied(zone_id=int(snapshot.zone_id), version=version_int, now=now)

    def _is_timeout_cancellation(self, exc: asyncio.CancelledError) -> bool:
        return any(str(arg) == TASK_EXECUTION_TIMEOUT_CANCEL_MSG for arg in getattr(exc, "args", ()))

    async def _load_terminal_task_or_none(self, *, task_id: int, fallback_task: Any) -> Any | None:
        if task_id <= 0:
            task = fallback_task
        else:
            get_task_by_id = getattr(self._task_repository, "get_by_id", None)
            if callable(get_task_by_id):
                try:
                    task = await get_task_by_id(task_id=task_id)
                except Exception:
                    logger.warning(
                        "AE3 failed to load current task state for terminal short-circuit: task_id=%s",
                        task_id,
                        exc_info=True,
                    )
                    task = fallback_task
            else:
                task = fallback_task
        if task is None or bool(getattr(task, "is_active", False)):
            return None
        return task
