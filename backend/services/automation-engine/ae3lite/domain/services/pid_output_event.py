"""Pure builder for PID_OUTPUT zone events.

Extracted from ``CorrectionHandler._maybe_emit_pid_output_zone_event`` as
part of the God-Object decomposition (audit finding B1). Builds the
``detail`` payload that populates the "Логи PID" tab in the frontend:
proportional / integral / derivative term breakdown plus metadata about
the tick (current value, target, dt_seconds since last measurement).

This is a pure domain function — no async, no I/O, no handler coupling.
The handler calls it, gets a dict (or ``None`` to skip), and writes the
event itself via the zone_events sink.

Why here, not in ``ObservationAnalyzer``:
  * Observation analyzer reasons about *post-dose* reaction (peak/tail/wave).
  * PID output event snapshots the *pre-dose* plan (P/I/D term math from
    the freshly built DosePlan). Different concern, separate module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional

from ae3lite.domain.services.correction_planner import DosePlan


def build_pid_output_detail(
    *,
    corr_step: str,
    dose_plan: DosePlan,
    pid_state_before: Mapping[str, Any],
    current_ph: float,
    current_ec: float,
    target_ph: float,
    target_ec: float,
    now: datetime,
) -> Optional[dict[str, Any]]:
    """Render the ``detail`` dict for a PID_OUTPUT zone event, or ``None`` to skip.

    Skips (returns ``None``) when:
      * ``corr_step`` is neither ``corr_dose_ec`` nor ``corr_dose_ph``
      * the DosePlan's respective direction is not scheduled for dispatch
      * amount_ml is non-positive
      * the planner did not attach pid_state_updates for that pid_type

    The returned dict is the raw, unfiltered detail — callers typically
    pass it through ``with_runtime_event_contract`` and drop ``None`` values
    before persisting.
    """
    if corr_step == "corr_dose_ec":
        if not dose_plan.needs_ec or dose_plan.ec_amount_ml <= 0:
            return None
        return _build_direction_detail(
            pid_type="ec",
            dose_plan=dose_plan,
            coeffs=dose_plan.ec_pid_coeffs if isinstance(dose_plan.ec_pid_coeffs, Mapping) else {},
            pid_zone=dose_plan.ec_pid_zone,
            output_ml=float(dose_plan.ec_amount_ml),
            current_value=current_ec,
            target_value=target_ec,
            pid_state_before=pid_state_before,
            now=now,
        )
    if corr_step == "corr_dose_ph":
        if not (dose_plan.needs_ph_up or dose_plan.needs_ph_down) or dose_plan.ph_amount_ml <= 0:
            return None
        return _build_direction_detail(
            pid_type="ph",
            dose_plan=dose_plan,
            coeffs=dose_plan.ph_pid_coeffs if isinstance(dose_plan.ph_pid_coeffs, Mapping) else {},
            pid_zone=dose_plan.ph_pid_zone,
            output_ml=float(dose_plan.ph_amount_ml),
            current_value=current_ph,
            target_value=target_ph,
            pid_state_before=pid_state_before,
            now=now,
        )
    return None


def _build_direction_detail(
    *,
    pid_type: str,
    dose_plan: DosePlan,
    coeffs: Mapping[str, Any],
    pid_zone: str,
    output_ml: float,
    current_value: float,
    target_value: float,
    pid_state_before: Mapping[str, Any],
    now: datetime,
) -> Optional[dict[str, Any]]:
    """Build one direction's PID_OUTPUT detail.

    Shared between EC and pH branches: reads the freshly updated PID state
    (``dose_plan.pid_state_updates[pid_type]``) to snapshot ``gap / integral /
    derivative`` at the moment the dose was committed, then multiplies by
    the active PID coefficients to materialize the P/I/D term breakdown.
    """
    pu = dose_plan.pid_state_updates.get(pid_type)
    if not isinstance(pu, Mapping):
        return None
    gap = float(pu.get("prev_error") or 0.0)
    integral = float(pu.get("integral") or 0.0)
    deriv = float(pu.get("prev_derivative") or 0.0)
    kp = float(coeffs.get("kp") or 0.0)
    ki = float(coeffs.get("ki") or 0.0)
    kd = float(coeffs.get("kd") or 0.0)
    p_term = kp * gap
    i_term = ki * integral
    d_term = kd * deriv
    zone_str = str(pid_zone or pu.get("current_zone") or "").strip()
    prev = pid_state_before.get(pid_type) if isinstance(pid_state_before.get(pid_type), Mapping) else {}
    dt_sec = _pid_output_dt_seconds(prev.get("last_measurement_at"), now)
    return {
        "type": pid_type,
        "zone_state": zone_str or None,
        "output": output_ml,
        "error": gap,
        "proportional_term": round(p_term, 6),
        "integral_term": round(i_term, 6),
        "derivative_term": round(d_term, 6),
        "dt_seconds": dt_sec,
        "current": current_value,
        "target": target_value,
    }


def _pid_output_dt_seconds(last_measurement_at: Any, now: datetime) -> Optional[float]:
    """Elapsed seconds between the previous measurement and ``now``.

    Returns ``None`` when there's no valid previous timestamp (first tick
    of a correction window or a reset just happened). Normalises tz-aware
    inputs to UTC-naive before subtraction so the arithmetic is safe
    regardless of caller's tz conventions.
    """
    if not isinstance(last_measurement_at, datetime):
        return None
    prev = _normalize_ts(last_measurement_at)
    cur = _normalize_ts(now)
    if prev is None or cur is None:
        return None
    return max(0.0, (cur - prev).total_seconds())


def _normalize_ts(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    from datetime import timezone
    return value.astimezone(timezone.utc).replace(tzinfo=None)
