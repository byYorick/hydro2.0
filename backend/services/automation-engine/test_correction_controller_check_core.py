from types import SimpleNamespace

from correction_controller_check_core import _reset_pid_integral_on_error_sign_change


def _pid(prev_error, integral):
    return SimpleNamespace(prev_error=prev_error, integral=integral)


def test_reset_pid_integral_on_error_sign_change_resets_integral():
    pid = _pid(prev_error=0.2, integral=12.0)

    changed = _reset_pid_integral_on_error_sign_change(
        pid=pid,
        zone_id=5,
        pid_type="ph",
        target_value=6.0,
        current_value=6.2,  # current_error = -0.2
    )

    assert changed is True
    assert pid.integral == 0.0


def test_reset_pid_integral_on_error_sign_change_ignores_same_sign():
    pid = _pid(prev_error=0.2, integral=12.0)

    changed = _reset_pid_integral_on_error_sign_change(
        pid=pid,
        zone_id=5,
        pid_type="ph",
        target_value=6.0,
        current_value=5.9,  # current_error = +0.1
    )

    assert changed is False
    assert pid.integral == 12.0


def test_reset_pid_integral_on_error_sign_change_ignores_missing_prev_error():
    pid = _pid(prev_error=None, integral=12.0)

    changed = _reset_pid_integral_on_error_sign_change(
        pid=pid,
        zone_id=5,
        pid_type="ph",
        target_value=6.0,
        current_value=6.2,
    )

    assert changed is False
    assert pid.integral == 12.0
