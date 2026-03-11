"""Execute one claimed AE3-Lite task to next safe state (v2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ae3lite.application.use_cases.finalize_task import FinalizeTaskUseCase
from ae3lite.domain.errors import (
    PlannerConfigurationError,
    SnapshotBuildError,
    TaskFinalizeError,
    TaskExecutionError,
)


class ExecuteTaskUseCase:
    """Runs one AE3 cycle_start stage and returns terminal or safely requeued task."""

    def __init__(
        self,
        *,
        task_repository: Any,
        zone_snapshot_read_model: Any,
        planner: Any,
        command_gateway: Any,
        workflow_router: Any,
        zone_correction_config_repository: Any | None = None,
        finalize_task_use_case: Any | None = None,
    ) -> None:
        self._task_repository = task_repository
        self._zone_snapshot_read_model = zone_snapshot_read_model
        self._planner = planner
        self._command_gateway = command_gateway
        self._workflow_router = workflow_router
        self._zone_correction_config_repository = zone_correction_config_repository
        self._finalize_task_use_case = finalize_task_use_case or FinalizeTaskUseCase(task_repository=task_repository)

    async def run(self, *, task: Any, now: datetime) -> Any:
        owner = str(task.claimed_by or "").strip()
        if owner == "":
            raise TaskExecutionError("ae3_task_missing_owner", f"Task {task.id} has no claimed_by owner")

        running_task = await self._task_repository.mark_running(task_id=task.id, owner=owner, now=now)
        if running_task is None:
            raise TaskExecutionError("ae3_task_running_transition_failed", f"Unable to mark task {task.id} running")

        try:
            snapshot = await self._zone_snapshot_read_model.load(zone_id=running_task.zone_id)
            plan = self._planner.build(task=running_task, snapshot=snapshot)

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
        except (SnapshotBuildError, PlannerConfigurationError, TaskExecutionError, TaskFinalizeError) as exc:
            return await self._fail_closed(
                task=running_task,
                owner=owner,
                error_code=getattr(exc, "code", "ae3_task_execution_failed"),
                error_message=str(exc),
                now=now,
            )
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
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
        return await self._finalize_task_use_case.fail_closed(
            task=task,
            owner=owner,
            error_code=error_code,
            error_message=error_message,
            now=now,
        )

    async def _mark_correction_config_applied_if_needed(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
        now: datetime,
    ) -> None:
        repository = self._zone_correction_config_repository
        if repository is None:
            return
        if getattr(task, "is_active", False):
            return
        if str(getattr(task, "status", "")).strip().lower() not in {"completed", "failed"}:
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
