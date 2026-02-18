"""Workflow routing for diagnostics scheduler tasks."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict

from infrastructure.observability import log_structured

logger = logging.getLogger(__name__)


class WorkflowRouter:
    """Routes diagnostics tasks to target workflow handlers."""

    def __init__(
        self,
        *,
        two_tank_topologies: set[str],
        three_tank_topologies: set[str],
        cycle_start_workflows: set[str],
        execute_two_tank: Callable[..., Awaitable[Dict[str, Any]]],
        execute_three_tank: Callable[..., Awaitable[Dict[str, Any]]],
        execute_cycle_start: Callable[..., Awaitable[Dict[str, Any]]],
        execute_default: Callable[..., Awaitable[Dict[str, Any]]],
    ) -> None:
        self._two_tank_topologies = two_tank_topologies
        self._three_tank_topologies = three_tank_topologies
        self._cycle_start_workflows = cycle_start_workflows
        self._execute_two_tank = execute_two_tank
        self._execute_three_tank = execute_three_tank
        self._execute_cycle_start = execute_cycle_start
        self._execute_default = execute_default

    async def route_diagnostics(
        self,
        *,
        zone_id: int,
        payload: Dict[str, Any],
        context: Dict[str, Any],
        decision: Any,
        workflow: str,
        topology: str,
        task_type: str,
    ) -> Dict[str, Any]:
        started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        normalized_topology = str(topology or "").strip().lower()
        normalized_workflow = str(workflow or "").strip().lower()

        if normalized_topology in self._two_tank_topologies:
            route = "two_tank"
            handler = self._execute_two_tank
        elif normalized_topology in self._three_tank_topologies:
            route = "three_tank"
            handler = self._execute_three_tank
        elif normalized_workflow in self._cycle_start_workflows:
            route = "cycle_start"
            handler = self._execute_cycle_start
        else:
            route = "default"
            handler = self._execute_default

        log_structured(
            logger,
            logging.INFO,
            "Diagnostics workflow route selected",
            component="workflow_router",
            zone_id=zone_id,
            task_id=str(context.get("task_id") or "") or None,
            task_type=task_type,
            workflow=normalized_workflow or None,
            decision="run",
            reason_code="route_selected",
            result_status="success",
            correlation_id=str(context.get("correlation_id") or "") or None,
            started_at=started_at,
            route=route,
            topology=normalized_topology or None,
        )
        return await handler(
            zone_id=zone_id,
            payload=payload,
            context=context,
            decision=decision,
        )
