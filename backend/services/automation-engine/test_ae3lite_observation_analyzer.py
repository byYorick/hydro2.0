"""Unit-тесты для ObservationAnalyzer (extracted from CorrectionHandler as part of B1).

These exercise the pure observation math in isolation: no handler, no async,
no database, no command gateway. The goal is to lock in the response-analysis
semantics so future extractions (DecisionWindowReader, CorrectionTransitionPolicy)
cannot silently change observation behavior.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.services.observation_analyzer import (
    ObservationAnalyzer,
    ObservationResult,
)


def _corr(
    *,
    ec_amount_ml: float | None = None,
    ph_amount_ml: float | None = None,
    needs_ph_up: bool = False,
    needs_ph_down: bool = False,
) -> CorrectionState:
    """Minimal CorrectionState fixture — only the fields the analyzer touches."""
    return CorrectionState(
        corr_step="corr_wait_ec",
        attempt=0,
        max_attempts=3,
        ec_attempt=0,
        ec_max_attempts=3,
        ph_attempt=0,
        ph_max_attempts=3,
        activated_here=True,
        stabilization_sec=30,
        return_stage_success="next",
        return_stage_fail="fail",
        outcome_success=None,
        needs_ec=ec_amount_ml is not None,
        ec_node_uid=None,
        ec_channel=None,
        ec_duration_ms=None,
        needs_ph_up=needs_ph_up,
        needs_ph_down=needs_ph_down,
        ph_node_uid=None,
        ph_channel=None,
        ph_duration_ms=None,
        wait_until=None,
        ec_amount_ml=ec_amount_ml,
        ph_amount_ml=ph_amount_ml,
    )


def _sample(ts: datetime, value: float) -> dict:
    return {"ts": ts, "value": value}


# ── expected_effect ─────────────────────────────────────────────────


def test_expected_effect_ec_uses_ec_gain_per_ml() -> None:
    analyzer = ObservationAnalyzer()
    effect = analyzer.expected_effect(
        pid_type="ec",
        corr=_corr(ec_amount_ml=2.0),
        process_cfg={"ec_gain_per_ml": 0.3},
    )
    assert effect == pytest.approx(0.6)


def test_expected_effect_ph_up_uses_ph_up_gain() -> None:
    analyzer = ObservationAnalyzer()
    effect = analyzer.expected_effect(
        pid_type="ph",
        corr=_corr(ph_amount_ml=1.0, needs_ph_up=True),
        process_cfg={"ph_up_gain_per_ml": 0.5, "ph_down_gain_per_ml": 99.0},
    )
    assert effect == pytest.approx(0.5)


def test_expected_effect_ph_down_uses_ph_down_gain() -> None:
    analyzer = ObservationAnalyzer()
    effect = analyzer.expected_effect(
        pid_type="ph",
        corr=_corr(ph_amount_ml=1.0, needs_ph_down=True),
        process_cfg={"ph_up_gain_per_ml": 99.0, "ph_down_gain_per_ml": 0.4},
    )
    assert effect == pytest.approx(0.4)


def test_expected_effect_raises_when_gain_missing() -> None:
    analyzer = ObservationAnalyzer()
    with pytest.raises(ValueError):
        analyzer.expected_effect(
            pid_type="ec",
            corr=_corr(ec_amount_ml=1.0),
            process_cfg={},
        )


def test_expected_effect_raises_when_dose_missing() -> None:
    analyzer = ObservationAnalyzer()
    with pytest.raises(ValueError):
        analyzer.expected_effect(
            pid_type="ec",
            corr=_corr(ec_amount_ml=None),
            process_cfg={"ec_gain_per_ml": 0.3},
        )


# ── directional_effect ──────────────────────────────────────────────


def test_directional_effect_ec_uses_upward_delta() -> None:
    analyzer = ObservationAnalyzer()
    effect = analyzer.directional_effect(
        pid_type="ec",
        corr=_corr(ec_amount_ml=1.0),
        baseline_value=1.8,
        observed_value=2.0,
    )
    assert effect == pytest.approx(0.2)


def test_directional_effect_ec_clamps_negative_to_zero() -> None:
    analyzer = ObservationAnalyzer()
    effect = analyzer.directional_effect(
        pid_type="ec",
        corr=_corr(ec_amount_ml=1.0),
        baseline_value=2.0,
        observed_value=1.8,
    )
    assert effect == 0.0


def test_directional_effect_ph_down_is_downward_delta() -> None:
    analyzer = ObservationAnalyzer()
    effect = analyzer.directional_effect(
        pid_type="ph",
        corr=_corr(ph_amount_ml=1.0, needs_ph_down=True),
        baseline_value=6.5,
        observed_value=6.0,
    )
    assert effect == pytest.approx(0.5)


def test_directional_effect_ph_up_is_upward_delta() -> None:
    analyzer = ObservationAnalyzer()
    effect = analyzer.directional_effect(
        pid_type="ph",
        corr=_corr(ph_amount_ml=1.0, needs_ph_up=True),
        baseline_value=5.5,
        observed_value=6.0,
    )
    assert effect == pytest.approx(0.5)


# ── analyze_window ──────────────────────────────────────────────────


def test_analyze_window_empty_samples_falls_back_to_observed_value() -> None:
    """No samples → analyzer uses observed_value for both tail and peak."""
    analyzer = ObservationAnalyzer()
    now = datetime(2026, 3, 10, 12, 0, 0)
    result = analyzer.analyze_window(
        samples=[],
        pid_type="ec",
        corr=_corr(ec_amount_ml=1.0),
        baseline_value=1.8,
        observed_value=2.0,
        last_dose_at=now,
        dose_amount_ml=1.0,
        threshold_effect=0.1,
        window_min_samples=3,
    )
    assert isinstance(result, ObservationResult)
    assert result.tail_effect == pytest.approx(0.2)
    assert result.peak_effect == pytest.approx(0.2)
    assert result.peak_value == pytest.approx(2.0)
    assert result.retention_ratio == 1.0
    assert result.wave_score == 0.0
    assert result.wave_detected is False
    assert result.learning_effect == pytest.approx(0.2)
    assert result.first_reaction_sec is None
    assert result.settle_sec is None


def test_analyze_window_detects_monotonic_rise_without_wave() -> None:
    """Clean monotonic response: peak == tail, retention=1, no wave."""
    analyzer = ObservationAnalyzer()
    base = datetime(2026, 3, 10, 12, 0, 0)
    samples = [
        _sample(base + timedelta(seconds=i * 5), value)
        for i, value in enumerate([1.82, 1.88, 1.94, 1.98, 2.02, 2.04])
    ]
    result = analyzer.analyze_window(
        samples=samples,
        pid_type="ec",
        corr=_corr(ec_amount_ml=1.0),
        baseline_value=1.8,
        observed_value=2.04,
        last_dose_at=base,
        dose_amount_ml=1.0,
        threshold_effect=0.1,
        window_min_samples=3,
    )
    assert result.peak_effect == pytest.approx(0.24)
    assert result.peak_value == pytest.approx(2.04)
    assert result.tail_effect > 0
    # Retention should be close to 1.0 for a clean monotonic rise.
    assert result.retention_ratio >= 0.9
    assert result.wave_detected is False


def test_analyze_window_detects_wave_when_response_decays() -> None:
    """Peak followed by significant decay → wave_detected=True."""
    analyzer = ObservationAnalyzer()
    base = datetime(2026, 3, 10, 12, 0, 0)
    # Rises from 1.8 → 2.2 (peak), then decays back toward 1.85.
    samples = [
        _sample(base + timedelta(seconds=i * 5), value)
        for i, value in enumerate([1.82, 1.95, 2.15, 2.2, 2.0, 1.9, 1.85])
    ]
    result = analyzer.analyze_window(
        samples=samples,
        pid_type="ec",
        corr=_corr(ec_amount_ml=1.0),
        baseline_value=1.8,
        observed_value=1.85,
        last_dose_at=base,
        dose_amount_ml=1.0,
        threshold_effect=0.1,
        window_min_samples=3,
    )
    assert result.peak_value == pytest.approx(2.2)
    assert result.peak_effect == pytest.approx(0.4)
    # Tail is well below peak → retention < 0.5, wave_score above detection threshold.
    assert result.retention_ratio < 0.5
    assert result.wave_score > 0.35
    assert result.wave_detected is True
    # Learning_effect should be bumped above tail by the wave blend (0.35).
    assert result.learning_effect > result.tail_effect


def test_analyze_window_first_reaction_sec_tracks_transport_delay() -> None:
    """first_reaction_sec measures time from dose to first significant effect."""
    analyzer = ObservationAnalyzer()
    dose_at = datetime(2026, 3, 10, 12, 0, 0)
    # First two samples stay near baseline (no reaction yet), then jump.
    samples = [
        _sample(dose_at + timedelta(seconds=5), 1.805),
        _sample(dose_at + timedelta(seconds=10), 1.81),
        _sample(dose_at + timedelta(seconds=20), 1.95),  # first reaction ≥ 0.05
        _sample(dose_at + timedelta(seconds=30), 2.02),
        _sample(dose_at + timedelta(seconds=40), 2.04),
    ]
    result = analyzer.analyze_window(
        samples=samples,
        pid_type="ec",
        corr=_corr(ec_amount_ml=1.0),
        baseline_value=1.8,
        observed_value=2.04,
        last_dose_at=dose_at,
        dose_amount_ml=1.0,
        threshold_effect=0.1,  # trigger = 0.05
        window_min_samples=3,
    )
    # First trigger sample is at t+20.
    assert result.first_reaction_sec == pytest.approx(20.0)
    # Settle window is last_sample - first_reaction = 40 - 20 = 20.
    assert result.settle_sec == pytest.approx(20.0)


def test_analyze_window_zero_dose_zeros_learning_effect() -> None:
    """Guard: learning_effect must not be attributed to a zero-dose observation."""
    analyzer = ObservationAnalyzer()
    base = datetime(2026, 3, 10, 12, 0, 0)
    samples = [
        _sample(base + timedelta(seconds=i * 5), v)
        for i, v in enumerate([1.82, 1.88, 1.94, 1.98])
    ]
    result = analyzer.analyze_window(
        samples=samples,
        pid_type="ec",
        corr=_corr(ec_amount_ml=0.0),
        baseline_value=1.8,
        observed_value=1.98,
        last_dose_at=base,
        dose_amount_ml=0.0,
        threshold_effect=0.05,
        window_min_samples=3,
    )
    assert result.learning_effect == 0.0


# ── merge_adaptive_stats ────────────────────────────────────────────


def test_merge_adaptive_stats_seeds_empty_stats_on_first_observation() -> None:
    """With no prior stats and a successful dose, gains/timing are populated."""
    analyzer = ObservationAnalyzer()
    merged = analyzer.merge_adaptive_stats(
        pid_entry={},
        pid_type="ec",
        corr=_corr(ec_amount_ml=2.0),
        dose_amount_ml=2.0,
        learning_effect=0.5,
        expected_effect=0.6,
        first_reaction_sec=18.0,
        settle_sec=42.0,
        wave_score=0.1,
        retention_ratio=0.9,
    )
    adaptive = merged["adaptive"]
    gains = adaptive["gains"]
    assert "ec_gain_per_ml" in gains
    # learned gain = 0.5 / 2.0 = 0.25; first observation → stored as-is.
    assert gains["ec_gain_per_ml"]["ema"] == pytest.approx(0.25)
    assert gains["ec_gain_per_ml"]["observations"] == 1
    assert adaptive["observations"] == 1
    # effectiveness_ema = learning_effect / expected_effect = 0.5 / 0.6 ≈ 0.833
    assert adaptive["effectiveness_ema"] == pytest.approx(0.5 / 0.6, rel=1e-4)
    timing = adaptive["timing"]
    assert timing["transport_delay_sec_ema"] == pytest.approx(18.0)
    assert timing["settle_sec_ema"] == pytest.approx(42.0)


def test_merge_adaptive_stats_ema_updates_existing_gain() -> None:
    """Second observation blends into the EMA (alpha=0.2)."""
    analyzer = ObservationAnalyzer()
    prior = {
        "stats": {
            "adaptive": {
                "gains": {
                    "ec_gain_per_ml": {"ema": 0.3, "observations": 5},
                },
                "observations": 5,
                "retention_ema": 0.8,
                "wave_score_ema": 0.1,
            }
        }
    }
    merged = analyzer.merge_adaptive_stats(
        pid_entry=prior,
        pid_type="ec",
        corr=_corr(ec_amount_ml=2.0),
        dose_amount_ml=2.0,
        learning_effect=0.5,  # learned gain = 0.25
        expected_effect=0.6,
        first_reaction_sec=None,
        settle_sec=None,
        wave_score=0.1,
        retention_ratio=0.9,
    )
    # EMA: 0.3 * 0.8 + 0.25 * 0.2 = 0.24 + 0.05 = 0.29
    assert merged["adaptive"]["gains"]["ec_gain_per_ml"]["ema"] == pytest.approx(0.29)
    assert merged["adaptive"]["gains"]["ec_gain_per_ml"]["observations"] == 6
    assert merged["adaptive"]["observations"] == 6


def test_merge_adaptive_stats_skips_gain_learning_when_dose_is_zero() -> None:
    analyzer = ObservationAnalyzer()
    prior = {
        "stats": {
            "adaptive": {
                "gains": {
                    "ec_gain_per_ml": {"ema": 0.3, "observations": 5},
                },
                "observations": 5,
            }
        }
    }
    merged = analyzer.merge_adaptive_stats(
        pid_entry=prior,
        pid_type="ec",
        corr=_corr(ec_amount_ml=0.0),
        dose_amount_ml=0.0,
        learning_effect=0.0,
        expected_effect=0.0,
        first_reaction_sec=None,
        settle_sec=None,
        wave_score=0.0,
        retention_ratio=0.0,
    )
    # gain unchanged
    assert merged["adaptive"]["gains"]["ec_gain_per_ml"] == {"ema": 0.3, "observations": 5}


# ── expected_cross_coupling_ph ──────────────────────────────────────


def test_expected_cross_coupling_ph_returns_zero_when_not_configured() -> None:
    analyzer = ObservationAnalyzer()
    value = analyzer.expected_cross_coupling_ph(
        corr=_corr(ec_amount_ml=2.0),
        process_cfg={},
    )
    assert value == 0.0


def test_expected_cross_coupling_ph_multiplies_ec_dose_by_gain() -> None:
    analyzer = ObservationAnalyzer()
    value = analyzer.expected_cross_coupling_ph(
        corr=_corr(ec_amount_ml=2.0),
        process_cfg={"ph_per_ec_ml": -0.05},
    )
    # Returns raw gain*dose (handler decides how to apply it as feedforward).
    assert value == pytest.approx(-0.1)


def test_expected_cross_coupling_ph_returns_zero_when_ec_dose_missing() -> None:
    analyzer = ObservationAnalyzer()
    value = analyzer.expected_cross_coupling_ph(
        corr=_corr(ec_amount_ml=None),
        process_cfg={"ph_per_ec_ml": -0.05},
    )
    assert value == 0.0
