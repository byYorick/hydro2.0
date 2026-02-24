"""Common callable type aliases for two-tank phase starters."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

DispatchTwoTankCommandPlanFn = Callable[..., Awaitable[Dict[str, Any]]]
EnqueueTwoTankCheckFn = Callable[..., Awaitable[Dict[str, Any]]]
CompensateStartEnqueueFailureFn = Callable[..., Awaitable[Dict[str, Any]]]
EmitTaskEventFn = Callable[..., Awaitable[None]]
TwoTankSafetyGuardsEnabledFn = Callable[[], bool]
DispatchSensorModeFn = Callable[..., Awaitable[Dict[str, Any]]]
MergeDispatchResultsFn = Callable[..., Dict[str, Any]]
UpdateWorkflowPhaseFn = Callable[..., Awaitable[None]]

__all__ = [
    "CompensateStartEnqueueFailureFn",
    "DispatchSensorModeFn",
    "DispatchTwoTankCommandPlanFn",
    "EmitTaskEventFn",
    "EnqueueTwoTankCheckFn",
    "MergeDispatchResultsFn",
    "TwoTankSafetyGuardsEnabledFn",
    "UpdateWorkflowPhaseFn",
]
