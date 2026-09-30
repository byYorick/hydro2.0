"""Свет зоны: короткий tick, без длинного гидравлического графа.

Климат теплицы — тот же вид ``tick``, но scope ``greenhouse`` и свои таблицы
lease. В zone FSM он не входит.
"""

from __future__ import annotations

from ae3lite.hydraulics.system import HydraulicSystem

LIGHTING_SYSTEM = HydraulicSystem(
    system_id="lighting",
    watches=("lighting",),
    controls=("light_main",),
    stages=frozenset({"apply"}),
    handlers={},
    kind="tick",
    scope="zone",
    required_node_types=frozenset(),
)

GREENHOUSE_CLIMATE_SYSTEM = HydraulicSystem(
    system_id="climate",
    watches=("temperature", "humidity"),
    controls=("vent_roof",),
    stages=frozenset(),
    handlers={},
    kind="tick",
    scope="greenhouse",
)
