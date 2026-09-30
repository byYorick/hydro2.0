"""Именованная установка зоны: граф стадий, узлы и входы по task_type.

Граф остаётся кодом. Оператор включает подсистемы флагами профиля,
а не задаёт рёбра workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from ae3lite.application.services.workflow_topology import StageDef


@dataclass(frozen=True)
class TopologyPack:
    """Дескриптор одной topology.

    ``two_tank`` и ``two_tank_drip_substrate_trays`` могут делить один граф
    и отличаться привязкой полива. Новая установка — новый дескриптор.
    """

    id: str
    stages: Mapping[str, StageDef]
    required_node_types: frozenset[str]
    required_subsystems: tuple[str, ...]
    optional_subsystems: tuple[str, ...]
    entry_by_task_type: Mapping[str, str]
    command_plan_keys: frozenset[str]
    irrigation_binding: str = ""
    scope: str = "zone"
    plan_profile: str = "two_tank"
    execution_mode: str = "workflow"
    check_stage_ownership: bool = True
    fail_safe_on_flow: bool = False
    tracks_correction_authority: bool = False
    retries_missing_actuators: bool = False


TWO_TANK_COMMAND_PLAN_KEYS: frozenset[str] = frozenset(
    {
        "irrigation_start",
        "irrigation_pump_stop",
        "irrigation_stop",
        "clean_fill_start",
        "clean_fill_stop",
        "solution_fill_start",
        "solution_fill_stop",
        "prepare_recirculation_start",
        "prepare_recirculation_stop",
        "recirc_dilute_start",
        "recirc_dilute_stop",
        "solution_drain_start",
        "solution_drain_stop",
    }
)

SINGLE_TANK_COMMAND_PLAN_KEYS: frozenset[str] = TWO_TANK_COMMAND_PLAN_KEYS - {
    "clean_fill_start",
    "clean_fill_stop",
}

HYDRAULIC_ENTRY_BY_TASK_TYPE: Mapping[str, str] = {
    "cycle_start": "startup",
    "irrigation_start": "await_ready",
    "solution_topup": "solution_topup_guard",
    "solution_change": "await_operator_drain_confirm",
}


def subsystem_enabled_flags(snapshot: object) -> dict[str, bool]:
    """Явные ``subsystems.<id>.enabled`` из targets. Отсутствие ключа — не флаг."""
    targets = getattr(snapshot, "targets", None)
    if not isinstance(targets, Mapping):
        return {}
    extensions = targets.get("extensions")
    if not isinstance(extensions, Mapping):
        return {}
    subsystems = extensions.get("subsystems")
    if not isinstance(subsystems, Mapping):
        return {}
    flags: dict[str, bool] = {}
    for key, node in subsystems.items():
        if isinstance(node, Mapping) and "enabled" in node:
            flags[str(key)] = bool(node.get("enabled"))
    return flags
