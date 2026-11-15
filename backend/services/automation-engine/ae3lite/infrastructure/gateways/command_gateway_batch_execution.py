"""SequentialCommandGateway batch execution: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping, Sequence

from ae3lite.domain.entities import PlannedCommand
from ae3lite.domain.errors import ErrorCodes
from ae3lite.infrastructure.gateways.command_gateway_shared import _AE3_FAIL_SAFE_KEY
from ae3lite.infrastructure.gateways.command_publish_pipeline import (
    planner_step_for_command,
)


@dataclass(frozen=True)
class CommandGatewayBatchExecutionPorts:
    command_poll_margin_sec: Callable[[], Any]
    command_stage_stop_reserve_sec: Callable[[], Any]
    completed_planner_step_status: Callable[..., Awaitable[Any]]
    load_recovery_resume_marker: Callable[..., Awaitable[Any]]
    recovery_batch_resume_active: Callable[..., Awaitable[Any]]
    run_command: Callable[..., Awaitable[Any]]
    stage_execution_token: Callable[..., Any]
    global_utcnow: Callable[..., Any]


class CommandGatewayBatchExecution:
    def __init__(self, ports: CommandGatewayBatchExecutionPorts) -> None:
        self._ports = ports

    async def run_batch(
        self,
        *,
        task: Any,
        commands: Sequence[PlannedCommand],
        now: datetime,
        track_task_state: bool = True,
    ) -> Mapping[str, Any]:
        current_task = task
        combined_statuses: list[dict[str, Any]] = []
        recovery_resume_marker: Mapping[str, Any] | None = None
        if track_task_state and await self._ports.recovery_batch_resume_active(task=task):
            recovery_resume_marker = await self._ports.load_recovery_resume_marker(task=task)
            if recovery_resume_marker is None:
                # has_recovery_batch_resume нашёл marker, но latest payload без него —
                # восстановим канонический marker из текущего stage token.
                recovery_resume_marker = {
                    "stage": str(getattr(task, "current_stage", "") or "").strip(),
                    "stage_execution_token": self._ports.stage_execution_token(task=task),
                }

        for seq_index, command in enumerate(commands):
            planner_step = planner_step_for_command(
                task=current_task,
                command=command,
                seq_index=seq_index,
            )
            if recovery_resume_marker is not None:
                completed_status = await self._ports.completed_planner_step_status(
                    task=current_task,
                    command=command,
                    planner_step=planner_step,
                )
                if completed_status is not None:
                    combined_statuses.append(completed_status)
                    continue
            # A recovered DONE dose needs no new admission. For a new dose,
            # use the time after earlier commands reached terminal status.
            command_now = self._ports.global_utcnow()
            admission_failure = self.dose_stage_admission_failure(
                task=current_task,
                command=command,
                now=command_now,
            )
            if admission_failure is not None:
                return {
                    "success": False,
                    "task": current_task,
                    "commands_total": len(combined_statuses),
                    "commands_failed": 1,
                    "command_statuses": combined_statuses,
                    **admission_failure,
                }
            result = await self._ports.run_command(
                task=current_task,
                command=command,
                now=command_now,
                track_task_state=track_task_state,
                seq_index=seq_index,
                planner_step=planner_step,
                recovery_resume_marker=recovery_resume_marker,
            )
            combined_statuses.extend(result["command_statuses"])
            current_task = result["task"]
            if not result["success"]:
                failed: dict[str, Any] = {
                    "success": False,
                    "task": current_task,
                    "commands_total": len(combined_statuses),
                    "commands_failed": 1,
                    "command_statuses": combined_statuses,
                    "error_code": result["error_code"],
                    "error_message": result["error_message"],
                }
                # Preserve admission vs poll binding for handler policy.
                if result.get("deadline_kind") is not None:
                    failed["deadline_kind"] = result["deadline_kind"]
                return failed

        return {
            "success": True,
            "task": current_task,
            "commands_total": len(combined_statuses),
            "commands_failed": 0,
            "command_statuses": combined_statuses,
        }

    def dose_stage_admission_failure(
        self,
        *,
        task: Any,
        command: PlannedCommand,
        now: datetime,
    ) -> dict[str, Any] | None:
        """Reject a new dose that cannot finish while preserving stop budget.

        This check deliberately runs before ``CommandPublishPipeline.publish`` so
        an insufficient stage budget cannot create a physical side effect. Once
        a dose is published, its terminal wait is governed only by the command
        poll timeout and is never cut short by the stage deadline.
        """
        payload = command.payload if isinstance(command.payload, Mapping) else {}
        if bool(payload.get(_AE3_FAIL_SAFE_KEY)):
            return None
        if str(payload.get("cmd") or "").strip().lower() != "dose":
            return None
        params = payload.get("params")
        if not isinstance(params, Mapping):
            return None
        try:
            duration_sec = max(0.0, float(params.get("duration_ms")) / 1000.0)
        except (TypeError, ValueError):
            return None
        workflow = getattr(task, "workflow", None)
        stage_deadline = getattr(workflow, "stage_deadline_at", None)
        if not isinstance(stage_deadline, datetime):
            return None

        normalized_now = now.replace(tzinfo=None) if now.tzinfo is not None else now
        normalized_deadline = (
            stage_deadline.replace(tzinfo=None) if stage_deadline.tzinfo is not None else stage_deadline
        )
        remaining_sec = max(0.0, (normalized_deadline - normalized_now).total_seconds())
        required_sec = (
            duration_sec + self._ports.command_poll_margin_sec() + self._ports.command_stage_stop_reserve_sec()
        )
        if remaining_sec >= required_sec:
            return None
        return {
            "error_code": ErrorCodes.AE3_COMMAND_STAGE_BUDGET_INSUFFICIENT,
            "error_message": (
                "Недостаточно stage budget для безопасной публикации dose: "
                f"remaining={remaining_sec:.3f}s required={required_sec:.3f}s "
                f"stage={getattr(task, 'current_stage', None)}"
            ),
            "deadline_kind": "stage_admission",
            "remaining_stage_sec": remaining_sec,
            "required_stage_budget_sec": required_sec,
        }
