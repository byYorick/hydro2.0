"""CAS-safe upsert helpers for ``zone_workflow_state``."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping, Optional

from ae3lite.domain.errors import Ae3LiteError, ErrorCodes, TaskExecutionError

logger = logging.getLogger(__name__)

CAS_MAX_ATTEMPTS = 3


class WorkflowStateSyncError(Ae3LiteError):
    """Workflow phase sync failed after CAS retries."""

    def __init__(self, message: str, *, zone_id: int, workflow_phase: str) -> None:
        super().__init__(message)
        self.zone_id = int(zone_id)
        self.workflow_phase = str(workflow_phase)
        self.code = ErrorCodes.AE3_WORKFLOW_STATE_SYNC_FAILED


def _is_cas_conflict(exc: Exception) -> bool:
    return isinstance(exc, Ae3LiteError) and "CAS conflict" in str(exc)


async def upsert_workflow_phase_strict(
    workflow_repo: Any,
    *,
    zone_id: int,
    workflow_phase: str,
    payload: Mapping[str, Any],
    scheduler_task_id: Optional[str],
    now: datetime,
    max_attempts: int = CAS_MAX_ATTEMPTS,
) -> None:
    """Upsert workflow phase with bounded CAS retry; raise on exhaustion."""
    attempts = max(1, int(max_attempts))
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            await workflow_repo.upsert_phase(
                zone_id=int(zone_id),
                workflow_phase=str(workflow_phase),
                payload=dict(payload),
                scheduler_task_id=scheduler_task_id,
                now=now,
            )
            return
        except Exception as exc:
            last_exc = exc
            if _is_cas_conflict(exc) and attempt < attempts - 1:
                continue
            break
    raise WorkflowStateSyncError(
        (
            f"Не удалось синхронизировать zone_workflow_state после {attempts} попыток "
            f"zone_id={zone_id} phase={workflow_phase}"
        ),
        zone_id=int(zone_id),
        workflow_phase=str(workflow_phase),
    ) from last_exc


async def upsert_workflow_phase_task_error(
    workflow_repo: Any,
    *,
    zone_id: int,
    workflow_phase: str,
    payload: Mapping[str, Any],
    scheduler_task_id: Optional[str],
    now: datetime,
) -> None:
    """Strict upsert that surfaces ``TaskExecutionError`` to the task FSM."""
    try:
        await upsert_workflow_phase_strict(
            workflow_repo,
            zone_id=zone_id,
            workflow_phase=workflow_phase,
            payload=payload,
            scheduler_task_id=scheduler_task_id,
            now=now,
        )
    except WorkflowStateSyncError as exc:
        raise TaskExecutionError(
            ErrorCodes.AE3_WORKFLOW_STATE_SYNC_FAILED,
            str(exc),
        ) from exc


__all__ = [
    "CAS_MAX_ATTEMPTS",
    "WorkflowStateSyncError",
    "upsert_workflow_phase_strict",
    "upsert_workflow_phase_task_error",
]
