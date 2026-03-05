from types import SimpleNamespace

import correction_controller_helpers as helpers
from correction_controller_helpers import (
    determine_correction_type_for_diff,
    get_dt_seconds_for_zone,
    select_actuator_for_correction,
)


def _controller(metric: str) -> SimpleNamespace:
    return SimpleNamespace(correction_type=SimpleNamespace(value=metric))


def test_determine_correction_type_for_diff_ec_uses_sign_for_small_negative_diff():
    controller = _controller("ec")
    correction_type = determine_correction_type_for_diff(controller, diff=-0.14)
    assert correction_type == "add_nutrients"


def test_determine_correction_type_for_diff_ec_uses_sign_for_positive_diff():
    controller = _controller("ec")
    correction_type = determine_correction_type_for_diff(controller, diff=0.03)
    assert correction_type == "dilute"


def test_determine_correction_type_for_diff_ph_uses_sign_for_negative_diff():
    controller = _controller("ph")
    correction_type = determine_correction_type_for_diff(controller, diff=-0.1)
    assert correction_type == "add_base"


def test_determine_correction_type_for_diff_ph_uses_sign_for_positive_diff():
    controller = _controller("ph")
    correction_type = determine_correction_type_for_diff(controller, diff=0.1)
    assert correction_type == "add_acid"


def test_get_dt_seconds_for_zone_clamps_to_max(monkeypatch):
    controller = SimpleNamespace(_last_pid_tick={7: 1000.0})
    monkeypatch.setattr(helpers.time, "monotonic", lambda: 1600.0)

    dt = get_dt_seconds_for_zone(controller, zone_id=7)

    assert dt == 300.0


def test_get_dt_seconds_for_zone_clamps_to_min(monkeypatch):
    controller = SimpleNamespace(_last_pid_tick={7: 1000.0})
    monkeypatch.setattr(helpers.time, "monotonic", lambda: 1001.0)

    dt = get_dt_seconds_for_zone(controller, zone_id=7)

    assert dt == 5.0


def test_select_actuator_for_dilute_prefers_recirculation_pump():
    controller = _controller("ec")
    actuators = {
        "irrigation_pump": {"role": "irrigation_pump", "channel": "pump_main"},
        "recirculation_pump": {"role": "recirculation_pump", "channel": "pump_recirc"},
    }

    selected = select_actuator_for_correction(
        controller=controller,
        correction_type="dilute",
        actuators=actuators,
        nodes={},
    )

    assert selected == actuators["recirculation_pump"]


def test_select_actuator_for_dilute_falls_back_to_irrigation_pump():
    controller = _controller("ec")
    actuators = {
        "irrigation_pump": {"role": "irrigation_pump", "channel": "pump_main"},
    }

    selected = select_actuator_for_correction(
        controller=controller,
        correction_type="dilute",
        actuators=actuators,
        nodes={},
    )

    assert selected == actuators["irrigation_pump"]
