"""runtime plan correction: one cohesive policy."""

from __future__ import annotations

from typing import Any, Mapping

from ae3lite.config.runtime_plan_values import _MAX_CORRECTION_ATTEMPTS
from ae3lite.config.runtime_plan_values_policy import (
    _normalize_component_policy,
    _normalize_controllers,
    _require_float,
    _require_int,
    _require_str,
    _resolve_bounded_int,
    _resolve_float,
    _to_mapping,
)


def _build_recirc_dilute_cfg(
    *,
    tank_recirc_cfg: Mapping[str, Any],
    base_cfg: Mapping[str, Any],
) -> dict[str, Any]:
    """zone.correction.recirc.* dilute-on-overshoot defaults."""
    recirc = _to_mapping(tank_recirc_cfg.get("recirc")) or _to_mapping(base_cfg.get("recirc"))
    return {
        "ec_overshoot_dilute_pct": float(
            _resolve_float(recirc.get("ec_overshoot_dilute_pct"), default=15.0, minimum=1.0, maximum=100.0)
        ),
        "dilute_pulse_sec": int(_resolve_bounded_int(recirc.get("dilute_pulse_sec"), 10, 1, 600)),
        "dilute_max_attempts": int(_resolve_bounded_int(recirc.get("dilute_max_attempts"), 3, 0, 20)),
        "dilute_settle_sec": int(_resolve_bounded_int(recirc.get("dilute_settle_sec"), 30, 0, 3600)),
    }


def _build_correction_cfg(
    phase_cfg: Mapping[str, Any],
    pump_calibration_cfg: Mapping[str, Any],
) -> dict[str, Any]:
    timing_cfg = _to_mapping(phase_cfg.get("timing"))
    dosing_cfg = _to_mapping(phase_cfg.get("dosing"))
    retry_cfg = _to_mapping(phase_cfg.get("retry"))
    controllers_cfg = _normalize_controllers(phase_cfg.get("controllers"))

    return {
        "dose_ec_channel": _require_str(dosing_cfg.get("dose_ec_channel"), path="dosing.dose_ec_channel"),
        "dose_ph_up_channel": _require_str(dosing_cfg.get("dose_ph_up_channel"), path="dosing.dose_ph_up_channel"),
        "dose_ph_down_channel": _require_str(
            dosing_cfg.get("dose_ph_down_channel"), path="dosing.dose_ph_down_channel"
        ),
        "max_ec_dose_ml": _require_float(
            dosing_cfg.get("max_ec_dose_ml"),
            path="dosing.max_ec_dose_ml",
            minimum=1.0,
            maximum=500.0,
        ),
        "max_ph_dose_ml": _require_float(
            dosing_cfg.get("max_ph_dose_ml"),
            path="dosing.max_ph_dose_ml",
            minimum=0.5,
            maximum=200.0,
        ),
        "stabilization_sec": _require_int(
            timing_cfg.get("stabilization_sec"),
            path="timing.stabilization_sec",
            minimum=0,
        ),
        "max_ec_correction_attempts": _require_int(
            retry_cfg.get("max_ec_correction_attempts"),
            path="retry.max_ec_correction_attempts",
            minimum=1,
            maximum=_MAX_CORRECTION_ATTEMPTS,
        ),
        "max_ph_correction_attempts": _require_int(
            retry_cfg.get("max_ph_correction_attempts"),
            path="retry.max_ph_correction_attempts",
            minimum=1,
            maximum=_MAX_CORRECTION_ATTEMPTS,
        ),
        "prepare_recirculation_max_attempts": _require_int(
            retry_cfg.get("prepare_recirculation_max_attempts"),
            path="retry.prepare_recirculation_max_attempts",
            minimum=1,
        ),
        "prepare_recirculation_max_correction_attempts": _require_int(
            retry_cfg.get("prepare_recirculation_max_correction_attempts"),
            path="retry.prepare_recirculation_max_correction_attempts",
            minimum=1,
            maximum=_MAX_CORRECTION_ATTEMPTS,
        ),
        "telemetry_stale_retry_sec": _require_int(
            retry_cfg.get("telemetry_stale_retry_sec"),
            path="retry.telemetry_stale_retry_sec",
            minimum=1,
            maximum=3600,
        ),
        "decision_window_retry_sec": _require_int(
            retry_cfg.get("decision_window_retry_sec"),
            path="retry.decision_window_retry_sec",
            minimum=1,
            maximum=3600,
        ),
        "low_water_retry_sec": _require_int(
            retry_cfg.get("low_water_retry_sec"),
            path="retry.low_water_retry_sec",
            minimum=1,
            maximum=3600,
        ),
        "solution_volume_l": _require_float(
            dosing_cfg.get("solution_volume_l"),
            path="dosing.solution_volume_l",
            minimum=1.0,
            maximum=10000.0,
        ),
        "controllers": controllers_cfg,
        "pump_calibration": dict(pump_calibration_cfg),
        "ec_component_policy": _normalize_component_policy(phase_cfg.get("ec_component_policy")),
        "ec_dosing_mode": _require_str(
            phase_cfg.get("ec_dosing_mode")
            if phase_cfg.get("ec_dosing_mode") is not None
            else dosing_cfg.get("ec_dosing_mode"),
            path="dosing.ec_dosing_mode",
        ),
        "ec_component_ratios": _to_mapping(phase_cfg.get("ec_component_ratios")),
        "ec_excluded_components": tuple(
            str(x).strip().lower() for x in (phase_cfg.get("ec_excluded_components") or ()) if str(x).strip()
        ),
        "actuators": {},
    }


def _build_prepare_tolerance_cfg(
    phase_cfg: Mapping[str, Any],
) -> dict[str, Any]:
    phase_tolerance = _to_mapping(_to_mapping(phase_cfg.get("tolerance")).get("prepare_tolerance"))
    return {
        "ph_pct": _require_float(
            phase_tolerance.get("ph_pct"),
            path="tolerance.prepare_tolerance.ph_pct",
            minimum=0.1,
            maximum=100.0,
        ),
        "ec_pct": _require_float(
            phase_tolerance.get("ec_pct"),
            path="tolerance.prepare_tolerance.ec_pct",
            minimum=0.1,
            maximum=100.0,
        ),
    }
