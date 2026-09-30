"""Подготовка и хранение раствора: чистый бак, бак раствора, рециркуляция, долив."""

from __future__ import annotations

from ae3lite.application.handlers.clean_fill import CleanFillCheckHandler
from ae3lite.application.handlers.prepare_recirc import PrepareRecircCheckHandler
from ae3lite.application.handlers.prepare_recirc_window import PrepareRecircWindowHandler
from ae3lite.application.handlers.solution_change import (
    SolutionChangeCompleteHandler,
    SolutionChangeOperatorGateHandler,
    SolutionDrainCheckHandler,
)
from ae3lite.application.handlers.solution_fill import SolutionFillCheckHandler
from ae3lite.application.handlers.solution_topup import (
    SolutionTopupCheckHandler,
    SolutionTopupCompleteHandler,
    SolutionTopupGuardHandler,
)
from ae3lite.application.handlers.startup import StartupHandler
from ae3lite.hydraulics.ownership import SOLUTION, SOLUTION_STAGES
from ae3lite.hydraulics.system import HydraulicSystem

SOLUTION_SYSTEM = HydraulicSystem(
    system_id=SOLUTION,
    watches=(
        "level_clean_min",
        "level_clean_max",
        "level_solution_min",
        "level_solution_max",
        "CLEAN_FILL_COMPLETED",
        "CLEAN_FILL_SOURCE_EMPTY",
        "SOLUTION_FILL_COMPLETED",
    ),
    controls=(
        "valve_clean_fill",
        "valve_clean_supply",
        "valve_solution_fill",
        "valve_drain",
        "pump_main",
    ),
    stages=SOLUTION_STAGES,
    handlers={
        "startup": StartupHandler,
        "clean_fill": CleanFillCheckHandler,
        "solution_fill": SolutionFillCheckHandler,
        "solution_topup_guard": SolutionTopupGuardHandler,
        "solution_topup_check": SolutionTopupCheckHandler,
        "solution_topup_complete": SolutionTopupCompleteHandler,
        "solution_change_gate": SolutionChangeOperatorGateHandler,
        "solution_drain_check": SolutionDrainCheckHandler,
        "solution_change_complete": SolutionChangeCompleteHandler,
        "prepare_recirc": PrepareRecircCheckHandler,
        "prepare_recirc_window": PrepareRecircWindowHandler,
    },
    kind="flow",
    scope="zone",
    required_node_types=frozenset({"irrig", "ph", "ec"}),
    handler_deps={
        "prepare_recirc": ("task_repository", "pid_state_repository"),
        "prepare_recirc_window": ("alert_repository",),
    },
)
