"""Correction domain policy: pid math."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Mapping

from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services.correction_math_defaults import (
    _DEFAULT_DERIVATIVE_FILTER_ALPHA,
    _DEFAULT_MAX_EC_DOSE_ML,
    _DEFAULT_MAX_PH_DOSE_ML,
)
from ae3lite.domain.services.correction_primitives import _positive_float, _to_utc_naive
from ae3lite.domain.services.correction_process_gain import effective_process_gain


def _retry_after(
    *,
    pid_entry: Mapping[str, Any],
    min_interval_sec: int,
    now: datetime,
) -> int | None:
    if min_interval_sec <= 0:
        return None
    last_dose_at = pid_entry.get("last_dose_at")
    if not isinstance(last_dose_at, datetime):
        return None
    elapsed = (_to_utc_naive(now) - _to_utc_naive(last_dose_at)).total_seconds()
    remaining = float(min_interval_sec) - elapsed
    if remaining <= 0:
        return None
    return max(1, int(math.ceil(remaining)))


def _apply_feedforward_bias(
    *,
    current_value: float,
    pid_entry: Mapping[str, Any],
    now: datetime,
) -> float:
    """Shift current pH prediction by the EC→pH cross-coupling bias, if active.

    Audit B5 simplification: previously the predicate also required
    ``last_correction_kind == "ec"`` in the pH pid_state row — a semantic
    overload of a field that otherwise stored the last pH correction side
    ("ph_up"/"ph_down"). That check is now redundant: the bias is authored
    *only* by ``_run_dose_ec`` (which sets ``feedforward_bias + hold_until``)
    and cleared by the EC observe step and by ``_run_dose_ph`` (explicit
    zero-out). So the single source of truth for "bias active?" is
    ``feedforward_bias != 0 AND hold_until > now``.
    """
    hold_until = pid_entry.get("hold_until")
    if not isinstance(hold_until, datetime):
        return current_value
    if _to_utc_naive(hold_until) <= _to_utc_naive(now):
        return current_value
    bias = float(pid_entry.get("feedforward_bias") or 0.0)
    if bias == 0.0:
        return current_value
    return current_value + bias


def _compute_amount_ml(
    *,
    kind: str,
    gap: float,
    lower_bound: float,
    current_value: float,
    controller_cfg: Mapping[str, Any],
    correction_config: Mapping[str, Any],
    process_cfg: Mapping[str, Any],
    phase_key: str,
    calibration: Mapping[str, Any],
    pid_entry: Mapping[str, Any],
    now: datetime,
) -> tuple[float, Mapping[str, Any], str, Mapping[str, Any]]:
    forced_component = None
    if kind == "ec":
        raw_forced = str(correction_config.get("ec_forced_component") or "").strip()
        forced_component = raw_forced or None
    gain = effective_process_gain(
        kind=kind,
        process_cfg=process_cfg,
        pid_entry=pid_entry,
        phase_key=phase_key,
        component=forced_component,
    )
    integral_before = float(pid_entry.get("integral") or 0.0)
    pid_update = _next_pid_state(
        kind=kind,
        gap=gap,
        current_value=current_value,
        controller_cfg=controller_cfg,
        pid_entry=pid_entry,
        now=now,
    )
    if gain is not None:
        output_units = (
            float(controller_cfg.get("kp") or 0.0) * gap
            + float(controller_cfg.get("ki") or 0.0) * float(pid_update["integral"])
            + float(controller_cfg.get("kd") or 0.0) * float(pid_update["prev_derivative"])
        )
        dose_ml = output_units / gain if gain > 0 else 0.0
    else:
        raise PlannerConfigurationError(f"Для {kind} в режиме observation-driven correction требуется process gain")

    uncapped_ml = dose_ml
    saturated = False

    if gain is not None and gap > 0:
        # A single pulse must not exceed the modelled dose required to reach the
        # nearest allowed bound/target. Without this cap, kp>1 PI output can
        # command a dose that overshoots the window in one step and causes
        # acid/base ping-pong during recirculation.
        capped = min(dose_ml, gap / gain)
        if capped < dose_ml:
            saturated = True
        dose_ml = capped

    gap_cap_ml = (gap / gain) if (gain is not None and gain > 0 and gap > 0) else None
    min_effective_ml = max(0.0, float(calibration.get("min_effective_ml") or 0.0))
    discard_reason = ""
    discard_details: Mapping[str, Any] = {}
    if dose_ml > 0 and min_effective_ml > 0:
        dose_ml = max(dose_ml, min_effective_ml)
        # Symmetric safety: re-apply gap/gain cap so the min_effective_ml bump
        # cannot push a single pulse past the target window. Mirrors the
        # multi_sequential branch; without it, single-dose could overshoot and
        # cause ping-pong around the setpoint.
        if gap_cap_ml is not None:
            if dose_ml > gap_cap_ml:
                saturated = True
            dose_ml = min(dose_ml, gap_cap_ml)
        if dose_ml > 0 and dose_ml < min_effective_ml:
            discard_reason = f"{kind}_min_effective_exceeds_cap"
            discard_details = {
                "kind": kind,
                "min_effective_ml": round(min_effective_ml, 6),
                "gap_cap_ml": round(gap_cap_ml, 6) if gap_cap_ml is not None else None,
                "capped_ml": round(float(dose_ml), 6),
            }
            dose_ml = 0.0
            saturated = True

    controller_max = _positive_float(controller_cfg.get("max_dose_ml"), 0.0)
    if kind == "ec":
        contract_max = _positive_float(correction_config.get("max_ec_dose_ml"), _DEFAULT_MAX_EC_DOSE_ML)
    else:
        contract_max = _positive_float(correction_config.get("max_ph_dose_ml"), _DEFAULT_MAX_PH_DOSE_ML)
    max_ml = min(controller_max, contract_max) if controller_max > 0 else contract_max
    if dose_ml > max_ml:
        saturated = True
    dose_ml = min(dose_ml, max_ml)
    dose_ml = round(max(0.0, dose_ml), 4)
    if _dose_output_saturated(uncapped_ml=uncapped_ml, capped_ml=dose_ml):
        saturated = True
    if saturated:
        # Conditional integration / anti-windup: do not persist ΔI when the
        # actuator command is clamped by gap/gain or max_dose_ml.
        pid_update = _with_frozen_integral(
            pid_update=pid_update,
            integral_before=integral_before,
            controller_cfg=controller_cfg,
        )
    return dose_ml, pid_update, discard_reason, discard_details


def _next_pid_state(
    *,
    kind: str,
    gap: float,
    current_value: float,
    controller_cfg: Mapping[str, Any],
    pid_entry: Mapping[str, Any],
    now: datetime,
    accumulate_integral: bool = True,
) -> Mapping[str, Any]:
    """Advance PID state for one measurement tick.

    ``accumulate_integral=False`` advances the measurement clock (and D-term)
    without adding ``gap * dt`` — used to skip hold/observe dead time so the
    integrator does not wind up during transport delay. Handler already touches
    ``last_measurement_at`` after observe; this flag makes the same contract
    available to the planner/tests without a separate code path.
    """
    now = _to_utc_naive(now)
    integral = float(pid_entry.get("integral") or 0.0)
    prev_error = float(pid_entry.get("prev_error") or 0.0)
    prev_derivative = float(pid_entry.get("prev_derivative") or 0.0)
    last_measurement_at = pid_entry.get("last_measurement_at")
    alpha = _resolve_derivative_filter_alpha(controller_cfg)
    derivative = 0.0
    if isinstance(last_measurement_at, datetime):
        dt = (now - _to_utc_naive(last_measurement_at)).total_seconds()
        if dt > 0:
            if accumulate_integral:
                integral += gap * dt
            raw_derivative = (gap - prev_error) / dt
            derivative = alpha * raw_derivative + (1.0 - alpha) * prev_derivative
    max_integral = float(controller_cfg.get("max_integral") or 0.0)
    if max_integral > 0:
        integral = max(-max_integral, min(max_integral, integral))
    return {
        "integral": round(integral, 6),
        "prev_error": round(gap, 6),
        "prev_derivative": round(derivative, 6),
        "last_measurement_at": now,
        "last_measured_value": round(current_value, 6),
        "last_correction_kind": "ec" if kind == "ec" else "ph",
    }


def _resolve_derivative_filter_alpha(controller_cfg: Mapping[str, Any]) -> float:
    raw = controller_cfg.get("derivative_filter_alpha")
    if raw is None:
        return _DEFAULT_DERIVATIVE_FILTER_ALPHA
    try:
        alpha = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_DERIVATIVE_FILTER_ALPHA
    return min(1.0, max(0.0, alpha))


def _dose_output_saturated(*, uncapped_ml: float, capped_ml: float) -> bool:
    """True when a positive PID output was reduced by a hard dose cap."""
    if uncapped_ml <= 0:
        return False
    return float(capped_ml) + 1e-9 < float(uncapped_ml)


def _with_frozen_integral(
    *,
    pid_update: Mapping[str, Any],
    integral_before: float,
    controller_cfg: Mapping[str, Any],
) -> dict[str, Any]:
    """Conditional integration: keep pre-tick integral when the dose saturates."""
    frozen = float(integral_before)
    max_integral = float(controller_cfg.get("max_integral") or 0.0)
    if max_integral > 0:
        frozen = max(-max_integral, min(max_integral, frozen))
    return {**dict(pid_update), "integral": round(frozen, 6)}


def _reset_pid_state_if_inside_bounds(
    *,
    current_ph: float,
    current_ec: float,
    ph_lo: float,
    ph_hi: float,
    ec_lo: float,
    ec_hi: float,
    pid_state: Mapping[str, Any],
    now: datetime,
    skip_ph: bool = False,
    skip_ec: bool = False,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if (not skip_ph) and ph_lo <= current_ph <= ph_hi and "ph" in pid_state:
        updates["ph"] = {
            "integral": 0.0,
            "prev_error": 0.0,
            "prev_derivative": 0.0,
            # Сбросить last_measurement_at, чтобы следующий out-of-bounds tick
            # считал dt от текущего момента, а не от устаревшей отметки времени,
            # иначе при повторном входе можно получить всплеск интеграла.
            "last_measurement_at": now,
            "current_zone": "dead",
        }
    if (not skip_ec) and ec_lo <= current_ec <= ec_hi and "ec" in pid_state:
        updates["ec"] = {
            "integral": 0.0,
            "prev_error": 0.0,
            "prev_derivative": 0.0,
            "last_measurement_at": now,
            "current_zone": "dead",
        }
    return updates


def _reset_pid_state_if_ph_direction_switched(
    *,
    predicted_ph: float,
    target_ph: float,
    pid_state: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Reset pH integral when the PID crosses its target into the opposite direction.

    Audit fix (B4): a single ``pid_state["ph"]`` row serves both ph_up and
    ph_down directions via non-negative gaps. The integrator accumulates
    ``gap * dt`` regardless of which direction owns the gap, so residual
    integral from chasing ph_up would linger after an overshoot and cause
    the first ph_down dose to be skewed (and symmetrically for down→up).

    Detection: we compare the previous ``last_measured_value`` against the
    current predicted pH, both expressed as signed offset from the target
    (``value - target``). A sign flip means the controller crossed the
    setpoint and is now in the opposite-direction regime — reset.

    Returns an empty dict when the row is absent, the last measurement is
    unknown, one side is exactly at the setpoint, or the direction did not
    change. Caller merges the result into ``pid_updates`` *after*
    ``_reset_pid_state_if_inside_bounds`` so the inside-bounds branch keeps
    priority (it leads to the same zeroed state).
    """
    ph_entry = pid_state.get("ph") if isinstance(pid_state.get("ph"), Mapping) else None
    if not ph_entry:
        return {}
    last_measured = ph_entry.get("last_measured_value")
    if last_measured is None:
        return {}
    try:
        prev_signed = float(last_measured) - float(target_ph)
        curr_signed = float(predicted_ph) - float(target_ph)
    except (TypeError, ValueError):
        return {}
    # Sign flip strictly required: same-sign or at-setpoint → no switch.
    if prev_signed * curr_signed >= 0:
        return {}
    return {
        "ph": {
            "integral": 0.0,
            "prev_error": 0.0,
            "prev_derivative": 0.0,
            "last_measurement_at": now,
            "current_zone": "direction_switch",
        }
    }
