"""Доменные сервисы AE3-Lite."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .cycle_start_planner import CycleStartPlanner


def __getattr__(name: str) -> Any:
    if name == "CycleStartPlanner":
        from .cycle_start_planner import CycleStartPlanner

        return CycleStartPlanner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)


__all__ = ["CycleStartPlanner"]
