"""Тесты per-phase EC target для двухбакового контура.

При подготовке раствора (solution_fill / tank_recirc) дозируется только NPK,
поэтому EC target = full_ec × npk_share.
При поливе (irrigation) — полный EC target (кумулятивно: NPK уже в растворе).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from ae3lite.domain.services.two_tank_runtime_spec import (
    _compute_prepare_ec_share,
    resolve_two_tank_runtime,
)


# ── _compute_prepare_ec_share ────────────────────────────────────────────────


class TestComputePrepareEcShare:

    def test_basic_4_component(self) -> None:
        ratios = {"npk": 44.0, "calcium": 36.0, "magnesium": 14.0, "micro": 8.0}
        # 44/(44+36+14+8) = 44/102? Нет, тут в процентах = 100 суммарно,
        # npk/total = 44/102 = 0.4314. Но типичный кейс: сумма = 100.
        cfg = {"ec_component_ratios": ratios}
        share = _compute_prepare_ec_share(cfg, {})
        assert share == pytest.approx(0.4314, abs=0.001)

    def test_ratios_sum_to_100(self) -> None:
        ratios = {"npk": 44.0, "calcium": 36.0, "magnesium": 12.0, "micro": 8.0}
        cfg = {"ec_component_ratios": ratios}
        share = _compute_prepare_ec_share(cfg, {})
        assert share == pytest.approx(0.44, abs=0.001)

    def test_no_ratios_returns_1(self) -> None:
        share = _compute_prepare_ec_share({}, {})
        assert share == 1.0

    def test_empty_ratios_returns_1(self) -> None:
        share = _compute_prepare_ec_share({"ec_component_ratios": {}}, {})
        assert share == 1.0

    def test_npk_zero_returns_1(self) -> None:
        ratios = {"npk": 0, "calcium": 50.0, "micro": 50.0}
        share = _compute_prepare_ec_share({"ec_component_ratios": ratios}, {})
        assert share == 1.0

    def test_npk_missing_returns_1(self) -> None:
        ratios = {"calcium": 60.0, "micro": 40.0}
        share = _compute_prepare_ec_share({"ec_component_ratios": ratios}, {})
        assert share == 1.0

    def test_fallback_to_base_cfg(self) -> None:
        """Если в solution_fill нет ratios, берём из base."""
        ratios = {"npk": 44.0, "calcium": 36.0, "magnesium": 12.0, "micro": 8.0}
        share = _compute_prepare_ec_share({}, {"ec_component_ratios": ratios})
        assert share == pytest.approx(0.44, abs=0.001)

    def test_3_component_model(self) -> None:
        """Старая 3-компонентная модель: npk + calcium + micro."""
        ratios = {"npk": 44.0, "calcium": 44.0, "micro": 12.0}
        cfg = {"ec_component_ratios": ratios}
        share = _compute_prepare_ec_share(cfg, {})
        assert share == pytest.approx(0.44, abs=0.001)

    def test_invalid_values_ignored(self) -> None:
        ratios = {"npk": 44.0, "calcium": "bad", "micro": -5}
        cfg = {"ec_component_ratios": ratios}
        share = _compute_prepare_ec_share(cfg, {})
        # total = 44 (only npk valid), npk/total = 1.0
        assert share == pytest.approx(1.0, abs=0.001)

    def test_non_mapping_ratios_returns_1(self) -> None:
        share = _compute_prepare_ec_share({"ec_component_ratios": "not_a_dict"}, {})
        assert share == 1.0


# ── resolve_two_tank_runtime — per-phase targets ─────────────────────────────


def _minimal_zone_correction_config(
    *,
    ec_component_ratios: dict[str, float] | None = None,
) -> dict[str, object]:
    phases: dict[str, object] = {
        "solution_fill": {},
        "tank_recirc": {},
        "irrigation": {},
    }
    base: dict[str, object] = {
        "runtime": {
            "required_node_type": "irrig",
            "clean_fill_timeout_sec": 1200,
            "solution_fill_timeout_sec": 1800,
            "clean_fill_retry_cycles": 1,
            "level_switch_on_threshold": 0.5,
            "clean_max_sensor_label": "level_clean_max",
            "clean_min_sensor_label": "level_clean_min",
            "solution_max_sensor_label": "level_solution_max",
            "solution_min_sensor_label": "level_solution_min",
        },
        "timing": {
            "sensor_mode_stabilization_time_sec": 60,
            "stabilization_sec": 60,
            "telemetry_max_age_sec": 60,
            "irr_state_max_age_sec": 30,
            "level_poll_interval_sec": 10,
        },
        "retry": {
            "max_ec_correction_attempts": 5,
            "max_ph_correction_attempts": 5,
            "prepare_recirculation_timeout_sec": 1200,
            "prepare_recirculation_max_attempts": 3,
            "prepare_recirculation_max_correction_attempts": 20,
            "telemetry_stale_retry_sec": 30,
            "decision_window_retry_sec": 30,
            "low_water_retry_sec": 60,
        },
        "dosing": {
            "solution_volume_l": 100.0,
            "dose_ec_channel": "ec_npk_pump",
            "dose_ph_up_channel": "ph_base_pump",
            "dose_ph_down_channel": "ph_acid_pump",
            "max_ec_dose_ml": 50.0,
            "max_ph_dose_ml": 20.0,
        },
        "tolerance": {
            "prepare_tolerance": {"ph_pct": 15.0, "ec_pct": 25.0},
        },
        "controllers": {
            "ph": {
                "mode": "cross_coupled_pi_d",
                "kp": 5.0, "ki": 0.05, "kd": 0.0,
                "derivative_filter_alpha": 0.35,
                "deadband": 0.05,
                "max_dose_ml": 20.0, "min_interval_sec": 90, "max_integral": 20.0,
                "anti_windup": {"enabled": True},
                "overshoot_guard": {"enabled": True, "hard_min": 4.0, "hard_max": 9.0},
                "no_effect": {"enabled": True, "max_count": 3},
                "observe": {
                    "telemetry_period_sec": 2, "window_min_samples": 3,
                    "decision_window_sec": 6, "observe_poll_sec": 2,
                    "min_effect_fraction": 0.25, "stability_max_slope": 0.02,
                    "no_effect_consecutive_limit": 3,
                },
            },
            "ec": {
                "mode": "supervisory_allocator",
                "kp": 30.0, "ki": 0.3, "kd": 0.0,
                "derivative_filter_alpha": 0.35,
                "deadband": 0.1,
                "max_dose_ml": 50.0, "min_interval_sec": 120, "max_integral": 100.0,
                "anti_windup": {"enabled": True},
                "overshoot_guard": {"enabled": True, "hard_min": 0.0, "hard_max": 10.0},
                "no_effect": {"enabled": True, "max_count": 3},
                "observe": {
                    "telemetry_period_sec": 2, "window_min_samples": 3,
                    "decision_window_sec": 6, "observe_poll_sec": 2,
                    "min_effect_fraction": 0.25, "stability_max_slope": 0.05,
                    "no_effect_consecutive_limit": 3,
                },
            },
        },
        "safety": {
            "safe_mode_on_no_effect": True,
            "block_on_active_no_effect_alert": True,
        },
    }
    if ec_component_ratios is not None:
        base["ec_component_ratios"] = ec_component_ratios
    return {"base": base, "phases": phases, "meta": {}}


def _minimal_pid_configs() -> dict[str, object]:
    return {
        "ph": {"config": {"kp": 1.0, "ki": 0.1, "kd": 0.0}},
        "ec": {"config": {"kp": 1.0, "ki": 0.1, "kd": 0.0}},
    }


def _snapshot(
    *,
    ec_target: float = 1.5,
    ec_min: float | None = None,
    ec_max: float | None = None,
    ec_component_ratios: dict[str, float] | None = None,
) -> SimpleNamespace:
    phase_targets: dict[str, object] = {
        "ph": {"target": 5.8},
        "ec": {"target": ec_target},
    }
    if ec_min is not None:
        phase_targets["ec"]["min"] = ec_min  # type: ignore[index]
    if ec_max is not None:
        phase_targets["ec"]["max"] = ec_max  # type: ignore[index]
    return SimpleNamespace(
        workflow_phase="tank_filling",
        zone_id=1,
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
            "startup": {"irr_state_wait_timeout_sec": 4.5},
            "correction": {},
        },
        targets={},
        phase_targets=phase_targets,
        pid_configs=_minimal_pid_configs(),
        process_calibrations={
            "solution_fill": {"transport_delay_sec": 10, "settle_sec": 10},
            "tank_recirc": {"transport_delay_sec": 10, "settle_sec": 10},
            "irrigation": {"transport_delay_sec": 10, "settle_sec": 10},
        },
        correction_config=_minimal_zone_correction_config(
            ec_component_ratios=ec_component_ratios,
        ),
    )


class TestRuntimePerPhaseEcTarget:

    def test_prepare_target_with_ratios(self) -> None:
        """target_ec_prepare = ec_target × npk_share."""
        runtime = resolve_two_tank_runtime(
            _snapshot(
                ec_target=1.5,
                ec_component_ratios={"npk": 44.0, "calcium": 36.0, "magnesium": 12.0, "micro": 8.0},
            )
        )
        assert runtime["target_ec"] == pytest.approx(1.5)
        assert runtime["target_ec_prepare"] == pytest.approx(1.5 * 0.44, abs=0.01)
        assert runtime["npk_ec_share"] == pytest.approx(0.44, abs=0.001)

    def test_prepare_target_without_ratios_equals_full(self) -> None:
        """Без ratios: target_ec_prepare = target_ec (backward compat)."""
        runtime = resolve_two_tank_runtime(_snapshot(ec_target=2.0))
        assert runtime["target_ec"] == pytest.approx(2.0)
        assert runtime["target_ec_prepare"] == pytest.approx(2.0)
        assert runtime["npk_ec_share"] == pytest.approx(1.0)

    def test_prepare_min_max_scaled(self) -> None:
        """Явные ec_min/max масштабируются тем же npk_share."""
        runtime = resolve_two_tank_runtime(
            _snapshot(
                ec_target=2.0,
                ec_min=1.5,
                ec_max=2.5,
                ec_component_ratios={"npk": 50.0, "calcium": 30.0, "magnesium": 10.0, "micro": 10.0},
            )
        )
        share = 0.5
        assert runtime["target_ec_prepare"] == pytest.approx(2.0 * share, abs=0.01)
        assert runtime["target_ec_prepare_min"] == pytest.approx(1.5 * share, abs=0.01)
        assert runtime["target_ec_prepare_max"] == pytest.approx(2.5 * share, abs=0.01)
        # Полный EC target — не масштабирован
        assert runtime["target_ec"] == pytest.approx(2.0)
        assert runtime["target_ec_min"] == pytest.approx(1.5)
        assert runtime["target_ec_max"] == pytest.approx(2.5)

    def test_prepare_target_3_component_model(self) -> None:
        """Старая 3-компонентная модель (без magnesium)."""
        runtime = resolve_two_tank_runtime(
            _snapshot(
                ec_target=1.4,
                ec_component_ratios={"npk": 44.0, "calcium": 44.0, "micro": 12.0},
            )
        )
        assert runtime["target_ec_prepare"] == pytest.approx(1.4 * 0.44, abs=0.01)

    def test_full_ec_target_unchanged_for_irrigation(self) -> None:
        """target_ec (для irrigation) всегда = полный recipe EC."""
        runtime = resolve_two_tank_runtime(
            _snapshot(
                ec_target=1.8,
                ec_component_ratios={"npk": 42.0, "calcium": 36.0, "magnesium": 14.0, "micro": 8.0},
            )
        )
        # target_ec — для полива, не масштабирован
        assert runtime["target_ec"] == pytest.approx(1.8)
