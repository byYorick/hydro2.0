"""Типизированный Protocol для executor context, передаваемого в workflow-функции."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable


@runtime_checkable
class WorkflowExecutorProtocol(Protocol):
    """Интерфейс, который ожидают two-tank workflow-функции от executor'а.

    Workflow-функции (execute_two_tank_startup_workflow_core и т.д.) принимают
    `executor: WorkflowExecutorProtocol` как первый аргумент вместо `self`.
    Protocol позволяет mypy/pyright проверять корректность вызовов без
    связывания workflow-логики с конкретным классом SchedulerTaskExecutor.
    """

    # --------------------------------------------------------------------------
    # Инфраструктурные атрибуты
    # --------------------------------------------------------------------------

    fetch_fn: Any  # callable: async (sql, *args) -> List[Row]
    command_gateway: Any  # CommandBus-like, имеет метод publish_command(...)

    # --------------------------------------------------------------------------
    # Утилитарные методы (синхронные)
    # --------------------------------------------------------------------------

    def _resolve_int(self, value: Any, default: int, minimum: int) -> int: ...

    def _normalize_two_tank_workflow(self, payload: Dict[str, Any]) -> str: ...

    def _resolve_two_tank_runtime_config(self, payload: Dict[str, Any]) -> Dict[str, Any]: ...

    def _extract_topology(self, payload: Dict[str, Any]) -> str: ...

    def _telemetry_freshness_enforce(self) -> bool: ...

    def _two_tank_safety_guards_enabled(self) -> bool: ...

    def _log_two_tank_safety_guard(self, *args: Any, **kwargs: Any) -> None: ...

    def _build_two_tank_stop_not_confirmed_result(self, **kwargs: Any) -> Dict[str, Any]: ...

    # --------------------------------------------------------------------------
    # Асинхронные методы — infrastructure / persistence
    # --------------------------------------------------------------------------

    async def _emit_task_event(
        self,
        *,
        zone_id: int,
        task_type: str,
        context: Dict[str, Any],
        event_type: str,
        payload: Dict[str, Any],
    ) -> None: ...

    async def _update_zone_workflow_phase(
        self,
        *,
        zone_id: int,
        workflow_phase: str,
        **kwargs: Any,
    ) -> None: ...

    async def _get_zone_nodes(
        self,
        zone_id: int,
        node_types: Tuple[str, ...],
    ) -> List[Dict[str, Any]]: ...

    async def _check_required_nodes_online(
        self,
        zone_id: int,
        required_types: Tuple[str, ...],
    ) -> Dict[str, Any]: ...

    async def _find_zone_event_since(self, **kwargs: Any) -> Optional[Dict[str, Any]]: ...

    async def _read_level_switch(self, **kwargs: Any) -> Optional[float]: ...

    # --------------------------------------------------------------------------
    # Асинхронные методы — two-tank command dispatch
    # --------------------------------------------------------------------------

    async def _dispatch_two_tank_command_plan(
        self,
        *,
        zone_id: int,
        command_plan: List[Any],
        context: Dict[str, Any],
        decision: Any,
    ) -> Dict[str, Any]: ...

    async def _start_two_tank_clean_fill(self, **kwargs: Any) -> Dict[str, Any]: ...

    async def _start_two_tank_solution_fill(self, **kwargs: Any) -> Dict[str, Any]: ...

    async def _start_two_tank_prepare_recirculation(self, **kwargs: Any) -> Dict[str, Any]: ...

    async def _start_two_tank_irrigation_recovery(self, **kwargs: Any) -> Dict[str, Any]: ...

    async def _merge_with_sensor_mode_deactivate(self, **kwargs: Any) -> Dict[str, Any]: ...

    async def _enqueue_two_tank_check(self, **kwargs: Any) -> Any: ...

    async def _evaluate_ph_ec_targets(self, **kwargs: Any) -> Any: ...


__all__ = ["WorkflowExecutorProtocol"]
