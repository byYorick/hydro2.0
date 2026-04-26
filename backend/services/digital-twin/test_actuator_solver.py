"""Unit-тесты ActuatorSolver и channel_roles (Phase B)."""
import pytest

from solvers import ActuatorSolver, ChemDoseEffect, resolve_channel_role


# --- channel_roles --------------------------------------------------------


@pytest.mark.parametrize(
    "channel,expected",
    [
        ("valve_clean_fill", "valve_clean_fill"),
        ("valve_clean_supply", "valve_clean_supply"),
        ("valve_solution_fill", "valve_solution_fill"),
        ("valve_solution_supply", "valve_solution_supply"),
        ("valve_irrigation", "valve_irrigation"),
        ("pump_main", "pump_main"),
        ("pump_acid", "pump_ph_down"),
        ("pump_base", "pump_ph_up"),
        ("pump_ph_down", "pump_ph_down"),
        ("pump_ph_up", "pump_ph_up"),
        ("pump_a", "pump_ec_a"),
        ("pump_b", "pump_ec_b"),
        ("pump_c", "pump_ec_c"),
        ("pump_d", "pump_ec_d"),
        ("dose_npk_a", "pump_ec_a"),
        ("relay_x", "unknown"),
    ],
)
def test_channel_roles_heuristic(channel, expected):
    assert resolve_channel_role(channel) == expected


def test_channel_roles_overrides_take_priority():
    assert (
        resolve_channel_role("custom_pump_77", overrides={"custom_pump_77": "pump_ec_a"})
        == "pump_ec_a"
    )


def test_channel_roles_invalid_override_falls_back_to_unknown():
    assert (
        resolve_channel_role("custom_pump_77", overrides={"custom_pump_77": "garbage"})
        == "unknown"
    )


# --- ActuatorSolver: set_relay --------------------------------------------


def test_actuator_solver_clean_fill_creates_inflow():
    solver = ActuatorSolver()
    solver.apply_command("set_relay", "valve_clean_fill", {"state": True})
    effect = solver.step(dt_seconds=10.0, solution_volume_l=100.0)
    assert effect.flows["clean_in_l_per_hour"] > 0
    assert effect.flows["clean_to_solution_l_per_hour"] == 0


def test_actuator_solver_clean_to_solution_requires_three_relays():
    solver = ActuatorSolver()
    solver.apply_command("set_relay", "pump_main", {"state": True})
    solver.apply_command("set_relay", "valve_clean_supply", {"state": True})
    # без valve_solution_fill потока быть не должно
    effect = solver.step(dt_seconds=10.0, solution_volume_l=100.0)
    assert effect.flows["clean_to_solution_l_per_hour"] == 0
    # включаем третий — поток появляется
    solver.apply_command("set_relay", "valve_solution_fill", {"state": True})
    effect = solver.step(dt_seconds=10.0, solution_volume_l=100.0)
    assert effect.flows["clean_to_solution_l_per_hour"] > 0


def test_actuator_solver_irrigation_path():
    solver = ActuatorSolver()
    for ch in ("pump_main", "valve_solution_supply", "valve_irrigation"):
        solver.apply_command("set_relay", ch, {"state": True})
    effect = solver.step(dt_seconds=60.0, solution_volume_l=100.0)
    assert effect.flows["irrigation_out_l_per_hour"] > 0


def test_actuator_solver_relay_off_disables_flow():
    solver = ActuatorSolver()
    solver.apply_command("set_relay", "valve_clean_fill", {"state": True})
    eff_on = solver.step(dt_seconds=1.0, solution_volume_l=100.0)
    solver.apply_command("set_relay", "valve_clean_fill", {"state": False})
    eff_off = solver.step(dt_seconds=1.0, solution_volume_l=100.0)
    assert eff_on.flows["clean_in_l_per_hour"] > 0
    assert eff_off.flows["clean_in_l_per_hour"] == 0


# --- ActuatorSolver: dose -------------------------------------------------


