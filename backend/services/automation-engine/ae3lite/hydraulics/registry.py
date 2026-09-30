"""Сборка трёх систем в один исполнитель гидравлики."""

from __future__ import annotations

from typing import Mapping

from ae3lite.application.handlers.command import CommandHandler
from ae3lite.application.handlers.manual_hold import ManualHoldHandler
from ae3lite.hydraulics.correction import CORRECTION_SYSTEM
from ae3lite.hydraulics.irrigation import IRRIGATION_SYSTEM
from ae3lite.hydraulics.lighting import GREENHOUSE_CLIMATE_SYSTEM, LIGHTING_SYSTEM
from ae3lite.hydraulics.solution import SOLUTION_SYSTEM
from ae3lite.hydraulics.system import HydraulicSystem

HYDRAULIC_SYSTEMS: tuple[HydraulicSystem, ...] = (
    SOLUTION_SYSTEM,
    IRRIGATION_SYSTEM,
    CORRECTION_SYSTEM,
)

# Tick-модули не добавляют handler-ключи zone-графа.
TICK_SYSTEMS: tuple[HydraulicSystem, ...] = (
    LIGHTING_SYSTEM,
    GREENHOUSE_CLIMATE_SYSTEM,
)

ALL_SYSTEMS: tuple[HydraulicSystem, ...] = HYDRAULIC_SYSTEMS + TICK_SYSTEMS

# Общий прогон команд и пауза потока. Это не четвёртая установка.
EXECUTOR_HANDLERS: dict[str, type] = {
    "command": CommandHandler,
    "manual_hold": ManualHoldHandler,
}


def hydraulic_handler_classes() -> dict[str, type]:
    """Ключ handler → класс. Один ключ принадлежит одному модулю."""
    classes: dict[str, type] = dict(EXECUTOR_HANDLERS)
    for system in HYDRAULIC_SYSTEMS:
        for key, handler_cls in system.handlers.items():
            if key in classes:
                owner = _owner_of_handler(key)
                raise RuntimeError(
                    f"Handler {key!r} заявлен и модулем {system.system_id}, и {owner}"
                )
            classes[key] = handler_cls
    return classes


def _owner_of_handler(key: str) -> str:
    if key in EXECUTOR_HANDLERS:
        return "executor"
    for system in HYDRAULIC_SYSTEMS:
        if key in system.handlers:
            return system.system_id
    return "unknown"


def system_by_id() -> Mapping[str, HydraulicSystem]:
    return {system.system_id: system for system in ALL_SYSTEMS}


def handler_dependency_map() -> dict[str, tuple[str, ...]]:
    """Ключ handler → имена зависимостей, которые объявил модуль-владелец."""
    deps: dict[str, tuple[str, ...]] = {}
    for system in ALL_SYSTEMS:
        for key, names in system.handler_deps.items():
            if key in deps:
                raise RuntimeError(
                    f"Зависимости handler {key!r} заявлены повторно модулем {system.system_id}"
                )
            deps[key] = tuple(names)
    return deps
