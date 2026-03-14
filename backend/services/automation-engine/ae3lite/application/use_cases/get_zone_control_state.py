"""Get current control mode and allowed manual steps for a zone."""

from __future__ import annotations

from typing import Any, Optional

from ae3lite.application.use_cases.manual_control_contract import (
    AVAILABLE_CONTROL_MODES,
    allowed_manual_steps_for_stage,
    normalize_control_mode,
)


class GetZoneControlStateUseCase:
    """Returns control_mode + current_stage + allowed_manual_steps for a zone.

    Reads zones.control_mode directly (not ae_tasks snapshot) so the response
    always reflects the latest operator setting.
    """

    def __init__(self, *, task_repository: Any, fetch_fn: Any) -> None:
        self._task_repository = task_repository
        self._fetch_fn = fetch_fn

    async def run(self, *, zone_id: int) -> dict[str, Any]:
        # Read control_mode from zones table (source of truth)
        rows = await self._fetch_fn(
            "SELECT control_mode FROM zones WHERE id = $1",
            zone_id,
        )
        control_mode = "auto"
        if rows:
            raw = rows[0].get("control_mode") if hasattr(rows[0], "get") else getattr(rows[0], "control_mode", None)
            control_mode = normalize_control_mode(raw)

        # Read active task for current_stage
        task: Optional[Any] = await self._task_repository.get_active_for_zone(zone_id=zone_id)

        current_stage: Optional[str] = None
        workflow_phase: Optional[str] = None
        pending_manual_step: Optional[str] = None

        if task is not None:
            wf = getattr(task, "workflow", None)
            if wf is not None:
                current_stage = getattr(wf, "current_stage", None)
                workflow_phase = getattr(wf, "workflow_phase", None)
                pending_manual_step = getattr(wf, "pending_manual_step", None)

        # Compute allowed steps only for manual/semi modes
        allowed_manual_steps: list[str] = []
        if control_mode in ("manual", "semi") and current_stage is not None:
            allowed_manual_steps = allowed_manual_steps_for_stage(current_stage)

        return {
            "control_mode": control_mode,
            "available_modes": list(AVAILABLE_CONTROL_MODES),
            "current_stage": current_stage,
            "workflow_phase": workflow_phase,
            "pending_manual_step": pending_manual_step,
            "allowed_manual_steps": allowed_manual_steps,
        }
