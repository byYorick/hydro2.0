"""Solver резервуаров (clean/solution баки).

Phase A: mass balance с потоками от actuators (входы пока 0 по умолчанию).
Phase B (план): ActuatorSolver формирует flows из cmd событий AE3.

Уровни (`level_clean_min/max`, `level_solution_min/max`) триггерятся по
порогам объёма и зеркалят семантику `application/level_monitor.py` в AE3
(см. `doc_ai/04_BACKEND_CORE/AE3_IRR_LEVEL_SWITCH_EVENT_CONTRACT.md`).
"""
from dataclasses import replace
from typing import Dict, Optional

from .state import TankState


class TankSolver:
    """Solver двух резервуаров с потоками."""

    DEFAULT_PARAMS: Dict[str, float] = {
        "clean_threshold_min_l": 10.0,
        "clean_threshold_max_l": 180.0,
        "solution_threshold_min_l": 10.0,
        "solution_threshold_max_l": 180.0,
        "evaporation_l_per_hour": 0.05,
    }

    def __init__(self, params: Optional[Dict[str, float]] = None) -> None:
        merged = dict(self.DEFAULT_PARAMS)
        if params:
            for key, value in params.items():
                if value is None:
                    continue
                try:
                    merged[key] = float(value)
                except (TypeError, ValueError):
                    continue
        self.params = merged

    def step(
        self,
        state: TankState,
        flows: Optional[Dict[str, float]] = None,
        dt_hours: float = 0.0,
    ) -> TankState:
        flows = flows or {}
        clean_in = float(flows.get("clean_in_l_per_hour", 0.0))
        clean_to_solution = float(flows.get("clean_to_solution_l_per_hour", 0.0))
        dose_in = float(flows.get("dose_in_l_per_hour", 0.0))
        irrigation_out = float(flows.get("irrigation_out_l_per_hour", 0.0))
        evap = self.params["evaporation_l_per_hour"]

        new_clean = max(
            0.0,
            min(
                state.clean_capacity_l,
                state.clean_volume_l
                + (clean_in - clean_to_solution) * dt_hours,
            ),
        )
        new_solution = max(
            0.0,
            min(
                state.solution_capacity_l,
                state.solution_volume_l
                + (clean_to_solution + dose_in - irrigation_out - evap) * dt_hours,
            ),
        )

        return replace(
            state,
            clean_volume_l=new_clean,
            solution_volume_l=new_solution,
            level_clean_min=new_clean >= self.params["clean_threshold_min_l"],
            level_clean_max=new_clean >= self.params["clean_threshold_max_l"],
            level_solution_min=new_solution >= self.params["solution_threshold_min_l"],
            level_solution_max=new_solution >= self.params["solution_threshold_max_l"],
        )
