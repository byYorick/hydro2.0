"""Request a public manual step for an active AE3-Lite task."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ae3lite.application.use_cases.manual_control_contract import (
    allowed_manual_steps_for_stage,
    normalize_control_mode,
)
from ae3lite.domain.errors import ManualControlError


class RequestManualStepUseCase:
    """Validate and persist a pending manual step for the active zone task."""

    def __init__(
        self,
        *,
        task_repository: Any,
        fetch_fn: Any,
    ) -> None:
        self._task_repository = task_repository
        self._fetch_fn = fetch_fn

    async def run(
        self,
        *,
        zone_id: int,
        manual_step: str,
        now: datetime,
    ) -> dict[str, Any]:
        control_mode = await self._load_control_mode(zone_id=zone_id)
        if control_mode == "auto":
            raise ManualControlError(
                "manual_step_forbidden_in_auto_mode",
                "manual step disabled in auto mode",
                status_code=409,
                details={"zone_id": zone_id},
            )

        task = await self._task_repository.get_active_for_zone(zone_id=zone_id)
        if task is None:
            raise ManualControlError(
                "manual_step_no_active_task",
                "no active automation task for zone",
                status_code=409,
                details={"zone_id": zone_id},
            )

        current_stage = str(getattr(task.workflow, "current_stage", "") or "")
        workflow_phase = str(getattr(task.workflow, "workflow_phase", "") or "")
        allowed_steps = allowed_manual_steps_for_stage(current_stage)
        if manual_step not in allowed_steps:
            raise ManualControlError(
                "manual_step_not_allowed_for_stage",
                "manual step is not allowed for current stage",
                status_code=422,
                details={
                    "zone_id": zone_id,
                    "current_stage": current_stage,
                    "workflow_phase": workflow_phase,
                    "allowed_manual_steps": allowed_steps,
                },
            )

        updated = await self._task_repository.set_pending_manual_step(
            task_id=int(task.id),
            manual_step=manual_step,
            now=now,
        )
        if updated is None:
            raise ManualControlError(
                "manual_step_task_changed",
                "active task changed before manual step could be stored",
                status_code=409,
                details={
                    "zone_id": zone_id,
                    "task_id": int(task.id),
                },
            )

        return {
            "zone_id": zone_id,
            "task_id": str(updated.id),
            "manual_step": manual_step,
            "pending_manual_step": manual_step,
            "control_mode": control_mode,
            "current_stage": current_stage,
            "workflow_phase": workflow_phase,
        }

    async def _load_control_mode(self, *, zone_id: int) -> str:
        rows = await self._fetch_fn(
            """
            SELECT control_mode
            FROM zones
            WHERE id = $1
            LIMIT 1
            """,
            zone_id,
        )
        if not rows:
            return "auto"
        row = rows[0]
        raw = row.get("control_mode") if hasattr(row, "get") else getattr(row, "control_mode", None)
        return normalize_control_mode(raw)


__all__ = ["RequestManualStepUseCase"]
