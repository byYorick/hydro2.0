"""Модульные solver-ы зоны для Digital Twin.

Phase A: target-driven solver-ы, эквивалентные legacy моделям из `models.py`.
Phase B: command-driven dynamics через actuator_solver + channel_roles.
"""
from .actuator_solver import (
    ActuatorEffect,
    ActuatorSolver,
    ActuatorState,
    ChemDoseEffect,
)
from .channel_roles import KNOWN_ROLES, resolve_channel_role
from .chem_solver import ChemSolver
from .climate_solver import ClimateSolver
from .state import ChemState, ClimateState, SubstrateState, TankState, ZoneState
from .substrate_solver import SubstrateSolver
from .tank_solver import TankSolver

__all__ = [
    "ZoneState",
    "TankState",
    "ChemState",
    "ClimateState",
    "SubstrateState",
    "TankSolver",
    "ChemSolver",
    "ClimateSolver",
    "SubstrateSolver",
    "ActuatorSolver",
    "ActuatorState",
    "ActuatorEffect",
    "ChemDoseEffect",
    "KNOWN_ROLES",
    "resolve_channel_role",
]
