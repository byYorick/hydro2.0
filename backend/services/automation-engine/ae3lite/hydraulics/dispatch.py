"""Проверка, что стадию исполняет модуль, которому она принадлежит."""

from __future__ import annotations

from typing import Any

from ae3lite.domain.errors import ErrorCodes, TaskExecutionError
from ae3lite.hydraulics.ownership import CORRECTION_HOST_STAGES
from ae3lite.hydraulics.registry import EXECUTOR_HANDLERS, HYDRAULIC_SYSTEMS

_EXECUTOR_HANDLER_KEYS = frozenset(EXECUTOR_HANDLERS) | {"ready"}

_HANDLERS_BY_SYSTEM: dict[str, frozenset[str]] = {
    system.system_id: frozenset(system.handlers)
    for system in HYDRAULIC_SYSTEMS
}


def assert_stage_dispatch(stage_def: Any, *, correction_active: bool) -> None:
    """Исполнитель пускает handler только системы-владельца стадии.

    Пустой ``system`` — diagnostics вне two_tank, проверку не включаем.
    ``command`` / ``manual_hold`` / ``ready`` общие для всех систем.
    """
    system = str(getattr(stage_def, "system", "") or "").strip()
    handler = str(getattr(stage_def, "handler", "") or "").strip()
    stage = str(getattr(stage_def, "name", "") or "").strip()
    if correction_active:
        if stage not in CORRECTION_HOST_STAGES:
            raise TaskExecutionError(
                ErrorCodes.AE3_STAGE_SYSTEM_MISMATCH,
                f"Коррекция запущена на стадии {stage!r}, которая её не принимает",
            )
        return
    if not system:
        return
    if handler in _EXECUTOR_HANDLER_KEYS:
        return
    allowed = _HANDLERS_BY_SYSTEM.get(system, frozenset())
    if handler not in allowed:
        raise TaskExecutionError(
            ErrorCodes.AE3_STAGE_SYSTEM_MISMATCH,
            f"Стадия {stage!r} системы {system!r} не может исполняться handler {handler!r}",
        )
