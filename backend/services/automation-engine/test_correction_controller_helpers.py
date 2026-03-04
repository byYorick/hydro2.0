from types import SimpleNamespace

from correction_controller_helpers import determine_correction_type_for_diff


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
