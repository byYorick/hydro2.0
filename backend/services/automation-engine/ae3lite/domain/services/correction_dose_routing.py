"""Pure routing of a planned correction dose; no commands or PID writes."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.services.correction_planner import DosePlan


@dataclass(frozen=True)
class RoutedDose:
    correction: CorrectionState
    selected_action: str
    decision_reason: str


def route_dose_plan(*, corr: CorrectionState, dose_plan: DosePlan) -> RoutedDose | None:
    """Preserve pending-pH priority and the persisted dose metadata shape."""
    # Save dose plan into correction state.
    ec_dose_sequence_json: str | None = None
    if dose_plan.ec_dose_sequence:
        ec_dose_sequence_json = json.dumps(
            [
                {
                    "component": s.component,
                    "node_uid": s.node_uid,
                    "channel": s.channel,
                    "amount_ml": s.amount_ml,
                    "requested_ml": s.requested_ml if s.requested_ml is not None else s.amount_ml,
                    "duration_ms": s.duration_ms,
                }
                for s in dose_plan.ec_dose_sequence
            ],
            separators=(",", ":"),
        )
    elif dose_plan.needs_ec:
        ec_dose_sequence_json = json.dumps(
            {
                "component": dose_plan.ec_component or "single",
                "node_uid": dose_plan.ec_node_uid,
                "channel": dose_plan.ec_channel,
                "amount_ml": dose_plan.ec_amount_ml,
                "requested_ml": dose_plan.ec_requested_ml or dose_plan.ec_amount_ml,
                "duration_ms": dose_plan.ec_duration_ms,
            },
            separators=(",", ":"),
        )
    elif (dose_plan.needs_ph_up or dose_plan.needs_ph_down) and (
        dose_plan.ph_requested_ml and dose_plan.ph_requested_ml != dose_plan.ph_amount_ml
    ):
        ec_dose_sequence_json = json.dumps(
            {
                "_kind": "ph_dose_meta",
                "requested_ml": dose_plan.ph_requested_ml,
                "effective_ml": dose_plan.ph_amount_ml,
            },
            separators=(",", ":"),
        )
    next_corr = replace(
        corr,
        needs_ec=dose_plan.needs_ec,
        ec_node_uid=dose_plan.ec_node_uid,
        ec_channel=dose_plan.ec_channel,
        ec_duration_ms=dose_plan.ec_duration_ms,
        ec_component=dose_plan.ec_component or None,
        ec_amount_ml=dose_plan.ec_amount_ml if dose_plan.ec_amount_ml else None,
        ec_dose_sequence_json=ec_dose_sequence_json,
        ec_current_seq_index=0,
        needs_ph_up=dose_plan.needs_ph_up,
        needs_ph_down=dose_plan.needs_ph_down,
        ph_node_uid=dose_plan.ph_node_uid,
        ph_channel=dose_plan.ph_channel,
        ph_duration_ms=dose_plan.ph_duration_ms,
        ph_amount_ml=dose_plan.ph_amount_ml if dose_plan.ph_amount_ml else None,
    )

    # Pick direction. When the previous observation window left a pending
    # pH dose (prioritize_pending_ph), we must honour it before EC so we
    # don't invalidate the EC observation by shifting pH mid-window.
    prioritize_pending_ph = (corr.needs_ph_up or corr.needs_ph_down) and (
        dose_plan.needs_ph_up or dose_plan.needs_ph_down
    )
    selected_action: str | None = None
    decision_reason: str | None = None
    if prioritize_pending_ph:
        next_corr = replace(next_corr, corr_step="corr_dose_ph")
        selected_action = "ph_up" if dose_plan.needs_ph_up else "ph_down"
        decision_reason = "prioritize_pending_ph_after_ec_observe"
    elif dose_plan.needs_ec:
        next_corr = replace(next_corr, corr_step="corr_dose_ec")
        selected_action = "ec"
        if dose_plan.needs_ph_up or dose_plan.needs_ph_down:
            decision_reason = "ec_first_in_window"
        else:
            decision_reason = "ec_only_needed"
    elif dose_plan.needs_ph_up or dose_plan.needs_ph_down:
        next_corr = replace(next_corr, corr_step="corr_dose_ph")
        selected_action = "ph_up" if dose_plan.needs_ph_up else "ph_down"
        decision_reason = "ph_raise_needed" if dose_plan.needs_ph_up else "ph_lower_needed"
    else:
        return None

    return RoutedDose(correction=next_corr, selected_action=selected_action, decision_reason=decision_reason)
