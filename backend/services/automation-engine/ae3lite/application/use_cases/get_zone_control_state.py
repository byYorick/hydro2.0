"""Get current control mode and allowed manual steps for a zone."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ae3lite.application.use_cases.manual_control_contract import (
    AVAILABLE_CONTROL_MODES,
    allowed_manual_steps_for_stage,
    normalize_control_mode,
)

logger = logging.getLogger(__name__)


class GetZoneControlStateUseCase:
    """Returns control_mode + current_stage + allowed_manual_steps for a zone.

    Reads zones.control_mode directly (not ae_tasks snapshot) so the response
    always reflects the latest operator setting.
    """

    def __init__(
        self,
        *,
        task_repository: Any,
        fetch_fn: Any,
        workflow_repository: Any | None = None,
    ) -> None:
        self._task_repository = task_repository
        self._fetch_fn = fetch_fn
        self._workflow_repository = workflow_repository

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
        workflow_state: Optional[Any] = None
        last_task: Optional[Any] = None

        current_stage: Optional[str] = None
        workflow_phase: Optional[str] = None
        pending_manual_step: Optional[str] = None

        if task is not None:
            wf = getattr(task, "workflow", None)
            if wf is not None:
                current_stage = getattr(wf, "current_stage", None)
                workflow_phase = getattr(wf, "workflow_phase", None)
                pending_manual_step = getattr(wf, "pending_manual_step", None)
        elif self._workflow_repository is not None:
            try:
                workflow_state = await self._workflow_repository.get(zone_id=zone_id)
            except Exception:
                logger.warning(
                    "AE3 control state: workflow read failed for zone_id=%s",
                    zone_id,
                    exc_info=True,
                )
                workflow_state = None
            get_last_for_zone = getattr(self._task_repository, "get_last_for_zone", None)
            if callable(get_last_for_zone):
                last_task = await get_last_for_zone(zone_id=zone_id)
            if workflow_state is not None and not self._workflow_state_is_stale(
                workflow_state=workflow_state,
                last_task=last_task,
            ):
                workflow_phase = str(getattr(workflow_state, "workflow_phase", None) or "").strip() or None
                payload = getattr(workflow_state, "payload", None)
                normalized_payload = payload if isinstance(payload, Mapping) else {}
                current_stage = str(normalized_payload.get("ae3_cycle_start_stage") or "").strip() or None

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

    def _workflow_state_is_stale(self, *, workflow_state: Optional[Any], last_task: Optional[Any]) -> bool:
        if workflow_state is None or last_task is None:
            return False
        if bool(getattr(last_task, "is_active", False)):
            return False

        scheduler_task_id = str(getattr(workflow_state, "scheduler_task_id", "") or "").strip()
        if scheduler_task_id and scheduler_task_id == str(getattr(last_task, "id", "") or ""):
            return True

        workflow_updated_at = getattr(workflow_state, "updated_at", None)
        task_updated_at = getattr(last_task, "updated_at", None)
        if workflow_updated_at is None or task_updated_at is None:
            return False

        workflow_cmp = self._normalize_utc_naive(workflow_updated_at)
        task_cmp = self._normalize_utc_naive(task_updated_at)
        return task_cmp >= workflow_cmp

    def _normalize_utc_naive(self, value: Any) -> Any:
        if not isinstance(value, datetime):
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
