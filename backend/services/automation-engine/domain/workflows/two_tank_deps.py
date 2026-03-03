"""Dependency container for two-tank workflow functions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from domain.policies.two_tank_safety_config import TwoTankSafetyConfig


def _missing_sync(name: str) -> Callable[..., Any]:
    def _raise(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(f"Missing two-tank dependency: {name}")

    return _raise


def _missing_async(name: str) -> Callable[..., Awaitable[Any]]:
    async def _raise(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(f"Missing two-tank dependency: {name}")

    return _raise


class _MissingCommandGateway:
    async def publish_controller_command(self, *args: Any, **kwargs: Any) -> bool:
        raise RuntimeError("Missing two-tank dependency: command_gateway.publish_controller_command")


@dataclass(frozen=True)
class TwoTankDeps:
    """All dependencies needed by two-tank workflow functions."""

    zone_id: int

    # Infrastructure
    fetch_fn: Any = field(default_factory=lambda: _missing_async("fetch_fn"))
    command_gateway: Any = field(default_factory=_MissingCommandGateway)

    # Command dispatch
    dispatch_two_tank_command_plan: Callable[..., Awaitable[Dict[str, Any]]] = field(
        default_factory=lambda: _missing_async("dispatch_two_tank_command_plan")
    )

    # Events / state
    emit_task_event: Callable[..., Awaitable[None]] = field(default_factory=lambda: _missing_async("emit_task_event"))
    update_zone_workflow_phase: Callable[..., Awaitable[None]] = field(
        default_factory=lambda: _missing_async("update_zone_workflow_phase")
    )
    find_zone_event_since: Callable[..., Awaitable[Optional[Dict[str, Any]]]] = field(
        default_factory=lambda: _missing_async("find_zone_event_since")
    )

    # Node queries
    check_required_nodes_online: Callable[..., Awaitable[Dict[str, Any]]] = field(
        default_factory=lambda: _missing_async("check_required_nodes_online")
    )
    get_zone_nodes: Callable[..., Awaitable[List[Dict[str, Any]]]] = field(
        default_factory=lambda: _missing_async("get_zone_nodes")
    )

    # Telemetry
    read_level_switch: Callable[..., Awaitable[Dict[str, Any]]] = field(
        default_factory=lambda: _missing_async("read_level_switch")
    )
    evaluate_ph_ec_targets: Callable[..., Awaitable[Dict[str, Any]]] = field(
        default_factory=lambda: _missing_async("evaluate_ph_ec_targets")
    )

    # Phase starters
    start_two_tank_clean_fill: Callable[..., Awaitable[Dict[str, Any]]] = field(
        default_factory=lambda: _missing_async("start_two_tank_clean_fill")
    )
    start_two_tank_solution_fill: Callable[..., Awaitable[Dict[str, Any]]] = field(
        default_factory=lambda: _missing_async("start_two_tank_solution_fill")
    )
    start_two_tank_prepare_recirculation: Callable[..., Awaitable[Dict[str, Any]]] = field(
        default_factory=lambda: _missing_async("start_two_tank_prepare_recirculation")
    )
    start_two_tank_irrigation_recovery: Callable[..., Awaitable[Dict[str, Any]]] = field(
        default_factory=lambda: _missing_async("start_two_tank_irrigation_recovery")
    )
    merge_with_sensor_mode_deactivate: Callable[..., Awaitable[Dict[str, Any]]] = field(
        default_factory=lambda: _missing_async("merge_with_sensor_mode_deactivate")
    )
    enqueue_two_tank_check: Callable[..., Awaitable[Dict[str, Any]]] = field(
        default_factory=lambda: _missing_async("enqueue_two_tank_check")
    )

    # Utilities
    resolve_int: Callable[[Any, int, int], int] = field(default_factory=lambda: _missing_sync("resolve_int"))
    normalize_two_tank_workflow: Callable[[Dict[str, Any]], str] = field(
        default_factory=lambda: _missing_sync("normalize_two_tank_workflow")
    )
    resolve_two_tank_runtime_config: Callable[[Dict[str, Any]], Dict[str, Any]] = field(
        default_factory=lambda: _missing_sync("resolve_two_tank_runtime_config")
    )
    extract_topology: Callable[[Dict[str, Any]], str] = field(default_factory=lambda: _missing_sync("extract_topology"))
    telemetry_freshness_enforce: Callable[[], bool] = field(
        default_factory=lambda: _missing_sync("telemetry_freshness_enforce")
    )
    safety_config: TwoTankSafetyConfig = field(default_factory=TwoTankSafetyConfig.production)
    log_two_tank_safety_guard: Callable[..., None] = field(
        default_factory=lambda: _missing_sync("log_two_tank_safety_guard")
    )
    build_two_tank_stop_not_confirmed_result: Callable[..., Dict[str, Any]] = field(
        default_factory=lambda: _missing_sync("build_two_tank_stop_not_confirmed_result")
    )

    # Compatibility wrappers for existing helper modules.
    def _resolve_int(self, value: Any, default: int, minimum: int) -> int:
        return self.resolve_int(value, default, minimum)

    def _normalize_two_tank_workflow(self, payload: Dict[str, Any]) -> str:
        return self.normalize_two_tank_workflow(payload)

    def _resolve_two_tank_runtime_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.resolve_two_tank_runtime_config(payload)

    def _extract_topology(self, payload: Dict[str, Any]) -> str:
        return self.extract_topology(payload)

    def _telemetry_freshness_enforce(self) -> bool:
        return bool(self.telemetry_freshness_enforce())

    def _two_tank_safety_guards_enabled(self) -> bool:
        return bool(self.safety_config.stop_confirmation_required)

    def _log_two_tank_safety_guard(self, *args: Any, **kwargs: Any) -> None:
        self.log_two_tank_safety_guard(*args, **kwargs)

    def _build_two_tank_stop_not_confirmed_result(self, **kwargs: Any) -> Dict[str, Any]:
        return self.build_two_tank_stop_not_confirmed_result(**kwargs)

    async def _emit_task_event(self, **kwargs: Any) -> None:
        await self.emit_task_event(**kwargs)

    async def _update_zone_workflow_phase(self, **kwargs: Any) -> None:
        await self.update_zone_workflow_phase(**kwargs)

    async def _find_zone_event_since(self, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return await self.find_zone_event_since(**kwargs)

    async def _check_required_nodes_online(self, zone_id: int, required_types: Any) -> Dict[str, Any]:
        return await self.check_required_nodes_online(zone_id, required_types)

    async def _get_zone_nodes(self, zone_id: int, node_types: Any) -> List[Dict[str, Any]]:
        return await self.get_zone_nodes(zone_id, node_types)

    async def _read_level_switch(self, **kwargs: Any) -> Dict[str, Any]:
        return await self.read_level_switch(**kwargs)

    async def _evaluate_ph_ec_targets(self, **kwargs: Any) -> Dict[str, Any]:
        return await self.evaluate_ph_ec_targets(**kwargs)

    async def _dispatch_two_tank_command_plan(self, **kwargs: Any) -> Dict[str, Any]:
        return await self.dispatch_two_tank_command_plan(**kwargs)

    async def _start_two_tank_clean_fill(self, **kwargs: Any) -> Dict[str, Any]:
        return await self.start_two_tank_clean_fill(**kwargs)

    async def _start_two_tank_solution_fill(self, **kwargs: Any) -> Dict[str, Any]:
        return await self.start_two_tank_solution_fill(**kwargs)

    async def _start_two_tank_prepare_recirculation(self, **kwargs: Any) -> Dict[str, Any]:
        return await self.start_two_tank_prepare_recirculation(**kwargs)

    async def _start_two_tank_irrigation_recovery(self, **kwargs: Any) -> Dict[str, Any]:
        return await self.start_two_tank_irrigation_recovery(**kwargs)

    async def _merge_with_sensor_mode_deactivate(self, **kwargs: Any) -> Dict[str, Any]:
        return await self.merge_with_sensor_mode_deactivate(**kwargs)

    async def _enqueue_two_tank_check(self, **kwargs: Any) -> Dict[str, Any]:
        return await self.enqueue_two_tank_check(**kwargs)


__all__ = ["TwoTankDeps"]
