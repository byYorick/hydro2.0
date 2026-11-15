"""GetZoneAutomationStateUseCase coordination: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from ae3lite.application.services.zone_state_shared import logger
from common.observability_thresholds import load_system_observability_thresholds


@dataclass(frozen=True)
class ZoneStateCoordinationPorts:
    build_state: Callable[..., Awaitable[Any]]
    build_workflow_state: Callable[..., Awaitable[Any]]
    fetch_fn: Callable[..., Any]
    fetch_zone_nodes_diag: Callable[..., Awaitable[Any]]
    fetch_zone_telemetry: Callable[..., Awaitable[Any]]
    merge_last_failed_task_into_workflow_view: Callable[..., Any]
    normalize_solution_tank_guard: Callable[..., Any]
    now: Callable[..., Any]
    should_prefer_workflow_state: Callable[..., Any]
    startup_reset_guard_use_case: Callable[[], Any]
    task_repository: Callable[[], Any]
    workflow_repository: Callable[[], Any]
    workflow_state_is_stale: Callable[..., Any]


class ZoneStateCoordination:
    def __init__(self, ports: ZoneStateCoordinationPorts) -> None:
        self._ports = ports

    async def run(self, *, zone_id: int) -> dict[str, Any]:
        # Сначала пробуем активную задачу, затем последнюю terminal-задачу
        task: Optional[Any] = await self._ports.task_repository().get_active_for_zone(zone_id=zone_id)
        workflow_state: Optional[Any] = None
        last_task: Optional[Any] = None
        solution_tank_guard = None
        if task is None and self._ports.startup_reset_guard_use_case() is not None:
            try:
                guard_result = await self._ports.startup_reset_guard_use_case().run(
                    zone_id=zone_id, now=self._ports.now()
                )
                solution_tank_guard = self._ports.normalize_solution_tank_guard(guard_result)
            except Exception:
                logger.warning(
                    "AE3 automation state: startup reset guard failed for zone_id=%s",
                    zone_id,
                    exc_info=True,
                )
        if task is None and self._ports.workflow_repository() is not None:
            try:
                workflow_state = await self._ports.workflow_repository().get(zone_id=zone_id)
            except Exception:
                logger.warning(
                    "AE3 automation state: workflow read failed for zone_id=%s",
                    zone_id,
                    exc_info=True,
                )
                workflow_state = None
        if task is None:
            last_task = await self._ports.task_repository().get_last_for_zone(zone_id=zone_id)

        # Подтянуть дополнительные данные; последовательного чтения здесь достаточно
        transitions: list[dict] = []
        if task is not None:
            try:
                transitions = await self._ports.task_repository().get_transitions_for_task(task_id=task.id)
            except Exception:
                logger.warning(
                    "AE3 automation state: transition read failed for zone_id=%s task_id=%s",
                    zone_id,
                    getattr(task, "id", None),
                    exc_info=True,
                )

        telemetry, telemetry_fetch_ok = await self._ports.fetch_zone_telemetry(zone_id=zone_id)
        node_rows = await self._ports.fetch_zone_nodes_diag(zone_id=zone_id)
        observability_thresholds = await load_system_observability_thresholds(self._ports.fetch_fn)
        if (
            task is None
            and self._ports.should_prefer_workflow_state(workflow_state)
            and not self._ports.workflow_state_is_stale(
                workflow_state=workflow_state,
                last_task=last_task,
            )
        ):
            built = await self._ports.build_workflow_state(
                zone_id=zone_id,
                workflow_state=workflow_state,
                telemetry=telemetry,
                telemetry_fetch_ok=telemetry_fetch_ok,
                solution_tank_guard=solution_tank_guard,
                node_rows=node_rows,
                observability_thresholds=observability_thresholds,
            )
            return self._ports.merge_last_failed_task_into_workflow_view(built, last_task, workflow_state)
        if task is None:
            task = last_task

        return await self._ports.build_state(
            zone_id=zone_id,
            task=task,
            transitions=transitions,
            telemetry=telemetry,
            telemetry_fetch_ok=telemetry_fetch_ok,
            solution_tank_guard=solution_tank_guard,
            workflow_state=workflow_state,
            node_rows=node_rows,
            observability_thresholds=observability_thresholds,
        )
