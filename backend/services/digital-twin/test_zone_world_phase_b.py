"""Интеграционные тесты Phase B: ZoneWorld + ActuatorSolver + CommandRouter."""
import pytest

from solvers import ActuatorSolver, ChemDoseEffect, ChemSolver, ChemState
from world import CommandRouter, ZoneWorld


def test_chem_solver_dose_effect_increases_ec():
    solver = ChemSolver()
    state = ChemState(ph=6.0, ec=1.0)
    new_state = solver.step(
        state,
        targets={"ph": 6.0, "ec": 1.0},  # без targets-driven correction
        dt_hours=0.0,
        dose_effect=ChemDoseEffect(ec_dose_ml=10.0, ph_dose_meq_net=0.0),
        solution_volume_l=100.0,
        ec_per_ml_per_l=0.4,
    )
    # 10 ml × 0.4 / 100 l = +0.04 EC. dt=0 → дополнительных drift нет.
    assert new_state.ec == pytest.approx(1.04, abs=1e-3)


def test_chem_solver_dose_effect_drops_ph_when_acid():
    solver = ChemSolver()
    state = ChemState(ph=6.5, ec=1.5)
    new_state = solver.step(
        state,
        targets={"ph": 6.5, "ec": 1.5},
        dt_hours=0.0,
        dose_effect=ChemDoseEffect(ec_dose_ml=0.0, ph_dose_meq_net=-2.0),
        solution_volume_l=100.0,
        ph_per_meq_per_l=0.5,
    )
    # -2 meq * 0.5 / 100 l = -0.01 pH. clamp to 4.0..9.0
    assert new_state.ph == pytest.approx(6.49, abs=1e-3)


def test_chem_solver_no_dose_effect_equivalent_to_phase_a():
    solver = ChemSolver()
    state = ChemState(ph=6.0, ec=1.2)
    legacy = solver.step(state, {"ph": 6.5, "ec": 1.4}, dt_hours=0.5)
    new_api = solver.step(
        state,
        {"ph": 6.5, "ec": 1.4},
        dt_hours=0.5,
        dose_effect=None,
    )
    assert legacy.ph == new_api.ph
    assert legacy.ec == new_api.ec


def test_zone_world_step_with_commands_clean_fill_raises_volume():
    world = ZoneWorld()
    state = world.initial_state({})
    initial_clean = state.tank.clean_volume_l
    world.actuator_solver.apply_command(
        "set_relay", "valve_clean_fill", {"state": True}
    )
    # шаг 30 минут (0.5 часа) при 60 l/час → +30 l
    new_state = world.step_with_commands(state, targets={}, dt_hours=0.5)
    assert new_state.tank.clean_volume_l > initial_clean


def test_zone_world_step_with_commands_dose_changes_ec():
    world = ZoneWorld(
        params_by_group={"actuator": {"channel_calibrations": {"pump_a": 2.0}}}
    )
    state = world.initial_state({"ec": 1.0, "ph": 6.0})
    world.actuator_solver.apply_command("dose", "pump_a", {"ml": 4.0})
    # 2 ml/sec за 2 секунды = 4ml; шаг по dt_hours = 2/3600
    new_state = world.step_with_commands(state, targets={}, dt_hours=2.0 / 3600.0)
    # Volume ~100l, +4ml *0.4/100 = +0.016 mass-balance term
    assert new_state.chem.ec > state.chem.ec


def test_zone_world_command_driven_full_pipeline_with_command_router():
    world = ZoneWorld()
    schedule = [
        {"t_min": 0.0, "cmd": "set_relay", "channel": "valve_clean_fill",
         "params": {"state": True}},
        {"t_min": 30.0, "cmd": "set_relay", "channel": "valve_clean_fill",
         "params": {"state": False}},
    ]
    router = CommandRouter(world.actuator_solver, schedule)
    state = world.initial_state({})
    # 0..30 min — наполняем
    router.advance_to(30.0)
    state = world.step_with_commands(state, targets={}, dt_hours=0.5)
    after_fill_clean = state.tank.clean_volume_l
    # 30..60 min — пусто
    router.advance_to(60.0)
    state = world.step_with_commands(state, targets={}, dt_hours=0.5)
    # Уровень не должен расти после закрытия (испарение из solution не влияет на clean)
    assert state.tank.clean_volume_l == pytest.approx(after_fill_clean, abs=1e-6)


def test_zone_world_step_with_commands_irrigation_increases_substrate_water():
    world = ZoneWorld()
    state = world.initial_state({"water_content": 50.0})
    for ch in ("pump_main", "valve_solution_supply", "valve_irrigation"):
        world.actuator_solver.apply_command("set_relay", ch, {"state": True})
    new_state = world.step_with_commands(state, targets={}, dt_hours=1.0)
    assert new_state.substrate.water_content_pct > state.substrate.water_content_pct


def test_zone_world_legacy_step_does_not_use_actuator_solver():
    """Phase A legacy путь — шагает без обращения к actuator_solver."""
    world = ZoneWorld()
    state = world.initial_state({"ph": 6.0, "ec": 1.2})
    # actuator state пуст — даже если использовать step_with_commands,
    # results не должны сильно отличаться от step() с пустыми flows
    s1 = world.step(state, {"ph": 6.5}, dt_hours=0.5)
    s2 = world.step_with_commands(state, {"ph": 6.5}, dt_hours=0.5)
    assert s1.chem.ph == pytest.approx(s2.chem.ph, abs=1e-9)
    assert s1.chem.ec == pytest.approx(s2.chem.ec, abs=1e-9)
