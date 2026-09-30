"""Коррекция pH/EC: вложенная машина доза → пауза → окно проб.

Своих стадий в графе нет. Её запускает check-стадия подготовки или полива,
исполнитель на это время отдаёт тик только этому модулю.
``valve_clean_supply`` принадлежит хранению раствора; коррекция берёт его
на один импульс разбавления при перелёте EC на рециркуляции.
"""

from __future__ import annotations

from ae3lite.application.handlers.correction import CorrectionHandler
from ae3lite.hydraulics.ownership import CORRECTION, CORRECTION_HOST_STAGES
from ae3lite.hydraulics.system import HydraulicSystem

CORRECTION_SYSTEM = HydraulicSystem(
    system_id=CORRECTION,
    watches=(
        "PH",
        "EC",
        "pid_state",
    ),
    controls=(
        "dose_ec",
        "dose_ph",
    ),
    borrows=("valve_clean_supply",),
    stages=frozenset(),
    hosted_by_stages=CORRECTION_HOST_STAGES,
    handlers={
        "correction": CorrectionHandler,
    },
    kind="hosted",
    scope="zone",
    required_node_types=frozenset({"ph", "ec"}),
    handler_deps={
        "correction": ("planner", "pid_state_repository"),
    },
)
