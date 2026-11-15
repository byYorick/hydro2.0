"""Post-dose calculation boundaries without command or persistence dependencies."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from ae3lite.application.services.correction_observation_finalizer import (
    build_observation_pid_update,
    correction_after_observation,
    evaluate_observation,
)
from ae3lite.application.services.correction_observation_reader import ObservationWindow
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.observation_analyzer import ObservationAnalyzer, ObservationResult

NOW = datetime(2026, 11, 15, 12)


def correction():
    corr = CorrectionState.build_default(
        corr_step='corr_wait_ec',
        max_attempts=5,
        ec_max_attempts=5,
        ph_max_attempts=5,
        activated_here=False,
        stabilization_sec=60,
        return_stage_success='ready',
        return_stage_fail='failed',
    )
    return replace(
        corr,
        attempt=3,
        ec_attempt=2,
        ph_attempt=1,
        needs_ec=True,
        ec_amount_ml=2,
        ec_node_uid='ec',
        ec_channel='ec',
        ec_duration_ms=1000,
        needs_ph_up=True,
        ph_amount_ml=2,
        ph_node_uid='ph',
        ph_channel='ph',
        ph_duration_ms=1000,
        wait_until=NOW,
    )


def window(values=(1.0, 1.0, 1.0), *, previous_count=2):
    return ObservationWindow(
        samples=[{'ts': NOW - timedelta(seconds=8 - i * 4), 'value': value} for i, value in enumerate(values)],
        summary_value=values[-1],
        baseline_value=1.0,
        last_dose_at=NOW - timedelta(seconds=20),
        observe_cfg=dict(
            min_effect_fraction=0.25, transport_delay_sec=6, settle_sec=4, window_min_samples=3, no_effect_limit=3
        ),
        pid_entry=dict(
            no_effect_count=previous_count,
            integral=1.5,
            prev_error=0.2,
            last_measurement_at=NOW - timedelta(seconds=100),
            stats={'adaptive': {'observations': 5}, 'feedforward_bias': 0.3},
        ),
        process_cfg=dict(ec_gain_per_ml=0.2, ph_up_gain_per_ml=0.2, ph_down_gain_per_ml=0.2),
    )


def evaluate(corr, observation, *, pid_type='ec', analyzer=None):
    return evaluate_observation(
        corr=corr,
        window=observation,
        pid_type=pid_type,
        sensor_type=pid_type.upper(),
        phase_key='solution_fill',
        analyzer=analyzer or ObservationAnalyzer(),
    )


def test_wave_peak_counts_as_effect_when_tail_has_returned_to_baseline():
    result = evaluate(correction(), window((1.0, 1.8, 1.0)))
    assert result.response.tail_effect == 0.0
    assert result.response.peak_effect == pytest.approx(0.8)
    assert result.is_no_effect is False
    assert result.next_no_effect_count == 0
    assert result.event_payload['actual_effect'] == 0.0
    assert result.event_payload['reaction_detected'] is True


@pytest.mark.parametrize('missing', ['gain', 'dose'])
def test_missing_process_gain_or_dose_keeps_fail_closed_error(missing):
    corr, observation = correction(), window()
    if missing == 'gain':
        observation = replace(observation, process_cfg={})
    else:
        corr = replace(corr, ec_amount_ml=None)
    with pytest.raises(TaskExecutionError) as error:
        evaluate(corr, observation)
    assert error.value.code == 'corr_process_gain_missing'


def test_peak_equal_to_threshold_is_a_reaction():
    analyzer = Mock(spec=ObservationAnalyzer)
    analyzer.expected_effect.return_value = 0.4
    analyzer.analyze_window.return_value = ObservationResult(
        tail_effect=0.0,
        peak_effect=0.1,
        peak_value=1.1,
        retention_ratio=0.0,
        wave_score=1.0,
        wave_detected=True,
        learning_effect=0.05,
        first_reaction_sec=6,
        settle_sec=None,
    )
    result = evaluate(correction(), window(), analyzer=analyzer)
    assert result.threshold_effect == 0.1
    assert result.is_no_effect is False
    assert result.next_no_effect_count == 0


@pytest.mark.parametrize('pid_type', ['ec', 'ph'])
def test_observation_pid_update_freezes_integral_and_does_not_inflate_learning(pid_type):
    corr, observation = correction(), window()
    baseline = deepcopy(observation.pid_entry)
    result = evaluate(corr, observation, pid_type=pid_type)
    update = build_observation_pid_update(
        corr=corr,
        pid_type=pid_type,
        window=observation,
        evaluation=result,
        now=NOW,
        target_ec=2.0,
        target_ph=6.0,
        analyzer=ObservationAnalyzer(),
    )[pid_type]
    assert update['integral'] == 1.5
    assert update['last_measurement_at'] == NOW
    assert update['last_measured_value'] == 1.0
    assert update['no_effect_count'] == 3
    assert update['stats']['adaptive']['observations'] == 5
    assert update['stats']['feedforward_bias'] == 0.3
    assert observation.pid_entry == baseline


@pytest.mark.parametrize('pid_type', ['ec', 'ph'])
@pytest.mark.parametrize('is_no_effect', [False, True])
def test_next_state_preserves_pending_opposite_dose_and_resets_only_on_reaction(pid_type, is_no_effect):
    corr = correction()
    next_corr = correction_after_observation(
        corr=corr,
        pid_type=pid_type,
        is_no_effect=is_no_effect,
        reset_attempt_counters=True,
    )
    assert next_corr.corr_step == 'corr_check'
    assert next_corr.wait_until is None
    assert (next_corr.attempt, next_corr.ec_attempt, next_corr.ph_attempt) == ((4, 2, 1) if is_no_effect else (0, 0, 0))
    if pid_type == 'ec':
        assert not next_corr.needs_ec and next_corr.ec_amount_ml is None
        assert next_corr.needs_ph_up and next_corr.ph_amount_ml == 2
        assert next_corr.ph_node_uid == 'ph'
    else:
        assert not next_corr.needs_ph_up and next_corr.ph_amount_ml is None
        assert next_corr.needs_ec and next_corr.ec_amount_ml == 2
        assert next_corr.ec_node_uid == 'ec'
    assert corr.attempt == 3 and corr.wait_until == NOW


def test_reset_policy_can_preserve_attempt_counters_after_reaction():
    result = correction_after_observation(
        corr=correction(),
        pid_type='ec',
        is_no_effect=False,
        reset_attempt_counters=False,
    )
    assert (result.attempt, result.ec_attempt, result.ph_attempt) == (3, 2, 1)
