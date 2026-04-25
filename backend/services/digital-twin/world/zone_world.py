"""ZoneWorld — оркестратор всех solver-ов зоны.

Phase A: target-driven — solver-ы получают targets текущей фазы рецепта.
Phase B: command-driven — ActuatorSolver принимает cmd-события (через
`CommandRouter`), формирует flows для TankSolver и dose effects для
ChemSolver. ZoneWorld объединяет оба режима: targets + flows + dose.
"""
import logging
from typing import Any, Dict, Optional

from solvers import (
    ActuatorEffect,
    ActuatorSolver,
    ChemSolver,
    ChemState,
    ClimateSolver,
    ClimateState,
    SubstrateSolver,
    SubstrateState,
    TankSolver,
    TankState,
    ZoneState,
)

logger = logging.getLogger(__name__)


class ZoneWorld:
    """Объединяет solver-ы и шагает по dt_hours общим временем."""

    def __init__(
        self,
        params_by_group: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> None:
        params = params_by_group or {}
        self.tank_solver = TankSolver(params.get("tank"))
        self.chem_solver = ChemSolver(
            ph_params=params.get("ph"),
            ec_params=params.get("ec"),
        )
        self.climate_solver = ClimateSolver(params.get("climate"))
        self.substrate_solver = SubstrateSolver(params.get("substrate"))
        self.actuator_solver = ActuatorSolver(params.get("actuator"))

    @staticmethod
    def initial_state(initial: Optional[Dict[str, Any]] = None) -> ZoneState:
        """Сборка ZoneState из плоского словаря initial_state из scenario."""
        initial = initial or {}

        def to_float(value: Any, default: float) -> float:
            if value is None:
                return default
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        return ZoneState(
            tank=TankState(
                water_temp_c=to_float(initial.get("temp_water"), 20.0),
            ),
            chem=ChemState(
                ph=to_float(initial.get("ph"), 6.0),
                ec=to_float(initial.get("ec"), 1.2),
            ),
            climate=ClimateState(
                temp_air_c=to_float(initial.get("temp_air"), 22.0),
                humidity_air_pct=to_float(initial.get("humidity_air"), 60.0),
                co2_ppm=to_float(initial.get("co2"), 400.0),
            ),
            substrate=SubstrateState(
                water_content_pct=to_float(initial.get("water_content"), 60.0),
            ),
        )

    def step(
        self,
        state: ZoneState,
        targets: Dict[str, float],
        dt_hours: float,
        flows: Optional[Dict[str, float]] = None,
    ) -> ZoneState:
        """Phase A совместимый шаг: targets + опциональные явные flows.

        Используется когда нет inputs_schedule (legacy-режим простой
        what-if симуляции по фазам рецепта).
        """
        flows = flows or {}
        return ZoneState(
            tank=self.tank_solver.step(state.tank, flows, dt_hours),
            chem=self.chem_solver.step(state.chem, targets, dt_hours),
            climate=self.climate_solver.step(state.climate, targets, dt_hours),
            substrate=self.substrate_solver.step(state.substrate, flows, dt_hours),
        )

    def step_with_commands(
        self,
        state: ZoneState,
        targets: Dict[str, float],
        dt_hours: float,
    ) -> ZoneState:
        """Phase B шаг: ActuatorSolver формирует flows и dose effects.

        Предполагается, что CommandRouter уже применил все события до начала
        этого dt-шага через `apply_command()`. Здесь мы делаем один step
        actuator-state на dt_seconds и пробрасываем результат в TankSolver/
        ChemSolver.
        """
        dt_seconds = max(0.0, dt_hours * 3600.0)
        effect: ActuatorEffect = self.actuator_solver.step(
            dt_seconds=dt_seconds,
            solution_volume_l=state.tank.solution_volume_l,
        )

        new_tank = self.tank_solver.step(state.tank, effect.flows, dt_hours)
        new_chem = self.chem_solver.step(
            state.chem,
            targets,
            dt_hours,
            dose_effect=effect.chem,
            solution_volume_l=max(state.tank.solution_volume_l, 1.0),
            ec_per_ml_per_l=float(self.actuator_solver.params["ec_per_ml_per_l"]),
            ph_per_meq_per_l=float(self.actuator_solver.params["ph_per_meq_per_l"]),
        )
        new_climate = self.climate_solver.step(state.climate, targets, dt_hours)

        # Полив (irrigation_out > 0) добавляет воду в субстрат пропорционально объёму.
        # Простая модель: каждые 10 л → +1% wc (configurable позже).
        substrate_flows: Dict[str, float] = {}
        irr_l_per_hour = effect.flows.get("irrigation_out_l_per_hour", 0.0)
        if irr_l_per_hour > 0:
            substrate_flows["irrigation_in_pct"] = irr_l_per_hour * dt_hours / 10.0
        new_substrate = self.substrate_solver.step(
            state.substrate, substrate_flows, dt_hours
        )

        return ZoneState(
            tank=new_tank,
            chem=new_chem,
            climate=new_climate,
            substrate=new_substrate,
        )
