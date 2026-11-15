"""Чистый доменный сервис планирования доз коррекции для AE3-Lite."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
import math
from typing import Any, Mapping, Optional

from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError
from ae3lite.domain.services.phase_utils import normalize_phase_key
from ae3lite.domain.services.correction_ec_planning import plan_ec_dose
from ae3lite.domain.services.correction_ph_planning import plan_ph_dose
from ae3lite.domain.services.correction_dose_plan import DosePlan, EcDoseStep
from ae3lite.domain.services.correction_primitives import (
    _resolve_target_tolerance_bounds,
    _phase_mapping,
    _pid_entry,
    _controller_cfg,
    _strip_last_dose_at,
    _to_utc_naive,
    _positive_float,
    _positive_int,
    _non_negative_float,
    _min_positive,
    _coerce_ratio,
)
from ae3lite.domain.services.correction_controller_config import _resolve_pid_controller_cfg, _merge_pid_deadband
from ae3lite.domain.services.correction_actuator_selection import (
    _assert_distinct_parallel_actuators,
    _ec_actuator_identity,
    _normalize_ec_component_alias,
    _find_ec_component_actuator,
    _resolve_ec_actuator,
)
from ae3lite.domain.services.correction_process_gain import (
    _ec_component_process_gain,
    effective_process_gain,
    _process_gain,
)
from ae3lite.domain.services.correction_pid_math import (
    _retry_after,
    _apply_feedforward_bias,
    _compute_amount_ml,
    _next_pid_state,
    _resolve_derivative_filter_alpha,
    _dose_output_saturated,
    _with_frozen_integral,
    _reset_pid_state_if_inside_bounds,
    _reset_pid_state_if_ph_direction_switched,
)
from ae3lite.domain.services.correction_calibration import (
    _require_solution_volume_l,
    _absorb_dual_calibration_mismatches,
    _resolve_dose_duration,
    _effective_log_context,
    _dose_ml_to_ms,
    _relative_pct_delta,
    _collect_dual_calibration_mismatches,
    _resolve_max_dose_ms,
    resolve_dose_feedback_from_response,
)
from ae3lite.domain.services.correction_math_defaults import (
    _logger,
    _DEFAULT_MAX_EC_DOSE_ML,
    _DEFAULT_MAX_PH_DOSE_ML,
    _DEFAULT_MAX_DOSE_MS,
    _DEFAULT_DERIVATIVE_FILTER_ALPHA,
    _EC_COMPONENT_DEFAULT_ORDER,
    _EC_COMPONENT_LEGACY_ALIAS_MAP,
    _EC_GAIN_COMPONENT_SKIP,
)


class CorrectionPlanner:
    """Доменный planner импульсов дозирования EC/pH."""

    def resolve_deadbands(
        self,
        *,
        current_ph: float,
        current_ec: float,
        target_ph: float,
        target_ec: float,
        correction_config: Mapping[str, Any],
        pid_configs: Mapping[str, Any] | None = None,
        allow_ec: bool = True,
        allow_ph: bool = True,
    ) -> Mapping[str, float]:
        """Resolve the effective PID deadbands used by dose and success checks."""
        pid_configs = pid_configs if isinstance(pid_configs, Mapping) else {}
        ph_deadband = 0.0
        ec_deadband = 0.0
        if allow_ph:
            ph_controller, _, _ = _resolve_pid_controller_cfg(
                controller_cfg=_controller_cfg(correction_config, "ph"),
                pid_configs=pid_configs,
                pid_type="ph",
                gap=abs(float(target_ph) - float(current_ph)),
            )
            ph_deadband = _non_negative_float(ph_controller.get("deadband"), 0.0)
        if allow_ec:
            ec_controller, _, _ = _resolve_pid_controller_cfg(
                controller_cfg=_controller_cfg(correction_config, "ec"),
                pid_configs=pid_configs,
                pid_type="ec",
                gap=abs(float(target_ec) - float(current_ec)),
            )
            ec_deadband = _non_negative_float(ec_controller.get("deadband"), 0.0)
        return {
            "ph": ph_deadband,
            "ec": ec_deadband,
        }

    def is_within_tolerance(
        self,
        *,
        current_ph: float,
        current_ec: float,
        target_ph: float,
        target_ec: float,
        ph_tolerance_pct: float,
        ec_tolerance_pct: float,
        ph_min: float | None = None,
        ph_max: float | None = None,
        ec_min: float | None = None,
        ec_max: float | None = None,
        correction_config: Mapping[str, Any] | None = None,
        pid_configs: Mapping[str, Any] | None = None,
        allow_ec: bool = True,
        allow_ph: bool = True,
    ) -> bool:
        # Runtime correction success must use the same deadband as dose planning.
        # Otherwise a broad prepare tolerance can declare success while the
        # planner would still issue a dose toward the canonical target.
        if correction_config is not None:
            ph_gap = abs(float(target_ph) - float(current_ph))
            ec_gap = abs(float(target_ec) - float(current_ec))
            deadbands = self.resolve_deadbands(
                current_ph=current_ph,
                current_ec=current_ec,
                target_ph=target_ph,
                target_ec=target_ec,
                correction_config=correction_config,
                pid_configs=pid_configs,
                allow_ec=allow_ec,
                allow_ph=allow_ph,
            )
            ph_deadband = deadbands["ph"]
            ec_deadband = deadbands["ec"]
            ph_reached = (not allow_ph) or ph_gap <= ph_deadband
            # Completion is symmetric around the EC setpoint. The actuator gap
            # remains upward-only; an overshoot is handled by recipe bounds /
            # recirculation dilution rather than a negative nutrient dose.
            ec_reached = (not allow_ec) or ec_gap <= ec_deadband
            return ph_reached and ec_reached

        # Compatibility path for callers without controller configuration.
        # Explicit min/max windows remain recipe bounds and observability
        # metadata, not an early-success shortcut at the lower edge.
        ph_lo, ph_hi = _resolve_target_tolerance_bounds(
            target=target_ph,
            tolerance_pct=ph_tolerance_pct,
        )
        ec_lo, ec_hi = _resolve_target_tolerance_bounds(
            target=target_ec,
            tolerance_pct=ec_tolerance_pct,
        )
        return ph_lo <= current_ph <= ph_hi and ec_lo <= current_ec <= ec_hi

    def build_dose_plan(
        self,
        *,
        current_ph: float,
        current_ec: float,
        target_ph: float,
        target_ec: float,
        ph_tolerance_pct: float,
        ec_tolerance_pct: float,
        correction_config: Mapping[str, Any],
        workflow_phase: str | None = None,
        process_calibrations: Optional[Mapping[str, Any]] = None,
        ec_component_policy: Optional[Mapping[str, Any]] = None,
        pid_state: Optional[Mapping[str, Any]] = None,
        pid_configs: Optional[Mapping[str, Any]] = None,
        now: Optional[datetime] = None,
        ph_min: float | None = None,
        ph_max: float | None = None,
        ec_min: float | None = None,
        ec_max: float | None = None,
        ec_actuator: Optional[Mapping[str, Any]] = None,
        ec_actuators: Optional[Mapping[str, Any]] = None,
        ph_up_actuator: Optional[Mapping[str, Any]] = None,
        ph_down_actuator: Optional[Mapping[str, Any]] = None,
        active_component: str | None = None,
        allow_ec: bool = True,
        allow_ph: bool = True,
        freeze_ec_pid: bool = False,
    ) -> DosePlan:
        phase_key = normalize_phase_key(workflow_phase)
        process_cfg = _phase_mapping(process_calibrations).get(phase_key, {})
        process_cfg = process_cfg if isinstance(process_cfg, Mapping) else {}
        pid_state = pid_state if isinstance(pid_state, Mapping) else {}
        pid_configs = pid_configs if isinstance(pid_configs, Mapping) else {}
        now = _to_utc_naive(now or datetime.now(UTC))

        ph_lo, ph_hi = _resolve_target_tolerance_bounds(
            target=target_ph,
            tolerance_pct=ph_tolerance_pct,
        )
        ec_lo, ec_hi = _resolve_target_tolerance_bounds(
            target=target_ec,
            tolerance_pct=ec_tolerance_pct,
        )

        ph_has_explicit_window = ph_min is not None and ph_max is not None
        ec_has_explicit_window = ec_min is not None and ec_max is not None

        predicted_ph = _apply_feedforward_bias(
            current_value=current_ph,
            pid_entry=_pid_entry(pid_state, "ph"),
            now=now,
        )

        controller_ec = _controller_cfg(correction_config, "ec")
        controller_ph = _controller_cfg(correction_config, "ph")
        _require_solution_volume_l(correction_config)

        ec_gap = max(0.0, target_ec - current_ec)
        ph_up_gap = max(0.0, target_ph - predicted_ph)
        ph_down_gap = max(0.0, predicted_ph - target_ph)

        ec_controller_cfg, ec_pid_zone, ec_pid_coeffs = _resolve_pid_controller_cfg(
            controller_cfg=controller_ec,
            pid_configs=pid_configs,
            pid_type="ec",
            gap=ec_gap,
        )
        ph_controller_cfg, ph_pid_zone, ph_pid_coeffs = _resolve_pid_controller_cfg(
            controller_cfg=controller_ph,
            pid_configs=pid_configs,
            pid_type="ph",
            gap=max(ph_up_gap, ph_down_gap),
        )

        ec_deadband = _non_negative_float(ec_controller_cfg.get("deadband"), 0.0)
        ph_deadband = _non_negative_float(ph_controller_cfg.get("deadband"), 0.0)

        pid_updates = _reset_pid_state_if_inside_bounds(
            current_ph=current_ph,
            current_ec=current_ec,
            ph_lo=target_ph - ph_deadband,
            ph_hi=target_ph + ph_deadband,
            ec_lo=target_ec - ec_deadband,
            ec_hi=target_ec + ec_deadband,
            pid_state=pid_state,
            now=now,
            skip_ph=not allow_ph,
            skip_ec=freeze_ec_pid or not allow_ec,
        )

        # Audit B4 fix: a single pH controller serves both ph_up and ph_down
        # directions via ``max(0, target-current)`` / ``max(0, current-target)``
        # gaps. Without an explicit reset on direction switch, integral
        # accumulated while chasing ph_up would linger and distort the first
        # ph_down dose after an overshoot (and vice versa). We detect the
        # direction switch by comparing the last measured pH against the
        # current one across the target setpoint and reset the integrator.
        # If ``_reset_pid_state_if_inside_bounds`` already scheduled a ph
        # reset (inside tolerance window), its keys are kept — both resets
        # converge on the same zeroed state.
        #
        # Crucially we ALSO patch the local ``pid_state`` view so the
        # downstream ``_next_pid_state`` call consumed by ``_compute_amount_ml``
        # starts from the zeroed integral; otherwise the reset would only
        # land in the persisted update dict but the current tick's dose
        # computation would still see the stale integrator value.
        if allow_ph and "ph" not in pid_updates:
            ph_switch_updates = _reset_pid_state_if_ph_direction_switched(
                predicted_ph=predicted_ph,
                target_ph=target_ph,
                pid_state=pid_state,
                now=now,
            )
            if ph_switch_updates:
                pid_updates.update(ph_switch_updates)
                pid_state = {
                    **pid_state,
                    "ph": {
                        **(pid_state.get("ph") if isinstance(pid_state.get("ph"), Mapping) else {}),
                        **ph_switch_updates["ph"],
                    },
                }

        ec_needs = ec_gap > ec_deadband
        ph_needs_up = ph_up_gap > ph_deadband
        ph_needs_down = ph_down_gap > ph_deadband
        if not allow_ec:
            ec_needs = False
        if not allow_ph:
            ph_needs_up = False
            ph_needs_down = False
        # Sequential pipeline: force single-component EC (ignore multi batch mode).
        forced_component = str(active_component or "").strip().lower()
        if forced_component and allow_ec:
            # Override dosing mode for this tick — single component to T_step.
            correction_config = {
                **dict(correction_config),
                "ec_dosing_mode": "single",
                "ec_forced_component": forced_component,
            }

        ec_retry_after = None
        ph_retry_after = None

        ec_component_name = ""
        ec_node_uid = ""
        ec_channel = ""
        ec_amount_ml = 0.0
        ec_requested_ml = 0.0
        ec_duration_ms = 0
        ec_discarded_reason = ""
        ec_discarded_details: Mapping[str, Any] = {}
        ec_clamped_reason = ""
        ec_clamped_details: Mapping[str, Any] = {}
        ec_dose_sequence: tuple[EcDoseStep, ...] = ()

        ph_node_uid = ""
        ph_channel = ""
        ph_amount_ml = 0.0
        ph_requested_ml = 0.0
        ph_duration_ms = 0
        ph_discarded_reason = ""
        ph_discarded_details: Mapping[str, Any] = {}
        ph_clamped_reason = ""
        ph_clamped_details: Mapping[str, Any] = {}
        dual_mismatch_collector: list[dict[str, Any]] = []

        if ec_needs:
            planned_ec = plan_ec_dose(
                ec_clamped_details=ec_clamped_details,
                ec_clamped_reason=ec_clamped_reason,
                ec_component_name=ec_component_name,
                ec_discarded_reason=ec_discarded_reason,
                ec_requested_ml=ec_requested_ml,
                controller_ec=controller_ec,
                correction_config=correction_config,
                current_ec=current_ec,
                dual_mismatch_collector=dual_mismatch_collector,
                ec_actuator=ec_actuator,
                ec_actuators=ec_actuators,
                ec_amount_ml=ec_amount_ml,
                ec_channel=ec_channel,
                ec_component_policy=ec_component_policy,
                ec_controller_cfg=ec_controller_cfg,
                ec_discarded_details=ec_discarded_details,
                ec_dose_sequence=ec_dose_sequence,
                ec_duration_ms=ec_duration_ms,
                ec_gap=ec_gap,
                ec_lo=ec_lo,
                ec_needs=ec_needs,
                ec_node_uid=ec_node_uid,
                ec_pid_zone=ec_pid_zone,
                ec_retry_after=ec_retry_after,
                now=now,
                phase_key=phase_key,
                pid_state=pid_state,
                pid_updates=pid_updates,
                process_cfg=process_cfg,
            )
            ec_amount_ml = planned_ec.ec_amount_ml
            ec_dosing_mode = planned_ec.ec_dosing_mode
            ec_channel = planned_ec.ec_channel
            ec_clamped_details = planned_ec.ec_clamped_details
            ec_clamped_reason = planned_ec.ec_clamped_reason
            ec_component_name = planned_ec.ec_component_name
            ec_discarded_details = planned_ec.ec_discarded_details
            ec_discarded_reason = planned_ec.ec_discarded_reason
            ec_dose_sequence = planned_ec.ec_dose_sequence
            ec_duration_ms = planned_ec.ec_duration_ms
            ec_needs = planned_ec.ec_needs
            ec_node_uid = planned_ec.ec_node_uid
            ec_requested_ml = planned_ec.ec_requested_ml
            ec_retry_after = planned_ec.ec_retry_after
            pid_updates = planned_ec.pid_updates
            dual_mismatch_collector = planned_ec.dual_mismatch_collector

        if ph_needs_up or ph_needs_down:
            planned_ph = plan_ph_dose(
                ph_clamped_details=ph_clamped_details,
                ph_clamped_reason=ph_clamped_reason,
                ph_discarded_details=ph_discarded_details,
                ph_discarded_reason=ph_discarded_reason,
                ph_requested_ml=ph_requested_ml,
                controller_ph=controller_ph,
                correction_config=correction_config,
                dual_mismatch_collector=dual_mismatch_collector,
                now=now,
                ph_amount_ml=ph_amount_ml,
                ph_channel=ph_channel,
                ph_controller_cfg=ph_controller_cfg,
                ph_down_actuator=ph_down_actuator,
                ph_down_gap=ph_down_gap,
                ph_duration_ms=ph_duration_ms,
                ph_hi=ph_hi,
                ph_lo=ph_lo,
                ph_needs_down=ph_needs_down,
                ph_needs_up=ph_needs_up,
                ph_node_uid=ph_node_uid,
                ph_pid_zone=ph_pid_zone,
                ph_retry_after=ph_retry_after,
                ph_up_actuator=ph_up_actuator,
                ph_up_gap=ph_up_gap,
                phase_key=phase_key,
                pid_state=pid_state,
                pid_updates=pid_updates,
                predicted_ph=predicted_ph,
                process_cfg=process_cfg,
            )
            ph_amount_ml = planned_ph.ph_amount_ml
            ph_channel = planned_ph.ph_channel
            ph_clamped_details = planned_ph.ph_clamped_details
            ph_clamped_reason = planned_ph.ph_clamped_reason
            ph_discarded_details = planned_ph.ph_discarded_details
            ph_discarded_reason = planned_ph.ph_discarded_reason
            ph_duration_ms = planned_ph.ph_duration_ms
            ph_needs_down = planned_ph.ph_needs_down
            ph_needs_up = planned_ph.ph_needs_up
            ph_node_uid = planned_ph.ph_node_uid
            ph_requested_ml = planned_ph.ph_requested_ml
            ph_retry_after = planned_ph.ph_retry_after
            pid_updates = planned_ph.pid_updates
            dual_mismatch_collector = planned_ph.dual_mismatch_collector

        retry_after = _min_positive(ec_retry_after, ph_retry_after)
        dead_zone_details = {
            "ec_gap": round(ec_gap, 6),
            "ec_deadband": round(ec_deadband, 6),
            "ec_pid_zone": ec_pid_zone or None,
            "ph_up_gap": round(ph_up_gap, 6),
            "ph_down_gap": round(ph_down_gap, 6),
            "ph_deadband": round(ph_deadband, 6),
            "ph_pid_zone": ph_pid_zone or None,
            "ph_has_explicit_window": ph_has_explicit_window,
            "ec_has_explicit_window": ec_has_explicit_window,
        }
        discarded_reason, discarded_details = _merge_controller_outcome_fields(
            ec_reason=ec_discarded_reason,
            ec_details=ec_discarded_details,
            ph_reason=ph_discarded_reason,
            ph_details=ph_discarded_details,
        )
        clamped_reason, clamped_details = _merge_controller_outcome_fields(
            ec_reason=ec_clamped_reason,
            ec_details=ec_clamped_details,
            ph_reason=ph_clamped_reason,
            ph_details=ph_clamped_details,
        )
        return DosePlan(
            needs_ec=ec_needs,
            ec_component=ec_component_name,
            ec_node_uid=ec_node_uid,
            ec_channel=ec_channel,
            ec_amount_ml=ec_amount_ml,
            ec_requested_ml=ec_requested_ml,
            ec_duration_ms=ec_duration_ms,
            ec_retry_after_sec=ec_retry_after,
            ec_dose_sequence=ec_dose_sequence,
            ec_dosing_mode=ec_dosing_mode if ec_dose_sequence else "single",
            needs_ph_up=ph_needs_up,
            needs_ph_down=ph_needs_down,
            ph_node_uid=ph_node_uid,
            ph_channel=ph_channel,
            ph_amount_ml=ph_amount_ml,
            ph_requested_ml=ph_requested_ml,
            ph_duration_ms=ph_duration_ms,
            ph_retry_after_sec=ph_retry_after,
            retry_after_sec=retry_after,
            dose_discarded_reason=discarded_reason,
            dose_discarded_details=discarded_details,
            dose_clamped_reason=clamped_reason,
            dose_clamped_details=clamped_details,
            dead_zone_details=dead_zone_details,
            pid_state_updates=pid_updates,
            ec_pid_zone=ec_pid_zone,
            ph_pid_zone=ph_pid_zone,
            ec_pid_coeffs=ec_pid_coeffs,
            ph_pid_coeffs=ph_pid_coeffs,
            dual_calibration_mismatches=tuple(dual_mismatch_collector),
        )


def _merge_controller_outcome_fields(
    *,
    ec_reason: str,
    ec_details: Mapping[str, Any],
    ph_reason: str,
    ph_details: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any]]:
    """Merge EC/PH outcome reasons without masking the peer controller.

    Primary ``reason`` stays EC-first for backward-compatible single-field
    consumers; details always expose both sides when present.
    """
    ec_reason = str(ec_reason or "").strip()
    ph_reason = str(ph_reason or "").strip()
    if not ec_reason and not ph_reason:
        return "", {}
    if ec_reason and not ph_reason:
        return ec_reason, {
            **(dict(ec_details) if isinstance(ec_details, Mapping) else {}),
            "ec_reason": ec_reason,
        }
    if ph_reason and not ec_reason:
        return ph_reason, {
            **(dict(ph_details) if isinstance(ph_details, Mapping) else {}),
            "ph_reason": ph_reason,
        }
    return ec_reason, {
        "ec_reason": ec_reason,
        "ph_reason": ph_reason,
        "ec": dict(ec_details) if isinstance(ec_details, Mapping) else {},
        "ph": dict(ph_details) if isinstance(ph_details, Mapping) else {},
    }
