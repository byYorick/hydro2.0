"""Workflow phase synchronization boundary for scheduler execution."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict

from infrastructure.observability import log_structured

logger = logging.getLogger(__name__)


class WorkflowStateSync:
    """Synchronizes workflow phase and persistence through executor core."""

    def __init__(
        self,
        *,
        sync_impl: Callable[..., Awaitable[None]],
    ) -> None:
        self._sync_impl = sync_impl

    async def sync(
        self,
        *,
        zone_id: int,
        task_type: str,
        payload: Dict[str, Any],
        result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> None:
        started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self._sync_impl(
            zone_id=zone_id,
            task_type=task_type,
            payload=payload,
            result=result,
            context=context,
        )
        log_structured(
            logger,
            logging.INFO,
            "Workflow state synchronized",
            component="workflow_state_sync",
            zone_id=zone_id,
            task_id=str(context.get("task_id") or "") or None,
            task_type=task_type,
            workflow=str(result.get("workflow") or payload.get("workflow") or "") or None,
            workflow_phase=str(result.get("workflow_phase") or payload.get("workflow_phase") or "") or None,
            decision=str(result.get("decision") or "") or None,
            reason_code=str(result.get("reason_code") or "") or None,
            command_count=int(result.get("commands_total") or 0),
            result_status="success" if result.get("success") else "failed",
            correlation_id=str(context.get("correlation_id") or "") or None,
            started_at=started_at,
        )