def test_actuator_solver_dose_ec_a_increments_chem():
    solver = ActuatorSolver(params={"channel_calibrations": {"pump_a": 2.0}})
    solver.apply_command("dose", "pump_a", {"ml": 5.0})
    # 2 ml/sec → 2.5 sec на полную дозу. Шагаем 1.5 сек, потом 1 сек.
    e1 = solver.step(dt_seconds=1.5, solution_volume_l=100.0)
    e2 = solver.step(dt_seconds=1.0, solution_volume_l=100.0)
    e3 = solver.step(dt_seconds=2.0, solution_volume_l=100.0)
    total_ml = e1.chem.ec_dose_ml + e2.chem.ec_dose_ml + e3.chem.ec_dose_ml
    assert total_ml == pytest.approx(5.0, abs=1e-6)
    # После полной дозы pulses пуст
    assert "pump_ec_a" not in solver.state.pulses_by_role


def test_actuator_solver_dose_ph_down_negative_meq():
    solver = ActuatorSolver()
    solver.apply_command("dose", "pump_acid", {"ml": 2.0})
    effect = solver.step(dt_seconds=10.0, solution_volume_l=100.0)
    assert effect.chem.ph_dose_meq_net < 0


def test_actuator_solver_dose_ph_up_positive_meq():
    solver = ActuatorSolver()
    solver.apply_command("dose", "pump_base", {"ml": 2.0})
    effect = solver.step(dt_seconds=10.0, solution_volume_l=100.0)
    assert effect.chem.ph_dose_meq_net > 0


def test_actuator_solver_run_pump_uses_duration_ms():
    solver = ActuatorSolver(params={"default_pump_ml_per_sec": 3.0})
    solver.apply_command("run_pump", "pump_a", {"duration_ms": 2000})
    # 3 ml/sec * 2 sec = 6ml
    effect = solver.step(dt_seconds=10.0, solution_volume_l=100.0)
    assert effect.chem.ec_dose_ml == pytest.approx(6.0, abs=1e-6)


def test_actuator_solver_dose_in_flow_reflects_volume_added():
    solver = ActuatorSolver(params={"channel_calibrations": {"pump_a": 2.0}})
    solver.apply_command("dose", "pump_a", {"ml": 4.0})
    effect = solver.step(dt_seconds=2.0, solution_volume_l=100.0)
    # за 2 сек прошло 4ml → 4ml/2s = 2ml/s = 7200 ml/hour = 7.2 l/hour
    assert effect.flows["dose_in_l_per_hour"] == pytest.approx(7.2, abs=1e-3)


def test_actuator_solver_zero_dt_returns_empty_effect():
    solver = ActuatorSolver()
    solver.apply_command("dose", "pump_a", {"ml": 5.0})
    effect = solver.step(dt_seconds=0.0, solution_volume_l=100.0)
    assert effect.chem.ec_dose_ml == 0.0
    assert effect.flows["dose_in_l_per_hour"] == 0.0


def test_actuator_solver_unknown_channel_doesnt_affect_chem():
    solver = ActuatorSolver()
    solver.apply_command("dose", "weird_channel_xyz", {"ml": 1.0})
    effect = solver.step(dt_seconds=10.0, solution_volume_l=100.0)
    assert effect.chem.ec_dose_ml == 0.0
    assert effect.chem.ph_dose_meq_net == 0.0


def test_actuator_solver_calibration_override_via_params():
    solver = ActuatorSolver(
        params={"channel_calibrations": {"pump_a": 5.0}}
    )
    assert solver._calibration_for("pump_a", "pump_ec_a") == 5.0
    # fallback к default для незнакомого
    assert solver._calibration_for("pump_unknown", "pump_ec_b") == solver.params["default_pump_ml_per_sec"]


def test_actuator_solver_channel_roles_override_via_params():
    solver = ActuatorSolver(
        params={"channel_roles": {"custom_npk": "pump_ec_a"}}
    )
    solver.apply_command("dose", "custom_npk", {"ml": 2.0})
    effect = solver.step(dt_seconds=10.0, solution_volume_l=100.0)
    assert effect.chem.ec_dose_ml == pytest.approx(2.0, abs=1e-6)


def test_chem_dose_effect_is_zero_by_default():
    eff = ChemDoseEffect()
    assert eff.ec_dose_ml == 0.0
    assert eff.ph_dose_meq_net == 0.0
