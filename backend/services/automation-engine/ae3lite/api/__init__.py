"""Публичная API-поверхность AE3-Lite v1."""

from .compat_endpoints import (
    bind_start_cycle_route,
    bind_start_irrigation_route,
    bind_start_lighting_tick_route,
    bind_start_solution_topup_route,
)
from .greenhouse_climate_compat import bind_greenhouse_climate_tick_route
from .internal_endpoints import bind_internal_task_route

__all__ = [
    "bind_start_cycle_route",
    "bind_start_irrigation_route",
    "bind_start_lighting_tick_route",
    "bind_start_solution_topup_route",
    "bind_internal_task_route",
    "bind_greenhouse_climate_tick_route",
]
