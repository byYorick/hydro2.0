"""Two-tank workflow domain entrypoint."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict

from infrastructure.observability import log_structured

logger = logging.getLogger(__name__)


class TwoTankWorkflow:
    """Runs two-tank startup/recovery workflow."""

    def __init__(self, *, execute_impl: Callable[..., Awaitable[Dict[str, Any]]]) -> None:
        self._execute_impl = execute_impl

    async def execute(
        self,
        *,
        zone_id: int,
        payload: Dict[str, Any],
        context: Dict[str, Any],
        decision: Any,
    ) -> Dict[str, Any]:
        started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        result = await self._execute_impl(
            zone_id=zone_id,
            payload=payload,
            context=context,
            decision=decision,
        )
        log_structured(
            logger,
            logging.INFO if result.get("success") else logging.WARNING,
            "Two-tank workflow handled",
            component="workflow_router",
            zone_id=zone_id,
            task_id=str(context.get("task_id") or "") or None,
            task_type="diagnostics",
            workflow=str(result.get("workflow") or payload.get("workflow") or "") or None,
            workflow_phase=str(result.get("workflow_phase") or payload.get("workflow_phase") or "") or None,
            decision=str(result.get("decision") or decision.decision or "") or None,
            reason_code=str(result.get("reason_code") or "") or None,
            command_count=int(result.get("commands_total") or 0),
            result_status="success" if result.get("success") else "failed",
            correlation_id=str(context.get("correlation_id") or "") or None,
            started_at=started_at,
        )
        return result
