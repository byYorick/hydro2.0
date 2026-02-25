import logging
from unittest.mock import patch

from utils.adaptive_pid import (
    AdaptivePid,
    AdaptivePidConfig,
    PidZone,
    PidZoneCoeffs,
)


def _build_pid_config(**overrides):
    zone_coeffs = {
        PidZone.DEAD: PidZoneCoeffs(kp=0.0, ki=0.0, kd=0.0),
        PidZone.CLOSE: PidZoneCoeffs(kp=0.8, ki=0.2, kd=0.1),
        PidZone.FAR: PidZoneCoeffs(kp=1.2, ki=0.3, kd=0.1),
    }
    config = AdaptivePidConfig(
        setpoint=10.0,
        dead_zone=0.1,
        close_zone=2.0,
        far_zone=10.0,
        zone_coeffs=zone_coeffs,
        max_output=50.0,
        min_output=0.0,
        max_integral=5.0,
        min_interval_ms=1000,
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def test_pid_respects_min_interval_and_logs_reason(caplog):
    pid = AdaptivePid(_build_pid_config())
    caplog.set_level(logging.DEBUG, logger="utils.adaptive_pid")

    with patch("utils.adaptive_pid.time.monotonic", side_effect=[1.0, 1.1]):
        first = pid.compute(current_value=5.0, dt_seconds=1.0)
        second = pid.compute(current_value=5.0, dt_seconds=1.0)

    assert first > 0
    assert second == 0.0
    assert "min interval guard" in caplog.text


def test_pid_clamps_integral_and_logs(caplog):
    pid = AdaptivePid(_build_pid_config(max_integral=1.0))
    caplog.set_level(logging.DEBUG, logger="utils.adaptive_pid")

    with patch("utils.adaptive_pid.time.monotonic", side_effect=[2.0]):
        _ = pid.compute(current_value=0.0, dt_seconds=5.0)

    assert pid.integral == 1.0
    assert "integral clamped" in caplog.text


def test_pid_dead_zone_returns_zero():
    pid = AdaptivePid(_build_pid_config())

    with patch("utils.adaptive_pid.time.monotonic", side_effect=[3.0]):
        output = pid.compute(current_value=10.05, dt_seconds=1.0)

    assert output == 0.0
    assert pid.get_zone() == PidZone.DEAD


def test_pid_emergency_mode_returns_zero():
    pid = AdaptivePid(_build_pid_config())
    pid.emergency_stop()

    with patch("utils.adaptive_pid.time.monotonic", side_effect=[4.0]):
        output = pid.compute(current_value=5.0, dt_seconds=1.0)

    assert output == 0.0
