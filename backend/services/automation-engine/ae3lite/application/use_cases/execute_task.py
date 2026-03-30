"""Execute one claimed AE3-Lite task to next safe state (v2)."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import timezone
from datetime import datetime
from datetime import timedelta
from typing import Any, Mapping

from ae3lite.application.use_cases.finalize_task import FinalizeTaskUseCase
from common.db import create_zone_event
from common.infra_alerts import send_infra_alert
from common.service_logs import send_service_log
from ae3lite.domain.entities import PlannedCommand
from ae3lite.domain.errors import (
    ErrorCodes,
    PlannerConfigurationError,
    SnapshotBuildError,
    TaskFinalizeError,
    TaskExecutionError,
    TaskTerminalStateReached,
)

logger = logging.getLogger(__name__)


TASK_EXECUTION_TIMEOUT_CANCEL_MSG = "ae3_task_execution_timeout"
NODE_STALE_ONLINE_THRESHOLD_SEC = max(1, int(os.getenv("NODE_OFFLINE_TIMEOUT_SEC", "120")))
SNAPSHOT_TRANSIENT_RETRY_SEC = max(1, int(os.getenv("AE3_SNAPSHOT_TRANSIENT_RETRY_SEC", "10")))
SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC = max(
    SNAPSHOT_TRANSIENT_RETRY_SEC,
    int(os.getenv("AE3_SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC", "90")),
)
SNAPSHOT_RETRY_SCHEDULED_CODE = "infra_ae3_snapshot_retry_scheduled"
SNAPSHOT_RETRY_EXHAUSTED_CODE = "ae3_snapshot_retry_exhausted"


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
        command_repository: Any | None = None,
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
        self._command_repository = command_repository
        self._finalize_task_use_case = finalize_task_use_case or FinalizeTaskUseCase(task_repository=task_repository)

    async def run(self, *, task: Any, now: datetime) -> Any:
        owner = str(task.claimed_by or "").strip()
        if owner == "":
            raise TaskExecutionError("ae3_task_missing_owner", f"Task {task.id} has no claimed_by owner")

        first_run = str(getattr(task, "status", "")).strip().lower() == "claimed"
        running_task = await self._task_repository.mark_running(task_id=task.id, owner=owner, now=now)
        if running_task is None:
            raise TaskExecutionError("ae3_task_running_transition_failed", f"Unable to mark task {task.id} running")

        snapshot = None
        plan = None
        start_observability_emitted = False
        try:
            snapshot = await self._zone_snapshot_read_model.load(zone_id=running_task.zone_id)
            plan = self._planner.build(task=running_task, snapshot=snapshot)
            if first_run:
                await self._emit_start_readiness_confirmed(
                    task=running_task,
                    snapshot=snapshot,
                    plan=plan,
                )
                start_observability_emitted = True

            # v2: all two_tank tasks go through WorkflowRouter
            topology = running_task.topology
            if topology in ("two_tank", "two_tank_drip_substrate_trays"):
                final_task = await self._workflow_router.run(task=running_task, plan=plan, now=now)
                await self._mark_correction_config_applied_if_needed(
                    task=final_task,
                    snapshot=snapshot,
                    plan=plan,
                    now=now,
                )
                if final_task is not None and not bool(getattr(final_task, "is_active", False)):
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
        except SnapshotBuildError as exc:
            snapshot_error_code = str(
                getattr(exc, "code", ErrorCodes.AE3_SNAPSHOT_BUILD_FAILED) or ErrorCodes.AE3_SNAPSHOT_BUILD_FAILED
            )
            if first_run and not start_observability_emitted:
                self._emit_start_readiness_failed(
                    task=running_task,
                    snapshot=snapshot,
                    error_code=snapshot_error_code,
                    error=exc,
                )
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
                    type(exc).__name__,
                )
                return terminal_task

            retried_task = await self._retry_transient_snapshot_gap(
                task=running_task,
                owner=owner,
                error=exc,
                now=now,
            )
            if retried_task is not None:
                return retried_task

            logger.error(
                "AE3 task execution domain error: zone_id=%s task_id=%s stage=%s error_type=%s error_code=%s error=%s",
                running_task.zone_id,
                running_task.id,
                getattr(running_task, "current_stage", None),
                type(exc).__name__,
                snapshot_error_code,
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
                error_code=snapshot_error_code,
                error_message=str(exc),
                now=now,
            )
        except (PlannerConfigurationError, TaskExecutionError, TaskFinalizeError) as exc:
            if first_run and not start_observability_emitted and isinstance(exc, PlannerConfigurationError):
                self._emit_start_readiness_failed(
                    task=running_task,
                    snapshot=snapshot,
                    error_code=str(getattr(exc, "code", "ae3_task_execution_failed") or "ae3_task_execution_failed"),
                    error=exc,
                )
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

    async def _retry_transient_snapshot_gap(
        self,
        *,
        task: Any,
        owner: str,
        error: SnapshotBuildError,
        now: datetime,
    ) -> Any | None:
        snapshot_error_code = getattr(error, "code", ErrorCodes.AE3_SNAPSHOT_BUILD_FAILED)
        error_message = str(error).strip()
        if not self._is_transient_snapshot_gap(task=task, error_code=snapshot_error_code):
            return None

        stage_entered_at = getattr(getattr(task, "workflow", None), "stage_entered_at", None)
        stage_age_sec = self._stage_age_sec(stage_entered_at=stage_entered_at, now=now)
        details = {
            "task_id": int(getattr(task, "id", 0) or 0),
            "stage": str(getattr(task, "current_stage", "") or ""),
            "workflow_phase": str(getattr(task, "workflow_phase", "") or ""),
            "topology": str(getattr(task, "topology", "") or ""),
            "error_code": SNAPSHOT_RETRY_EXHAUSTED_CODE,
            "snapshot_error_code": snapshot_error_code,
            "snapshot_error": error_message,
            "snapshot_reason": "no_online_actuator_channels",
            "stage_age_sec": stage_age_sec,
            "max_stage_age_sec": SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC,
        }

        if stage_age_sec >= SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC:
            final_message = (
                f"{error_message} (transient snapshot retry budget exhausted after {stage_age_sec}s "
                f"in stage {getattr(task, 'current_stage', '')})"
            )
            logger.error(
                "AE3 transient snapshot gap exhausted retry budget: zone_id=%s task_id=%s stage=%s stage_age_sec=%s error=%s",
                getattr(task, "zone_id", None),
                getattr(task, "id", None),
                getattr(task, "current_stage", None),
                stage_age_sec,
                error_message,
            )
            await self._emit_snapshot_retry_observability(
                task=task,
                now=now,
                event_type="AE_SNAPSHOT_RETRY_EXHAUSTED",
                alert_code="infra_ae3_snapshot_retry_exhausted",
                alert_message=final_message,
                severity="error",
                details=details,
            )
            return await self._fail_closed(
                task=task,
                owner=owner,
                error_code=SNAPSHOT_RETRY_EXHAUSTED_CODE,
                error_message=final_message,
                now=now,
            )

        update_stage = getattr(self._task_repository, "update_stage", None)
        if not callable(update_stage):
            raise TaskExecutionError(
                "ae3_snapshot_retry_persist_failed",
                f"Task repository does not support update_stage for transient snapshot retry task_id={task.id}",
            )

        due_at = now + timedelta(seconds=SNAPSHOT_TRANSIENT_RETRY_SEC)
        updated_task = await update_stage(
            task_id=int(getattr(task, "id", 0) or 0),
            owner=owner,
            workflow=getattr(task, "workflow"),
            correction=getattr(task, "correction", None),
            due_at=due_at,
            now=now,
        )
        if updated_task is None:
            raise TaskExecutionError(
                "ae3_snapshot_retry_persist_failed",
                f"Unable to persist transient snapshot retry for task {task.id}",
            )

        logger.warning(
            "AE3 transient snapshot gap detected: zone_id=%s task_id=%s stage=%s retry_in=%ss stage_age_sec=%s error=%s",
            getattr(task, "zone_id", None),
            getattr(task, "id", None),
            getattr(task, "current_stage", None),
            SNAPSHOT_TRANSIENT_RETRY_SEC,
            stage_age_sec,
            error_message,
        )
        await self._emit_snapshot_retry_observability(
            task=task,
            now=now,
            event_type="AE_SNAPSHOT_RETRY_SCHEDULED",
            alert_code=SNAPSHOT_RETRY_SCHEDULED_CODE,
            alert_message=error_message,
            severity="warning",
            details={
                **details,
                "retry_after_sec": SNAPSHOT_TRANSIENT_RETRY_SEC,
                "next_due_at": due_at.astimezone(timezone.utc).isoformat()
                if due_at.tzinfo is not None
                else due_at.replace(tzinfo=timezone.utc).isoformat(),
            },
        )
        return updated_task

    def _is_transient_snapshot_gap(self, *, task: Any, error_code: str) -> bool:
        topology = str(getattr(task, "topology", "") or "").strip().lower()
        return (
            topology in {"two_tank", "two_tank_drip_substrate_trays"}
            and str(error_code or "").strip() == ErrorCodes.AE3_SNAPSHOT_NO_ONLINE_ACTUATOR_CHANNELS
        )

    def _stage_age_sec(self, *, stage_entered_at: datetime | None, now: datetime) -> int:
        if not isinstance(stage_entered_at, datetime):
            return 0
        normalized_now = now.astimezone(timezone.utc) if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
        normalized_stage_entered_at = (
            stage_entered_at.astimezone(timezone.utc)
            if stage_entered_at.tzinfo is not None
            else stage_entered_at.replace(tzinfo=timezone.utc)
        )
        return max(0, int((normalized_now - normalized_stage_entered_at).total_seconds()))

    async def _emit_snapshot_retry_observability(
        self,
        *,
        task: Any,
        now: datetime,
        event_type: str,
        alert_code: str,
        alert_message: str,
        severity: str,
        details: Mapping[str, Any],
    ) -> None:
        zone_id = int(getattr(task, "zone_id", 0) or 0)
        try:
            await create_zone_event(zone_id, event_type, dict(details))
        except Exception:
            logger.warning(
                "AE3 failed to log snapshot retry observability event zone_id=%s task_id=%s event_type=%s",
                zone_id,
                int(getattr(task, "id", 0) or 0),
                event_type,
                exc_info=True,
            )

        try:
            await send_infra_alert(
                code=alert_code,
                message=alert_message,
                zone_id=zone_id,
                severity=severity,
                service="automation-engine",
                component="execute_task",
                error_type="SnapshotBuildError",
                details=dict(details),
            )
        except Exception:
            logger.warning(
                "AE3 failed to publish snapshot retry infra alert zone_id=%s task_id=%s code=%s",
                zone_id,
                int(getattr(task, "id", 0) or 0),
                alert_code,
                exc_info=True,
            )

    async def _emit_start_readiness_confirmed(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
    ) -> None:
        details = self._build_start_readiness_details(task=task, snapshot=snapshot, plan=plan)
        try:
            await create_zone_event(
                int(getattr(task, "zone_id", 0) or 0),
                "AE_TASK_STARTED",
                details,
            )
        except Exception:
            logger.warning(
                "AE3 failed to log AE_TASK_STARTED readiness event zone_id=%s task_id=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                exc_info=True,
            )
        send_service_log(
            service="automation-engine",
            level="info",
            message="AE3 task start readiness confirmed",
            context=details,
        )

    def _emit_start_readiness_failed(
        self,
        *,
        task: Any,
        snapshot: Any,
        error_code: str,
        error: Exception,
    ) -> None:
        details = self._build_start_failure_details(
            task=task,
            snapshot=snapshot,
            error_code=error_code,
            error=error,
        )
        send_service_log(
            service="automation-engine",
            level="error",
            message="AE3 task start readiness failed",
            context=details,
        )

    def _build_start_readiness_details(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
    ) -> dict[str, Any]:
        correction_config = getattr(snapshot, "correction_config", None)
        correction_meta = correction_config.get("meta") if isinstance(correction_config, Mapping) else None
        command_plans = getattr(snapshot, "command_plans", None)
        phase_targets = getattr(snapshot, "phase_targets", None)
        details: dict[str, Any] = {
            "task_id": int(getattr(task, "id", 0) or 0),
            "zone_id": int(getattr(task, "zone_id", 0) or 0),
            "topology": str(getattr(plan, "topology", "") or getattr(task, "topology", "") or ""),
            "stage": str(getattr(task, "current_stage", "") or ""),
            "workflow_phase": str(getattr(task, "workflow_phase", "") or ""),
            "intent_trigger": str(getattr(task, "intent_trigger", "") or "") or None,
            "automation_runtime": str(getattr(snapshot, "automation_runtime", "") or ""),
            "grow_cycle_id": int(getattr(snapshot, "grow_cycle_id", 0) or 0) or None,
            "current_phase_id": int(getattr(snapshot, "current_phase_id", 0) or 0) or None,
            "phase_name": str(getattr(snapshot, "phase_name", "") or "") or None,
            "actuator_count": len(getattr(snapshot, "actuators", ()) or ()),
            "pid_config_count": len(getattr(snapshot, "pid_configs", {}) or {}),
            "process_calibration_count": len(getattr(snapshot, "process_calibrations", {}) or {}),
            "command_plan_schema_version": (
                str(command_plans.get("schema_version") or "").strip()
                if isinstance(command_plans, Mapping)
                else None
            ),
            "plan_steps_count": len(getattr(plan, "steps", ()) or ()),
            "target_ph": self._extract_phase_target(phase_targets=phase_targets, key="ph"),
            "target_ec": self._extract_phase_target(phase_targets=phase_targets, key="ec"),
            "correction_config_version": (
                int(correction_meta.get("version", 0) or 0) or None
                if isinstance(correction_meta, Mapping)
                else None
            ),
        }
        return {key: value for key, value in details.items() if value is not None}

    def _build_start_failure_details(
        self,
        *,
        task: Any,
        snapshot: Any,
        error_code: str,
        error: Exception,
    ) -> dict[str, Any]:
        details: dict[str, Any] = {
            "task_id": int(getattr(task, "id", 0) or 0),
            "zone_id": int(getattr(task, "zone_id", 0) or 0),
            "topology": str(getattr(task, "topology", "") or ""),
            "stage": str(getattr(task, "current_stage", "") or ""),
            "workflow_phase": str(getattr(task, "workflow_phase", "") or ""),
            "intent_trigger": str(getattr(task, "intent_trigger", "") or "") or None,
            "error_code": str(error_code or "ae3_task_execution_failed"),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "snapshot_loaded": snapshot is not None,
        }
        if snapshot is not None:
            details.update({
                "automation_runtime": str(getattr(snapshot, "automation_runtime", "") or "") or None,
                "grow_cycle_id": int(getattr(snapshot, "grow_cycle_id", 0) or 0) or None,
                "current_phase_id": int(getattr(snapshot, "current_phase_id", 0) or 0) or None,
                "phase_name": str(getattr(snapshot, "phase_name", "") or "") or None,
            })
        return {key: value for key, value in details.items() if value is not None}

    def _extract_phase_target(self, *, phase_targets: Any, key: str) -> float | None:
        if not isinstance(phase_targets, Mapping):
            return None
        candidate = phase_targets.get(key)
        if isinstance(candidate, Mapping):
            candidate = candidate.get("target")
        if candidate is None:
            candidate = phase_targets.get(f"{key}_target")
        try:
            return float(candidate)
        except (TypeError, ValueError):
            return None

    async def _fail_closed(
        self,
        *,
        task: Any,
        owner: str,
        error_code: str,
        error_message: str,
        now: datetime,
    ) -> Any:
        extra_details = await self._build_failure_observability_details(
            task=task,
            error_code=error_code,
            now=now,
        )
        zone_id = int(getattr(task, "zone_id", 0) or 0)
        task_still_exists = await self._task_still_exists(task=task)
        if task_still_exists:
            await self._sync_workflow_failure_state(task=task, now=now)
            await self._emit_task_failed_alert(
                task=task,
                error_code=error_code,
                error_message=error_message,
                now=now,
                extra_details=extra_details,
            )
        else:
            logger.info(
                "AE3 fail-closed skipping zone-bound side-effects because task was already cleaned up: zone_id=%s task_id=%s",
                zone_id,
                int(getattr(task, "id", 0) or 0),
            )
        try:
            startup_probe_timeout = extra_details.get("startup_probe_timeout")
            if task_still_exists and isinstance(startup_probe_timeout, Mapping):
                await create_zone_event(
                    zone_id,
                    "AE_STARTUP_PROBE_TIMEOUT",
                    {
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "stage": str(getattr(task, "current_stage", "") or ""),
                        "topology": str(getattr(task, "topology", "") or ""),
                        **dict(startup_probe_timeout),
                    },
                )
            if task_still_exists:
                await create_zone_event(
                    zone_id,
                    "AE_TASK_FAILED",
                    {
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "error_code": str(error_code),
                        "error_message": str(error_message),
                        "stage": str(getattr(task, "current_stage", "") or ""),
                        "topology": str(getattr(task, "topology", "") or ""),
                        **extra_details,
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

    async def _task_still_exists(self, *, task: Any) -> bool:
        get_by_id = getattr(self._task_repository, "get_by_id", None)
        if not callable(get_by_id):
            return True
        current = await get_by_id(task_id=int(getattr(task, "id", 0) or 0))
        return current is not None

    async def _emit_task_failed_alert(
        self,
        *,
        task: Any,
        error_code: str,
        error_message: str,
        now: datetime,
        extra_details: Mapping[str, Any] | None = None,
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
            if extra_details:
                details.update(dict(extra_details))

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

            await repository.raise_active(
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

    async def _build_failure_observability_details(
        self,
        *,
        task: Any,
        error_code: str,
        now: datetime,
    ) -> dict[str, Any]:
        if str(error_code).strip().lower() != "command_timeout":
            return {}

        repository = self._command_repository
        if repository is None:
            return {}

        try:
            ae_command = await repository.get_latest_for_task(task_id=int(getattr(task, "id", 0) or 0))
            if not isinstance(ae_command, Mapping):
                return {}

            payload = ae_command.get("payload")
            payload = payload if isinstance(payload, Mapping) else {}
            external_id = str(ae_command.get("external_id") or "").strip() or None
            cmd_id = str(payload.get("cmd_id") or "").strip() or None

            legacy_command = None
            if external_id:
                legacy_command = await repository.get_legacy_command_by_id(external_id=external_id)
            elif cmd_id:
                legacy_command = await repository.get_legacy_command_by_cmd_id(
                    zone_id=int(getattr(task, "zone_id", 0) or 0),
                    cmd_id=cmd_id,
                )

            node_uid = str(ae_command.get("node_uid") or "").strip() or None
            if node_uid is None and isinstance(legacy_command, Mapping):
                node_uid = str(legacy_command.get("node_uid") or "").strip() or None

            node_context = None
            if node_uid:
                node_context = await repository.get_node_runtime_context(node_uid=node_uid)

            timeout_details = self._compose_timeout_details(
                task=task,
                ae_command=ae_command,
                payload=payload,
                legacy_command=legacy_command,
                node_context=node_context,
                now=now,
            )
            if timeout_details is None:
                return {}

            result: dict[str, Any] = {"timed_out_command": timeout_details}
            if self._is_startup_probe_timeout(task=task, timeout_details=timeout_details):
                result["startup_probe_timeout"] = {
                    "probe_name": timeout_details.get("probe_name"),
                    "cmd_id": timeout_details.get("cmd_id"),
                    "node_uid": timeout_details.get("node_uid"),
                    "channel": timeout_details.get("channel"),
                    "command": timeout_details.get("command"),
                    "publish_status": timeout_details.get("publish_status"),
                    "legacy_status": timeout_details.get("legacy_status"),
                    "node_status": timeout_details.get("node_status"),
                    "node_last_seen_at": timeout_details.get("node_last_seen_at"),
                    "node_last_seen_age_sec": timeout_details.get("node_last_seen_age_sec"),
                    "node_stale_online_candidate": timeout_details.get("node_stale_online_candidate"),
                    "timeout_at": timeout_details.get("timeout_at"),
                }
            return result
        except Exception:
            logger.warning(
                "AE3 failed to enrich command_timeout observability details: zone_id=%s task_id=%s",
                getattr(task, "zone_id", None),
                getattr(task, "id", None),
                exc_info=True,
            )
            return {}

    def _compose_timeout_details(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        payload: Mapping[str, Any],
        legacy_command: Mapping[str, Any] | None,
        node_context: Mapping[str, Any] | None,
        now: datetime,
    ) -> dict[str, Any] | None:
        node_uid = str(ae_command.get("node_uid") or "").strip() or None
        channel = str(ae_command.get("channel") or "").strip() or None
        cmd_id = str(payload.get("cmd_id") or "").strip() or None
        command_name = str(payload.get("cmd") or "").strip() or None
        probe_name = str(payload.get("name") or "").strip() or None
        if not any((node_uid, channel, cmd_id, command_name, probe_name, legacy_command, node_context)):
            return None

        sent_at = legacy_command.get("sent_at") if isinstance(legacy_command, Mapping) else None
        ack_at = legacy_command.get("ack_at") if isinstance(legacy_command, Mapping) else None
        failed_at = legacy_command.get("failed_at") if isinstance(legacy_command, Mapping) else None
        node_last_seen_at = node_context.get("last_seen_at") if isinstance(node_context, Mapping) else None

        node_last_seen_age_sec: int | None = None
        if isinstance(node_last_seen_at, datetime):
            normalized_now = now.astimezone(timezone.utc) if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
            normalized_last_seen = (
                node_last_seen_at.astimezone(timezone.utc)
                if node_last_seen_at.tzinfo is not None
                else node_last_seen_at.replace(tzinfo=timezone.utc)
            )
            node_last_seen_age_sec = max(
                0,
                int((normalized_now - normalized_last_seen).total_seconds()),
            )

        node_status = str(node_context.get("node_status") or "").strip().lower() or None if isinstance(node_context, Mapping) else None
        node_stale_online_candidate = (
            node_status == "online"
            and node_last_seen_age_sec is not None
            and node_last_seen_age_sec >= NODE_STALE_ONLINE_THRESHOLD_SEC
        )

        details: dict[str, Any] = {
            "task_id": int(getattr(task, "id", 0) or 0),
            "stage": str(getattr(task, "current_stage", "") or ""),
            "workflow_phase": str(getattr(task, "workflow_phase", "") or ""),
            "cmd_id": cmd_id,
            "command": command_name,
            "probe_name": probe_name,
            "node_uid": node_uid,
            "channel": channel,
            "publish_status": str(ae_command.get("publish_status") or "").strip().lower() or None,
            "terminal_status": str(ae_command.get("terminal_status") or "").strip().upper() or None,
            "legacy_command_id": int(legacy_command["id"]) if isinstance(legacy_command, Mapping) and legacy_command.get("id") is not None else None,
            "legacy_status": str(legacy_command.get("status") or "").strip().upper() or None if isinstance(legacy_command, Mapping) else None,
            "sent_at": sent_at.isoformat() if isinstance(sent_at, datetime) else None,
            "ack_at": ack_at.isoformat() if isinstance(ack_at, datetime) else None,
            "failed_at": failed_at.isoformat() if isinstance(failed_at, datetime) else None,
            "timeout_at": now.astimezone(timezone.utc).isoformat() if now.tzinfo is not None else now.replace(tzinfo=timezone.utc).isoformat(),
            "node_status": node_status,
            "node_type": str(node_context.get("node_type") or "").strip().lower() or None if isinstance(node_context, Mapping) else None,
            "node_last_seen_at": node_last_seen_at.isoformat() if isinstance(node_last_seen_at, datetime) else None,
            "node_last_seen_age_sec": node_last_seen_age_sec,
            "node_stale_online_candidate": node_stale_online_candidate,
        }
        return {key: value for key, value in details.items() if value is not None}

    def _is_startup_probe_timeout(self, *, task: Any, timeout_details: Mapping[str, Any]) -> bool:
        return (
            str(getattr(task, "current_stage", "") or "").strip().lower() == "startup"
            and str(timeout_details.get("channel") or "").strip().lower() == "storage_state"
            and str(timeout_details.get("command") or "").strip().lower() == "state"
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
            if fallback_task is None or bool(getattr(fallback_task, "is_active", False)):
                return None
            return fallback_task
        return task
