"""Command dispatch orchestration for scheduler execution flows."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict

from infrastructure.observability import log_structured

logger = logging.getLogger(__name__)


class CommandDispatch:
    """Coordinates command dispatch boundaries and result aggregation logs."""

    def __init__(
        self,
        *,
        execute_device_task_impl: Callable[..., Awaitable[Dict[str, Any]]],
        dispatch_command_plan_impl: Callable[..., Awaitable[Dict[str, Any]]],
    ) -> None:
        self._execute_device_task_impl = execute_device_task_impl
        self._dispatch_command_plan_impl = dispatch_command_plan_impl

    async def execute_device_task(
        self,
        *,
        zone_id: int,
        payload: Dict[str, Any],
        mapping: Any,
        context: Dict[str, Any],
        decision: Any,
        task_type: str,
    ) -> Dict[str, Any]:
        started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        result = await self._execute_device_task_impl(
            zone_id,
            payload,
            mapping,
            context=context,
            decision=decision,
        )
        log_structured(
            logger,
            logging.INFO if result.get("success") else logging.ERROR,
            "Device task dispatch completed",
            component="command_dispatch",
            zone_id=zone_id,
            task_id=str(context.get("task_id") or "") or None,
            task_type=task_type,
            workflow=str(result.get("workflow") or "") or None,
            decision=str(result.get("decision") or decision.decision or "") or None,
            reason_code=str(result.get("reason_code") or "") or None,
            command_count=int(result.get("commands_total") or 0),
            result_status="success" if result.get("success") else "failed",
            correlation_id=str(context.get("correlation_id") or "") or None,
            started_at=started_at,
            commands_failed=int(result.get("commands_failed") or 0),
        )
        return result

    async def dispatch_command_plan(
        self,
        *,
        zone_id: int,
        command_plan: Any,
        context: Dict[str, Any],
        decision: Any,
        task_type: str,
    ) -> Dict[str, Any]:
        started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        plan_size = len(command_plan) if isinstance(command_plan, list) else 0
        log_structured(
            logger,
            logging.INFO,
            "Dispatching workflow command plan",
            component="command_dispatch",
            zone_id=zone_id,
            task_id=str(context.get("task_id") or "") or None,
            task_type=task_type,
            workflow=None,
            decision=decision.decision,
            reason_code=decision.reason_code,
            command_count=plan_size,
            result_status="success",
            correlation_id=str(context.get("correlation_id") or "") or None,
        )
        result = await self._dispatch_command_plan_impl(
            zone_id=zone_id,
            command_plan=command_plan,
            context=context,
            decision=decision,
        )
        log_structured(
            logger,
            logging.INFO if result.get("success") else logging.ERROR,
            "Workflow command plan dispatch finished",
            component="command_dispatch",
            zone_id=zone_id,
            task_id=str(context.get("task_id") or "") or None,
            task_type=task_type,
            workflow=None,
            decision=decision.decision,
            reason_code=decision.reason_code,
            command_count=int(result.get("commands_total") or 0),
            result_status="success" if result.get("success") else "failed",
            correlation_id=str(context.get("correlation_id") or "") or None,
            started_at=started_at,
            commands_failed=int(result.get("commands_failed") or 0),
        )
        return result
