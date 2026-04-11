"""Чистый доменный анализатор observation window коррекции pH/EC.

Extracted from `ae3lite.application.handlers.correction.CorrectionHandler`
as part of the God-Object decomposition (audit finding B1). This module owns
the pure response-analysis logic: directional effect, peak/tail detection,
wave-score, retention ratio, learning effect and the adaptive EMA stats that
feed back into `CorrectionPlanner._process_gain`.

No I/O, no async, no database, no command gateway — purely samples → metrics.
The handler injects an instance and delegates observation math to it, so the
logic is unit-testable in isolation and the handler stays smaller.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Any, Mapping

from ae3lite.domain.entities.workflow_state import CorrectionState


# ── Named constants (replacing the inline magic numbers from handler) ──
#
# The handler previously scattered these values inline with no documentation
# of why they were chosen. We pin them here so a single change propagates and
# so future tuning has a documented home.

#: Minimum peak_effect fraction of threshold at which a sample qualifies as a
#: "first reaction" marker, used to estimate transport delay.
_FIRST_REACTION_TRIGGER_FRACTION: float = 0.5

#: wave_score threshold above which we conclude the response peaked and
#: decayed (oscillation / overshoot / dilution wave), rather than settling.
_WAVE_DETECTED_SCORE_THRESHOLD: float = 0.35

#: Fraction of (peak - tail) added to tail_effect when a wave is detected.
#: Pulls `learning_effect` upward so adaptive gain is not penalised for a
#: pulse that actually moved the system before the wave decay ate the tail.
_WAVE_LEARNING_BLEND: float = 0.35

#: EMA alpha for adaptive gain / timing learning.
_ADAPTIVE_EMA_ALPHA: float = 0.2


@dataclass(frozen=True)
class ObservationResult:
    """Structured output of :meth:`ObservationAnalyzer.analyze_window`."""

    tail_effect: float
    peak_effect: float
    peak_value: float
    retention_ratio: float
    wave_score: float
    wave_detected: bool
    learning_effect: float
    first_reaction_sec: float | None
    settle_sec: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "tail_effect": self.tail_effect,
            "peak_effect": self.peak_effect,
            "peak_value": self.peak_value,
            "retention_ratio": self.retention_ratio,
            "wave_score": self.wave_score,
            "wave_detected": self.wave_detected,
            "learning_effect": self.learning_effect,
            "first_reaction_sec": self.first_reaction_sec,
            "settle_sec": self.settle_sec,
        }


class ObservationAnalyzer:
    """Pure observation-window analysis for correction cycles."""

    # ── Public API ──────────────────────────────────────────────────

    def expected_effect(
        self,
        *,
        pid_type: str,
        corr: CorrectionState,
        process_cfg: Mapping[str, Any],
    ) -> float:
        """Compute the dose-response prediction for a freshly issued pulse.

        Raises ValueError when the required process gain or dose amount is
        missing; the handler translates this into a TaskExecutionError.
        """
        if pid_type == "ec":
            gain = self._coerce_float(process_cfg.get("ec_gain_per_ml"))
            amount_ml = corr.ec_amount_ml
        elif corr.needs_ph_up:
            gain = self._coerce_float(process_cfg.get("ph_up_gain_per_ml"))
            amount_ml = corr.ph_amount_ml
        else:
            gain = self._coerce_float(process_cfg.get("ph_down_gain_per_ml"))
            amount_ml = corr.ph_amount_ml
        if gain is None or gain <= 0 or amount_ml is None or amount_ml <= 0:
            raise ValueError(
                f"Для оценки отклика {pid_type} требуется process gain и положительный amount_ml"
            )
        return float(gain) * float(amount_ml)

    def directional_effect(
        self,
        *,
        pid_type: str,
        corr: CorrectionState,
        baseline_value: float,
        observed_value: float,
    ) -> float:
        """Signed displacement from baseline, clamped to the "desired" direction."""
        if pid_type == "ec":
            return max(0.0, observed_value - baseline_value)
        if corr.needs_ph_up:
            return max(0.0, observed_value - baseline_value)
        return max(0.0, baseline_value - observed_value)

    def expected_cross_coupling_ph(
        self, *, corr: CorrectionState, process_cfg: Mapping[str, Any],
    ) -> float:
        """Predicted pH shift from a freshly issued EC dose (ph_per_ec_ml).

        Returns 0.0 if the coupling is not configured or the EC dose was not
        recorded — the handler relies on this to populate feedforward_bias.
        """
        gain = self._coerce_float(process_cfg.get("ph_per_ec_ml"))
        if gain is None or corr.ec_amount_ml is None:
            return 0.0
        return float(gain) * float(corr.ec_amount_ml)

    def analyze_window(
        self,
        *,
        samples: Any,
        pid_type: str,
        corr: CorrectionState,
        baseline_value: float,
        observed_value: float,
        last_dose_at: datetime,
        dose_amount_ml: float,
        threshold_effect: float,
        window_min_samples: int,
    ) -> ObservationResult:
        """Compute peak / tail / wave / retention / learning metrics for a window.

        Mirrors the semantics of the extracted handler method one-for-one so
        the handler tests that exercise this path through run_wait_ec/run_wait_ph
        continue to pass without modification.
        """
        sample_list = [
            item
            for item in (list(samples) if isinstance(samples, (list, tuple)) else [])
            if item.get("value") is not None
        ]
        if not sample_list:
            tail_effect = self.directional_effect(
                pid_type=pid_type,
                corr=corr,
                baseline_value=baseline_value,
                observed_value=observed_value,
            )
            return ObservationResult(
                tail_effect=tail_effect,
                peak_effect=tail_effect,
                peak_value=observed_value,
                retention_ratio=1.0 if tail_effect > 0 else 0.0,
                wave_score=0.0,
                wave_detected=False,
                learning_effect=tail_effect,
                first_reaction_sec=None,
                settle_sec=None,
            )

        tail_size = min(
            len(sample_list),
            max(window_min_samples, math.ceil(len(sample_list) / 2)),
        )
        tail_values = [float(item["value"]) for item in sample_list[-tail_size:]]
        tail_value = float(median(tail_values))
        directional_effects = [
            self.directional_effect(
                pid_type=pid_type,
                corr=corr,
                baseline_value=baseline_value,
                observed_value=float(item["value"]),
            )
            for item in sample_list
        ]
        peak_index = max(
            range(len(directional_effects)), key=directional_effects.__getitem__
        )
        peak_effect = float(directional_effects[peak_index])
        peak_value = float(sample_list[peak_index]["value"])
        tail_effect = self.directional_effect(
            pid_type=pid_type,
            corr=corr,
            baseline_value=baseline_value,
            observed_value=tail_value,
        )
        retention_ratio = (
            0.0 if peak_effect <= 0 else max(0.0, min(1.0, tail_effect / peak_effect))
        )
        wave_score = (
            0.0 if peak_effect <= 0 else max(0.0, min(1.0, 1.0 - retention_ratio))
        )
        wave_detected = (
            peak_effect >= threshold_effect
            and wave_score >= _WAVE_DETECTED_SCORE_THRESHOLD
        )
        learning_effect = (
            tail_effect
            if not wave_detected
            else (tail_effect + ((peak_effect - tail_effect) * _WAVE_LEARNING_BLEND))
        )

        trigger_effect = max(threshold_effect * _FIRST_REACTION_TRIGGER_FRACTION, 1e-6)
        first_reaction_sec: float | None = None
        settle_sec: float | None = None
        first_reaction_ts: datetime | None = None
        for sample, effect in zip(sample_list, directional_effects):
            ts = sample.get("ts")
            if effect >= trigger_effect and isinstance(ts, datetime):
                first_reaction_ts = ts
                break
        last_sample_ts = sample_list[-1].get("ts")
        if isinstance(first_reaction_ts, datetime):
            first_reaction_sec = max(0.0, (first_reaction_ts - last_dose_at).total_seconds())
            if isinstance(last_sample_ts, datetime):
                settle_sec = max(0.0, (last_sample_ts - first_reaction_ts).total_seconds())

        if dose_amount_ml <= 0:
            learning_effect = 0.0

        return ObservationResult(
            tail_effect=float(tail_effect),
            peak_effect=peak_effect,
            peak_value=peak_value,
            retention_ratio=retention_ratio,
            wave_score=wave_score,
            wave_detected=wave_detected,
            learning_effect=float(max(0.0, learning_effect)),
            first_reaction_sec=first_reaction_sec,
            settle_sec=settle_sec,
        )

    def merge_adaptive_stats(
        self,
        *,
        pid_entry: Mapping[str, Any],
        pid_type: str,
        corr: CorrectionState,
        dose_amount_ml: float,
        learning_effect: float,
        expected_effect: float,
        first_reaction_sec: float | None,
        settle_sec: float | None,
        wave_score: float,
        retention_ratio: float,
    ) -> Mapping[str, Any]:
        """Fold this observation into the running adaptive EMA stats.

        Contract: the existing observations counter is incremented once per
        call (matches the pre-refactor handler behavior). Audit finding B10
        tracks a follow-up fix for observations-inflation; we keep the same
        semantics here so this refactor is behavior-preserving.
        """
        stats = dict(pid_entry.get("stats")) if isinstance(pid_entry.get("stats"), Mapping) else {}
        adaptive = dict(stats.get("adaptive")) if isinstance(stats.get("adaptive"), Mapping) else {}
        gains = dict(adaptive.get("gains")) if isinstance(adaptive.get("gains"), Mapping) else {}
        timing = dict(adaptive.get("timing")) if isinstance(adaptive.get("timing"), Mapping) else {}

        gain_key = (
            "ec_gain_per_ml"
            if pid_type == "ec"
            else ("ph_up_gain_per_ml" if corr.needs_ph_up else "ph_down_gain_per_ml")
        )
        gain_entry = dict(gains.get(gain_key)) if isinstance(gains.get(gain_key), Mapping) else {}
        gain_observations = int(gain_entry.get("observations") or 0)
        if dose_amount_ml > 0 and learning_effect > 0:
            learned_gain = learning_effect / dose_amount_ml
            gain_entry["ema"] = self._ema(gain_entry.get("ema"), learned_gain, gain_observations)
            gain_entry["observations"] = gain_observations + 1
            gains[gain_key] = gain_entry

        adaptive["gains"] = gains
        adaptive["effectiveness_ema"] = self._ema_ratio(
            adaptive.get("effectiveness_ema"),
            0.0 if expected_effect <= 0 else learning_effect / expected_effect,
            int(adaptive.get("observations") or 0),
        )
        adaptive["retention_ema"] = self._ema_ratio(
            adaptive.get("retention_ema"),
            retention_ratio,
            int(adaptive.get("observations") or 0),
        )
        adaptive["wave_score_ema"] = self._ema_ratio(
            adaptive.get("wave_score_ema"),
            wave_score,
            int(adaptive.get("observations") or 0),
        )
        adaptive["observations"] = int(adaptive.get("observations") or 0) + 1

        timing_observations = int(timing.get("observations") or 0)
        if first_reaction_sec is not None:
            timing["transport_delay_sec_ema"] = self._ema(
                timing.get("transport_delay_sec_ema"),
                first_reaction_sec,
                timing_observations,
            )
            timing_observations += 1
        if settle_sec is not None:
            timing["settle_sec_ema"] = self._ema(
                timing.get("settle_sec_ema"),
                settle_sec,
                max(0, timing_observations - 1),
            )
        timing["observations"] = max(
            timing_observations,
            int(timing.get("observations") or 0),
            1,
        )
        adaptive["timing"] = timing

        stats["adaptive"] = adaptive
        return stats

    # ── Private helpers ─────────────────────────────────────────────

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _ema(
        previous: Any,
        current: float,
        observations: int,
        alpha: float = _ADAPTIVE_EMA_ALPHA,
    ) -> float:
        try:
            prev_value = float(previous)
        except (TypeError, ValueError):
            prev_value = current
        if observations <= 0:
            return round(current, 6)
        return round((prev_value * (1.0 - alpha)) + (current * alpha), 6)

    @staticmethod
    def _ema_ratio(previous: Any, current: float, observations: int) -> float:
        return max(0.0, min(1.0, ObservationAnalyzer._ema(previous, current, observations)))
