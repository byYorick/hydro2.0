"""Полив: решение, подача раствора в зону и останов по времени или низкому уровню."""

from __future__ import annotations

from ae3lite.application.handlers.await_ready import AwaitReadyHandler
from ae3lite.application.handlers.decision_gate import DecisionGateHandler
from ae3lite.application.handlers.irrigation_check import IrrigationCheckHandler
from ae3lite.hydraulics.ownership import IRRIGATION, IRRIGATION_STAGES
from ae3lite.hydraulics.system import HydraulicSystem

IRRIGATION_SYSTEM = HydraulicSystem(
    system_id=IRRIGATION,
    watches=(
        "zone_workflow_phase",
        "irr_state",
        "level_solution_min",
        "soil_moisture",
        "IRRIGATION_SOLUTION_LOW",
        "EMERGENCY_STOP_ACTIVATED",
    ),
    controls=(
        "valve_solution_supply",
        "valve_irrigation",
        "pump_main",
    ),
    stages=IRRIGATION_STAGES,
    handlers={
        "await_ready": AwaitReadyHandler,
        "decision_gate": DecisionGateHandler,
        "irrigation_check": IrrigationCheckHandler,
    },
    kind="flow",
    scope="zone",
    required_node_types=frozenset({"irrig"}),
    handler_deps={
        "await_ready": ("task_repository",),
        "decision_gate": ("task_repository", "decision_controller"),
        "irrigation_check": ("task_repository",),
    },
)
