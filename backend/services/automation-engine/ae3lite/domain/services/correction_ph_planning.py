"""Pure PH dose planning for one normalized measurement/config snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services.correction_calibration import _absorb_dual_calibration_mismatches, _resolve_dose_duration
from ae3lite.domain.services.correction_pid_math import _compute_amount_ml, _retry_after, _with_frozen_integral
from ae3lite.domain.services.correction_primitives import _pid_entry, _positive_int


@dataclass(frozen=True)
class PHDosePlanningResult:
    ph_amount_ml: float
    ph_channel: str
    ph_clamped_details: Mapping[str, Any]
    ph_clamped_reason: str
    ph_discarded_details: Mapping[str, Any]
    ph_discarded_reason: str
    ph_duration_ms: int
    ph_needs_down: bool
    ph_needs_up: bool
    ph_node_uid: str
    ph_requested_ml: float
    ph_retry_after: Optional[int]
    pid_updates: dict[str, Any]
    dual_mismatch_collector: list[dict[str, Any]]


def plan_ph_dose(
    *,
    controller_ph: Mapping[str, Any],
    correction_config: Mapping[str, Any],
    dual_mismatch_collector: list[dict[str, Any]],
    now: Optional[datetime],
    ph_amount_ml: float,
    ph_channel: str,
    ph_controller_cfg: Mapping[str, Any],
    ph_down_actuator: Optional[Mapping[str, Any]],
    ph_down_gap: float,
    ph_duration_ms: int,
    ph_hi: float,
    ph_lo: float,
    ph_needs_down: bool,
    ph_needs_up: bool,
    ph_node_uid: str,
    ph_pid_zone: str,
    ph_retry_after: Optional[int],
    ph_up_actuator: Optional[Mapping[str, Any]],
    ph_up_gap: float,
    phase_key: str,
    pid_state: Optional[Mapping[str, Any]],
    pid_updates: dict[str, Any],
    predicted_ph: float,
    process_cfg: Mapping[str, Any],
    ph_clamped_details: Mapping[str, Any],
    ph_clamped_reason: str,
    ph_discarded_details: Mapping[str, Any],
    ph_discarded_reason: str,
    ph_requested_ml: float,
) -> PHDosePlanningResult:
    pid_updates = dict(pid_updates)
    dual_mismatch_collector = list(dual_mismatch_collector)
    ph_retry_after = _retry_after(
        pid_entry=_pid_entry(pid_state, "ph"),
        min_interval_sec=_positive_int(controller_ph.get("min_interval_sec"), 0),
        now=now,
    )
    if ph_retry_after is None:
        default_channel = (
            str(
                (
                    correction_config.get("dose_ph_up_channel")
                    if ph_needs_up
                    else correction_config.get("dose_ph_down_channel")
                )
                or ""
            )
            .strip()
            .lower()
        )
        resolved_ph = ph_up_actuator if ph_needs_up else ph_down_actuator
        if resolved_ph is None:
            raise PlannerConfigurationError(
                f"Требуется коррекция pH, но не найден actuator для channel={default_channel}"
            )
        ph_node_uid = str(resolved_ph["node_uid"])
        ph_channel = str(resolved_ph["channel"])
        calibration = resolved_ph.get("calibration")
        if not isinstance(calibration, Mapping):
            raise PlannerConfigurationError(
                f"Для насоса дозирования PH требуется calibration (channel={ph_channel}, node={ph_node_uid})"
            )
        ph_gap = ph_up_gap if ph_needs_up else ph_down_gap
        (
            ph_amount_ml,
            ph_pid_update,
            ph_planner_discard_reason,
            ph_planner_discard_details,
        ) = _compute_amount_ml(
            kind="ph_up" if ph_needs_up else "ph_down",
            gap=ph_gap,
            lower_bound=ph_lo if ph_needs_up else ph_hi,
            current_value=predicted_ph,
            controller_cfg=ph_controller_cfg,
            correction_config=correction_config,
            process_cfg=process_cfg,
            phase_key=phase_key,
            calibration=calibration,
            pid_entry=_pid_entry(pid_state, "ph"),
            now=now,
        )
        ph_integral_before = float(_pid_entry(pid_state, "ph").get("integral") or 0.0)
        if ph_pid_update:
            if ph_pid_zone:
                ph_pid_update = {**ph_pid_update, "current_zone": ph_pid_zone}
            pid_updates["ph"] = ph_pid_update
        ph_requested_ml = ph_amount_ml
        ph_amount_ml, ph_requested_ml, ph_duration_ms, ph_duration_reason, ph_duration_details = _resolve_dose_duration(
            requested_ml=ph_amount_ml,
            calibration=calibration,
            correction_config=correction_config,
        )
        _absorb_dual_calibration_mismatches(dual_mismatch_collector, ph_duration_details)
        if ph_duration_reason == "clamped_to_max_dose_ms" and isinstance(ph_pid_update, Mapping) and ph_pid_update:
            ph_pid_update = _with_frozen_integral(
                pid_update=ph_pid_update,
                integral_before=ph_integral_before,
                controller_cfg=ph_controller_cfg,
            )
            if ph_pid_zone:
                ph_pid_update = {**ph_pid_update, "current_zone": ph_pid_zone}
            pid_updates["ph"] = ph_pid_update
        if ph_planner_discard_reason:
            ph_discarded_reason = ph_planner_discard_reason
            ph_discarded_details = ph_planner_discard_details
        elif ph_duration_reason == "clamped_to_max_dose_ms":
            ph_clamped_reason = ph_duration_reason
            ph_clamped_details = ph_duration_details
        elif ph_duration_reason:
            ph_discarded_reason = ph_duration_reason
            ph_discarded_details = ph_duration_details
        ph_needs_up = ph_needs_up and ph_duration_ms > 0
        ph_needs_down = ph_needs_down and ph_duration_ms > 0
    else:
        ph_needs_up = False
        ph_needs_down = False
    return PHDosePlanningResult(
        ph_amount_ml=ph_amount_ml,
        ph_channel=ph_channel,
        ph_clamped_details=ph_clamped_details,
        ph_clamped_reason=ph_clamped_reason,
        ph_discarded_details=ph_discarded_details,
        ph_discarded_reason=ph_discarded_reason,
        ph_duration_ms=ph_duration_ms,
        ph_needs_down=ph_needs_down,
        ph_needs_up=ph_needs_up,
        ph_node_uid=ph_node_uid,
        ph_requested_ml=ph_requested_ml,
        ph_retry_after=ph_retry_after,
        pid_updates=pid_updates,
        dual_mismatch_collector=dual_mismatch_collector,
    )
