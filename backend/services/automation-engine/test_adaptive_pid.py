from unittest.mock import patch

from utils.adaptive_pid import AdaptivePid, AdaptivePidConfig, PidZone, PidZoneCoeffs


def _ph_pid_config(setpoint: float = 6.0, **overrides) -> AdaptivePidConfig:
    zone_coeffs = {
        PidZone.DEAD: PidZoneCoeffs(kp=0.0, ki=0.0, kd=0.0),
        PidZone.CLOSE: PidZoneCoeffs(kp=5.0, ki=0.05, kd=0.0),
        PidZone.FAR: PidZoneCoeffs(kp=8.0, ki=0.02, kd=0.0),
    }
    return AdaptivePidConfig(
        setpoint=setpoint,
        dead_zone=0.05,
        close_zone=0.30,
        far_zone=1.0,
        zone_coeffs=overrides.get("zone_coeffs", zone_coeffs),
        max_output=overrides.get("max_output", 20.0),
        min_output=0.0,
        max_integral=overrides.get("max_integral", 20.0),
        anti_windup_mode=overrides.get("anti_windup_mode", "conditional"),
        min_interval_ms=overrides.get("min_interval_ms", 0),
        derivative_filter_alpha=0.35,
    )


class TestAdaptivePidDeadZone:
    def test_dead_zone_no_output(self):
        pid = AdaptivePid(_ph_pid_config())
        output = pid.compute(6.03, dt_seconds=60.0)
        assert output == 0.0

    def test_just_outside_dead_zone(self):
        pid = AdaptivePid(_ph_pid_config())
        output = pid.compute(5.94, dt_seconds=60.0)
        assert output > 0.0


class TestAdaptivePidProportional:
    def test_p_term_scales_with_error(self):
        pid1 = AdaptivePid(_ph_pid_config())
        pid2 = AdaptivePid(_ph_pid_config())

        out1 = pid1.compute(5.75, dt_seconds=0.001)
        out2 = pid2.compute(5.85, dt_seconds=0.001)

        assert out1 > out2
        assert abs((out1 / out2) - (0.25 / 0.15)) < 0.2


class TestAdaptivePidIntegral:
    def test_integral_eliminates_steady_state_error(self):
        pid = AdaptivePid(_ph_pid_config(setpoint=6.0))

        outputs = []
        for _ in range(5):
            outputs.append(pid.compute(5.93, dt_seconds=60.0))

        assert outputs[-1] > outputs[0]
        assert outputs[-1] > 0.35

    def test_ki_zero_means_no_integral_growth(self):
        coeffs = {
            PidZone.DEAD: PidZoneCoeffs(0.0, 0.0, 0.0),
            PidZone.CLOSE: PidZoneCoeffs(5.0, 0.0, 0.0),
            PidZone.FAR: PidZoneCoeffs(8.0, 0.0, 0.0),
        }
        pid = AdaptivePid(_ph_pid_config(zone_coeffs=coeffs))
        outputs = [pid.compute(5.93, dt_seconds=60.0) for _ in range(5)]

        assert all(abs(value - outputs[0]) < 1e-9 for value in outputs)


class TestAdaptivePidAntiWindup:
    def test_integral_clamped_by_max_integral(self):
        pid = AdaptivePid(_ph_pid_config(max_integral=5.0))

        for _ in range(100):
            pid.compute(4.0, dt_seconds=60.0)

        assert abs(pid.integral) <= 5.0 + 1e-9

    def test_conditional_antiwindup_prevents_growth_at_saturation(self):
        pid = AdaptivePid(
            _ph_pid_config(
                max_output=1.0,
                max_integral=100.0,
                anti_windup_mode="conditional",
            )
        )
        integrals = []

        for _ in range(10):
            pid.compute(3.0, dt_seconds=60.0)
            integrals.append(pid.integral)

        assert max(integrals[-5:]) - min(integrals[-5:]) < 1e-6


class TestAdaptivePidMinInterval:
    def test_min_interval_blocks_second_dose(self):
        pid = AdaptivePid(_ph_pid_config(min_interval_ms=1000))

        with patch("utils.adaptive_pid.time.monotonic", side_effect=[10.0, 10.5]):
            out1 = pid.compute(5.5, dt_seconds=60.0)
            out2 = pid.compute(5.5, dt_seconds=1.0)

        assert out1 > 0.0
        assert out2 == 0.0

    def test_min_interval_allows_after_elapsed(self):
        pid = AdaptivePid(_ph_pid_config(min_interval_ms=100))

        with patch("utils.adaptive_pid.time.monotonic", side_effect=[20.0, 20.2]):
            out1 = pid.compute(5.5, dt_seconds=60.0)
            out2 = pid.compute(5.5, dt_seconds=60.0)

        assert out1 > 0.0
        assert out2 > 0.0


class TestAdaptivePidEmergency:
    def test_emergency_stop_blocks_output(self):
        pid = AdaptivePid(_ph_pid_config())
        pid.emergency_stop()

        output = pid.compute(5.0, dt_seconds=60.0)

        assert output == 0.0

    def test_resume_after_emergency(self):
        pid = AdaptivePid(_ph_pid_config())
        pid.emergency_stop()
        pid.resume()

        output = pid.compute(5.0, dt_seconds=60.0)

        assert output > 0.0


class TestAdaptivePidSetpointChange:
    def test_integral_reset_on_large_setpoint_change(self):
        pid = AdaptivePid(_ph_pid_config(setpoint=6.0))
        pid.integral = 10.0
        pid.prev_error = 0.2

        pid.update_setpoint(6.5)

        assert pid.integral == 0.0
        assert pid.prev_error is None

    def test_setpoint_no_reset_on_tiny_change(self):
        pid = AdaptivePid(_ph_pid_config(setpoint=6.0))
        pid.integral = 10.0
        pid.prev_error = 0.2

        pid.update_setpoint(6.0005)

        assert pid.integral == 10.0
        assert pid.prev_error == 0.2
