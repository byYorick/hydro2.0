"""SequentialCommandGateway batch authority: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.domain.errors import ErrorCodes
from ae3lite.infrastructure.gateways.command_gateway_shared import _AE3_RECOVERY_RESUME_KEY


@dataclass(frozen=True)
class CommandGatewayBatchAuthorityPorts:
    command_repository: Callable[[], Any]
    load_recovery_resume_marker: Callable[..., Awaitable[Any]]
    task_repository: Callable[[], Any]


class CommandGatewayBatchAuthority:
    def __init__(self, ports: CommandGatewayBatchAuthorityPorts) -> None:
        self._ports = ports

    def cleanup_race_batch_result(self, *, task: Any, message: str) -> dict[str, Any]:
        return {
            "success": False,
            "task": task,
            "command_statuses": [],
            "error_code": ErrorCodes.AE3_TASK_MISSING_DURING_PUBLISH,
            "error_message": message,
        }

    async def task_row_missing(self, *, task_id: int) -> bool:
        get_by_id = getattr(self._ports.task_repository(), "get_by_id", None)
        if not callable(get_by_id):
            return False
        current = await get_by_id(task_id=task_id)
        return current is None

    def stage_execution_token(self, *, task: Any) -> str:
        stage = str(getattr(task, "current_stage", "") or "").strip() or "unknown"
        workflow = getattr(task, "workflow", None)
        anchor = getattr(workflow, "stage_entered_at", None)
        if not isinstance(anchor, datetime):
            anchor = getattr(task, "created_at", None)
        if isinstance(anchor, datetime):
            return f"{stage}:{anchor.isoformat()}"
        return f"{stage}:task:{int(getattr(task, 'id', 0) or 0)}"

    async def mark_recovery_batch_resume(self, *, task: Any, now: datetime) -> bool:
        """Персистентно разрешает skip DONE planner_step только для recovery stage-run."""
        ae_command = await self._ports.command_repository().get_latest_for_task(task_id=task.id)
        if ae_command is None or not str(ae_command.get("planner_step") or "").strip():
            return False
        mark_resume = getattr(self._ports.command_repository(), "mark_recovery_batch_resume", None)
        if not callable(mark_resume):
            return False
        return bool(
            await mark_resume(
                ae_command_id=int(ae_command["id"]),
                stage_name=str(getattr(task, "current_stage", "") or ""),
                stage_execution_token=self.stage_execution_token(task=task),
                now=now,
            )
        )

    async def load_recovery_resume_marker(self, *, task: Any) -> Mapping[str, Any] | None:
        ae_command = await self._ports.command_repository().get_latest_for_task(task_id=task.id)
        if ae_command is None:
            return None
        payload = ae_command.get("payload")
        if not isinstance(payload, Mapping):
            return None
        marker = payload.get(_AE3_RECOVERY_RESUME_KEY)
        if not isinstance(marker, Mapping):
            return None
        stage = str(getattr(task, "current_stage", "") or "").strip()
        token = self.stage_execution_token(task=task)
        if (
            str(marker.get("stage") or "").strip() != stage
            or str(marker.get("stage_execution_token") or "").strip() != token
        ):
            return None
        return {
            "stage": stage,
            "stage_execution_token": token,
        }

    async def recovery_batch_resume_active(self, *, task: Any) -> bool:
        stage = str(getattr(task, "current_stage", "") or "").strip()
        token = self.stage_execution_token(task=task)
        has_resume = getattr(self._ports.command_repository(), "has_recovery_batch_resume", None)
        if callable(has_resume):
            return bool(
                await has_resume(
                    task_id=task.id,
                    stage_name=stage,
                    stage_execution_token=token,
                )
            )
        # Fallback для unit-моков без has_recovery_batch_resume.
        return await self._ports.load_recovery_resume_marker(task=task) is not None
