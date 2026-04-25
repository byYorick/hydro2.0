"""Тесты ZoneWorld — оркестратора solver-ов.

Phase A: проверяем equivalence trajectory с legacy моделями + integration с
parametric input и flow inputs.
"""
import pytest

from solvers import ChemState, ClimateState, TankState, SubstrateState, ZoneState
from world import ZoneWorld


def test_zone_world_initial_state_uses_initial_dict():
    world = ZoneWorld()
    state = world.initial_state(
        {
            "ph": 5.8,
            "ec": 1.6,
            "temp_air": 23.5,
            "humidity_air": 65.0,
            "temp_water": 19.0,
        }
    )
    assert state.chem.ph == 5.8
    assert state.chem.ec == 1.6
    assert state.climate.temp_air_c == 23.5
    assert state.climate.humidity_air_pct == 65.0
    assert state.tank.water_temp_c == 19.0


def test_zone_world_initial_state_falls_back_to_defaults_for_missing_keys():
    world = ZoneWorld()
    state = world.initial_state({})
    assert state.chem.ph == 6.0
    assert state.chem.ec == 1.2
    assert state.climate.temp_air_c == 22.0


def test_zone_world_initial_state_handles_invalid_values():
    world = ZoneWorld()
    state = world.initial_state({"ph": "bad", "ec": None})
    # bad/None должны дать defaults
    assert state.chem.ph == 6.0
    assert state.chem.ec == 1.2


def test_zone_world_step_drives_chem_and_climate_with_targets():
    world = ZoneWorld()
    state = world.initial_state({"ph": 6.0, "ec": 1.2})
    new_state = world.step(
        state,
        targets={"ph": 6.5, "ec": 1.4, "temp_air": 22.0, "humidity_air": 60.0},
        dt_hours=0.5,
    )
    assert new_state.chem.ph > state.chem.ph
    assert new_state.chem.ec > state.chem.ec


def test_zone_world_step_passes_flows_to_tank_solver():
    world = ZoneWorld()
    state = world.initial_state({})
    new_state = world.step(
        state,
        targets={},
        dt_hours=0.5,
        flows={"clean_in_l_per_hour": 50.0},
    )
    assert new_state.tank.clean_volume_l > state.tank.clean_volume_l


def test_zone_world_params_by_group_propagate_to_solvers():
    world = ZoneWorld(
        params_by_group={
            "ph": {"correction_rate": 0.2},
            "ec": {"evaporation_rate": 0.05},
            "climate": {"heat_loss_rate": 1.0},
            "tank": {"evaporation_l_per_hour": 0.5},
        }
    )
    assert world.chem_solver.ph_params["correction_rate"] == 0.2
    assert world.chem_solver.ec_params["evaporation_rate"] == 0.05
    assert world.climate_solver.params["heat_loss_rate"] == 1.0
    assert world.tank_solver.params["evaporation_l_per_hour"] == 0.5


def test_zone_world_step_returns_new_state_object():
    """ZoneState immutable между шагами — solver-ы возвращают новый объект."""
    world = ZoneWorld()
    state = world.initial_state({})
    new_state = world.step(state, targets={"ph": 6.5}, dt_hours=0.5)
    assert new_state is not state
    assert new_state.chem is not state.chem


def test_zone_world_step_holds_state_when_no_targets_no_flows():
    """Без targets ChemSolver применяет только дрейф/испарение."""
    world = ZoneWorld()
    state = world.initial_state({"ph": 6.5, "ec": 1.5})
    new_state = world.step(state, targets={}, dt_hours=1.0)
    # ph: только drift вверх; ec: только evaporation вверх
    assert new_state.chem.ph >= state.chem.ph
    assert new_state.chem.ec > state.chem.ec
