import pytest

from utils.adaptive_pid import RelayAutotuneConfig, RelayAutotuner


def _default_config(**overrides) -> RelayAutotuneConfig:
    return RelayAutotuneConfig(
        relay_amplitude_ml=overrides.get("relay_amplitude_ml", 3.0),
        min_cycles=overrides.get("min_cycles", 3),
        max_duration_sec=overrides.get("max_duration_sec", 7200.0),
        min_oscillation_amplitude=overrides.get("min_oscillation_amplitude", 0.02),
    )


class TestRelayAutotuner:
    def test_relay_output_matches_sign(self):
        autotuner = RelayAutotuner(_default_config(), setpoint=6.0, start_time_sec=0.0)

        output = autotuner.update(5.5, now_sec=0.0)

        assert output == pytest.approx(3.0)

    def test_relay_output_is_negative_when_current_above_setpoint_on_first_tick(self):
        autotuner = RelayAutotuner(_default_config(), setpoint=6.0, start_time_sec=0.0)

        output = autotuner.update(6.5, now_sec=0.0)

        assert output == pytest.approx(-3.0)

    def test_relay_flips_on_zero_crossing(self):
        autotuner = RelayAutotuner(_default_config(), setpoint=6.0, start_time_sec=0.0)

        first = autotuner.update(5.5, now_sec=0.0)
        second = autotuner.update(6.1, now_sec=20.0)

        assert first == pytest.approx(3.0)
        assert second == pytest.approx(-3.0)

    def test_converges_after_min_cycles(self):
        autotuner = RelayAutotuner(_default_config(min_cycles=3), setpoint=6.0, start_time_sec=0.0)

        values = [5.8, 6.2, 5.8, 6.2, 5.8, 6.2, 5.8]
        now = 0.0
        for value in values:
            _ = autotuner.update(value, now_sec=now)
            now += 20.0

        assert autotuner.is_complete
        assert not autotuner.is_timed_out
        assert autotuner.result is not None
        assert autotuner.result.kp > 0
        assert autotuner.result.ki >= 0
        assert autotuner.result.ku > 0
        assert autotuner.result.tu_sec > 0

    def test_timeout_if_no_oscillations(self):
        autotuner = RelayAutotuner(
            _default_config(max_duration_sec=10.0, min_cycles=3),
            setpoint=6.0,
            start_time_sec=0.0,
        )

        for tick in range(100):
            output = autotuner.update(6.5, now_sec=float(tick))
            if output is None:
                break

        assert autotuner.is_timed_out
        assert not autotuner.is_complete

    def test_result_none_if_not_complete(self):
        autotuner = RelayAutotuner(_default_config(), setpoint=6.0, start_time_sec=0.0)

        assert autotuner.result is None
        assert not autotuner.is_complete

    def test_simc_formulas_correct(self):
        config = RelayAutotuneConfig(
            relay_amplitude_ml=5.0,
            min_cycles=3,
            simc_kp_factor=0.45,
            simc_ti_factor=0.83,
        )
        autotuner = RelayAutotuner(config, setpoint=6.0, start_time_sec=0.0)

        autotuner._extrema = [6.5, 5.5, 6.5, 5.5, 6.5, 5.5, 6.5, 5.5]
        autotuner._extrema_times = [50.0, 100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0]
        autotuner._zero_crossings = 8

        result = autotuner._compute_params(elapsed_sec=400.0)

        assert result is not None
        assert result.kp == pytest.approx(5.73, abs=0.1)
        assert result.ki == pytest.approx(0.069, abs=0.01)
