"""Unit-тесты для модульных solver-ов Digital Twin (Phase A)."""
import pytest

from solvers import (
    ChemSolver,
    ChemState,
    ClimateSolver,
    ClimateState,
    SubstrateSolver,
    SubstrateState,
    TankSolver,
    TankState,
)


# --- ChemSolver -----------------------------------------------------------


def test_chem_solver_default_params_equal_legacy():
    solver = ChemSolver()
    assert solver.ph_params["natural_drift"] == 0.01
    assert solver.ph_params["correction_rate"] == 0.05
    assert solver.ec_params["evaporation_rate"] == 0.02
    assert solver.ec_params["nutrient_addition_rate"] == 0.03


def test_chem_solver_step_drives_ph_toward_target():
    solver = ChemSolver()
    state = ChemState(ph=6.0, ec=1.2)
    new_state = solver.step(state, {"ph": 6.5, "ec": 1.2}, dt_hours=1.0)
    assert new_state.ph > state.ph
    assert 4.0 <= new_state.ph <= 9.0


def test_chem_solver_step_evaporation_raises_ec_without_target_change():
    solver = ChemSolver()
    state = ChemState(ph=6.0, ec=1.2)
    new_state = solver.step(state, {"ec": 1.2}, dt_hours=1.0)
    assert new_state.ec > state.ec


def test_chem_solver_overrides_merge_with_defaults():
    solver = ChemSolver(ph_params={"correction_rate": 0.2})
    assert solver.ph_params["correction_rate"] == 0.2
    # defaults сохранены
    assert solver.ph_params["natural_drift"] == 0.01


def test_chem_solver_ignores_invalid_overrides():
    solver = ChemSolver(ec_params={"evaporation_rate": "not a number", "dilution_rate": None})
    assert solver.ec_params["evaporation_rate"] == 0.02
    assert solver.ec_params["dilution_rate"] == 0.01


def test_chem_solver_clamps_ec_to_range():
    solver = ChemSolver(ec_params={"nutrient_addition_rate": 1000.0})
    state = ChemState(ph=6.0, ec=1.0)
    new_state = solver.step(state, {"ec": 4.0}, dt_hours=1.0)
    assert 0.1 <= new_state.ec <= 5.0


# --- ClimateSolver --------------------------------------------------------


def test_climate_solver_heat_loss_only_when_target_close():
    solver = ClimateSolver()
    state = ClimateState(temp_air_c=22.0, humidity_air_pct=60.0)
    new_state = solver.step(state, {"temp_air": 22.0, "humidity_air": 60.0}, dt_hours=1.0)
    assert new_state.temp_air_c < state.temp_air_c
    assert new_state.humidity_air_pct < state.humidity_air_pct


def test_climate_solver_drives_temp_up_when_target_higher():
    solver = ClimateSolver()
    state = ClimateState(temp_air_c=20.0, humidity_air_pct=50.0)
    new_state = solver.step(state, {"temp_air": 25.0, "humidity_air": 70.0}, dt_hours=1.0)
    assert new_state.temp_air_c > state.temp_air_c - solver.params["heat_loss_rate"]
    assert 10.0 <= new_state.temp_air_c <= 35.0


# --- TankSolver -----------------------------------------------------------


def test_tank_solver_no_flow_only_evaporation():
    solver = TankSolver()
    state = TankState(clean_volume_l=100.0, solution_volume_l=100.0)
    new_state = solver.step(state, flows={}, dt_hours=1.0)
    assert new_state.clean_volume_l == pytest.approx(100.0)
    assert new_state.solution_volume_l == pytest.approx(100.0 - solver.params["evaporation_l_per_hour"])


def test_tank_solver_clean_fill_raises_clean_max():
    solver = TankSolver()
    state = TankState(clean_volume_l=50.0)
    new_state = solver.step(state, flows={"clean_in_l_per_hour": 200.0}, dt_hours=1.0)
    # Заполнение в пределах capacity, level_clean_max сработал
    assert new_state.clean_volume_l > state.clean_volume_l
    assert new_state.level_clean_max is True


def test_tank_solver_clean_to_solution_transfers_volume():
    solver = TankSolver()
    state = TankState(clean_volume_l=100.0, solution_volume_l=50.0)
    new_state = solver.step(
        state,
        flows={"clean_to_solution_l_per_hour": 30.0},
        dt_hours=1.0,
    )
    assert new_state.clean_volume_l == pytest.approx(70.0)
    assert new_state.solution_volume_l == pytest.approx(
        50.0 + 30.0 - solver.params["evaporation_l_per_hour"]
    )


def test_tank_solver_irrigation_lowers_solution():
    solver = TankSolver()
    state = TankState(solution_volume_l=100.0)
    new_state = solver.step(
        state,
        flows={"irrigation_out_l_per_hour": 20.0},
        dt_hours=0.5,
    )
    assert new_state.solution_volume_l < state.solution_volume_l


def test_tank_solver_level_min_drops_when_volume_below_threshold():
    solver = TankSolver(params={"solution_threshold_min_l": 50.0})
    state = TankState(solution_volume_l=60.0)
    new_state = solver.step(
        state,
        flows={"irrigation_out_l_per_hour": 30.0},
        dt_hours=1.0,
    )
    assert new_state.solution_volume_l < 50.0
    assert new_state.level_solution_min is False


def test_tank_solver_does_not_overflow_capacity():
    solver = TankSolver()
    state = TankState(clean_volume_l=190.0, clean_capacity_l=200.0)
    new_state = solver.step(
        state,
        flows={"clean_in_l_per_hour": 1000.0},
        dt_hours=1.0,
    )
    assert new_state.clean_volume_l == pytest.approx(state.clean_capacity_l)


# --- SubstrateSolver ------------------------------------------------------


def test_substrate_solver_drains_without_irrigation():
    solver = SubstrateSolver()
    state = SubstrateState(water_content_pct=60.0)
    new_state = solver.step(state, flows={}, dt_hours=1.0)
    assert new_state.water_content_pct == pytest.approx(
        60.0 - solver.params["drainage_pct_per_hour"]
    )


def test_substrate_solver_irrigation_increases_wc():
    solver = SubstrateSolver()
    state = SubstrateState(water_content_pct=40.0)
    new_state = solver.step(state, flows={"irrigation_in_pct": 10.0}, dt_hours=1.0)
    assert new_state.water_content_pct > state.water_content_pct


def test_substrate_solver_clamps_to_range():
    solver = SubstrateSolver()
    overflow = solver.step(
        SubstrateState(water_content_pct=99.0),
        flows={"irrigation_in_pct": 50.0},
        dt_hours=1.0,
    )
    underflow = solver.step(
        SubstrateState(water_content_pct=1.0),
        flows={},
        dt_hours=10.0,
    )
    assert overflow.water_content_pct == 100.0
    assert underflow.water_content_pct == 0.0
