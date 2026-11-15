"""Stateless post-dose calculations; the handler owns events, PID writes and outcomes."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Mapping

from ae3lite.application.services.correction_event_logger import CorrectionEventLogger
from ae3lite.application.services.correction_observation_reader import ObservationWindow
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.correction_planner import _next_pid_state
from ae3lite.domain.services.observation_analyzer import ObservationAnalyzer, ObservationResult


@dataclass(frozen=True)
class ObservationEvaluation:
    expected_effect: float
    threshold_effect: float
    response: ObservationResult
    is_no_effect: bool
    next_no_effect_count: int
    event_payload: Mapping[str, Any]


def evaluate_observation(
    *,
    corr: CorrectionState,
    pid_type: str,
    sensor_type: str,
    window: ObservationWindow,
    phase_key: str,
    analyzer: ObservationAnalyzer,
) -> ObservationEvaluation:
    observe_cfg = window.observe_cfg
    pid_entry = window.pid_entry
    baseline_value = window.baseline_value
    observed_value = window.summary_value
    last_dose_at = window.last_dose_at
    dose_amount_ml = corr.ec_amount_ml if pid_type == "ec" else corr.ph_amount_ml
    try:
        expected_effect = analyzer.expected_effect(
            pid_type=pid_type,
            corr=corr,
            process_cfg=window.process_cfg,
            pid_entry=pid_entry,
            phase_key=phase_key,
        )
    except ValueError:
        raise TaskExecutionError(
            "corr_process_gain_missing",
            f"Для оценки отклика {pid_type} требуется process gain",
        )
    threshold_effect = expected_effect * float(observe_cfg["min_effect_fraction"])
    response = analyzer.analyze_window(
        samples=window.samples,
        pid_type=pid_type,
        corr=corr,
        baseline_value=baseline_value,
        observed_value=observed_value,
        last_dose_at=last_dose_at,
        dose_amount_ml=float(dose_amount_ml or 0.0),
        threshold_effect=threshold_effect,
        window_min_samples=int(observe_cfg["window_min_samples"]),
    )
    directional_effect = float(response.tail_effect)
    peak_effect = float(response.peak_effect)
    learning_effect = float(response.learning_effect)
    is_no_effect = peak_effect < threshold_effect
    next_no_effect_count = int(pid_entry.get("no_effect_count") or 0) + 1 if is_no_effect else 0
    event_payload = {
        "pid_type": pid_type,
        "sensor_type": sensor_type,
        "observe_seq": CorrectionEventLogger.observe_seq(corr=corr, pid_type=pid_type),
        "dose_amount_ml": dose_amount_ml,
        "baseline_value": baseline_value,
        "observed_value": observed_value,
        "expected_effect": expected_effect,
        "actual_effect": directional_effect,
        "peak_effect": peak_effect,
        "peak_observed_value": response.peak_value,
        "retention_ratio": response.retention_ratio,
        "wave_score": response.wave_score,
        "wave_detected": response.wave_detected,
        "reaction_detected": peak_effect >= threshold_effect,
        "learning_effect": learning_effect,
        "first_reaction_sec": response.first_reaction_sec,
        "threshold_effect": threshold_effect,
        "min_effect_fraction": float(observe_cfg["min_effect_fraction"]),
        "transport_delay_sec": int(observe_cfg["transport_delay_sec"]),
        "settle_sec": int(observe_cfg["settle_sec"]),
        "window_min_samples": int(observe_cfg["window_min_samples"]),
        "no_effect_count_next": next_no_effect_count,
        "is_no_effect": is_no_effect,
    }
    return ObservationEvaluation(
        expected_effect=expected_effect,
        threshold_effect=threshold_effect,
        response=response,
        is_no_effect=is_no_effect,
        next_no_effect_count=next_no_effect_count,
        event_payload=event_payload,
    )


def build_observation_pid_update(
    *,
    corr: CorrectionState,
    pid_type: str,
    window: ObservationWindow,
    evaluation: ObservationEvaluation,
    now: datetime,
    target_ph: float,
    target_ec: float,
    analyzer: ObservationAnalyzer,
) -> dict[str, Any]:
    pid_entry = window.pid_entry
    observed_value = window.summary_value
    dose_amount_ml = corr.ec_amount_ml if pid_type == "ec" else corr.ph_amount_ml
    if pid_type == "ec":
        gap_for_freeze = max(0.0, target_ec - float(observed_value))
    else:
        gap_for_freeze = abs(target_ph - float(observed_value))
    frozen_pid = _next_pid_state(
        kind=pid_type,
        gap=gap_for_freeze,
        current_value=float(observed_value),
        controller_cfg={},
        pid_entry=pid_entry,
        now=now,
        accumulate_integral=False,
    )
    return {
        pid_type: {
            **dict(frozen_pid),
            "no_effect_count": evaluation.next_no_effect_count,
            "stats": analyzer.merge_adaptive_stats(
                pid_entry=pid_entry,
                pid_type=pid_type,
                corr=corr,
                dose_amount_ml=float(dose_amount_ml or 0.0),
                learning_effect=float(evaluation.response.learning_effect),
                expected_effect=evaluation.expected_effect,
                first_reaction_sec=evaluation.response.first_reaction_sec,
                settle_sec=evaluation.response.settle_sec,
                wave_score=evaluation.response.wave_score,
                retention_ratio=evaluation.response.retention_ratio,
            ),
        },
    }


def correction_after_observation(
    *,
    corr: CorrectionState,
    pid_type: str,
    is_no_effect: bool,
    reset_attempt_counters: bool,
) -> CorrectionState:
    # Attempt counters model consecutive no-effect observations only.
    # Any observable reaction resets the correction window counters.
    if is_no_effect:
        next_attempt = corr.attempt + 1
        next_ec_attempt = corr.ec_attempt
        next_ph_attempt = corr.ph_attempt
    elif reset_attempt_counters:
        next_attempt = 0
        next_ec_attempt = 0
        next_ph_attempt = 0
    else:
        next_attempt = corr.attempt
        next_ec_attempt = corr.ec_attempt
        next_ph_attempt = corr.ph_attempt

    preserve_ec_pending = pid_type != "ec" and bool(corr.needs_ec)
    preserve_ph_up_pending = pid_type != "ph" and bool(corr.needs_ph_up)
    preserve_ph_down_pending = pid_type != "ph" and bool(corr.needs_ph_down)

    next_corr = replace(
        corr,
        corr_step="corr_check",
        attempt=next_attempt,
        ec_attempt=next_ec_attempt,
        ph_attempt=next_ph_attempt,
        wait_until=None,
        needs_ec=preserve_ec_pending,
        ec_node_uid=corr.ec_node_uid if preserve_ec_pending else None,
        ec_channel=corr.ec_channel if preserve_ec_pending else None,
        ec_duration_ms=corr.ec_duration_ms if preserve_ec_pending else None,
        ec_component=corr.ec_component if preserve_ec_pending else None,
        ec_amount_ml=corr.ec_amount_ml if preserve_ec_pending else None,
        needs_ph_up=preserve_ph_up_pending,
        needs_ph_down=preserve_ph_down_pending,
        ph_node_uid=corr.ph_node_uid if (preserve_ph_up_pending or preserve_ph_down_pending) else None,
        ph_channel=corr.ph_channel if (preserve_ph_up_pending or preserve_ph_down_pending) else None,
        ph_duration_ms=corr.ph_duration_ms if (preserve_ph_up_pending or preserve_ph_down_pending) else None,
        ph_amount_ml=corr.ph_amount_ml if (preserve_ph_up_pending or preserve_ph_down_pending) else None,
    )
    return next_corr
