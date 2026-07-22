"""Pipeline FSM helpers for CorrectionHandler (sequential nutrient)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Optional

from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.services.nutrient_pipeline import (
    PIPELINE_PHASE_FILL_CA,
    ComponentTargets,
    advance_pipeline_phase,
    component_for_phase,
    ec_overshoot_requires_dilute,
    is_ec_step_phase,
    is_ph_gate_phase,
    pipeline_phase_for_index,
)


def pipeline_dose_flags(corr: CorrectionState) -> dict[str, Any]:
    """Return allow_ec / allow_ph / freeze_ec_pid / active_component for planner."""
    phase = str(getattr(corr, "pipeline_phase", None) or "").strip().lower()
    component = str(getattr(corr, "active_component", None) or "").strip().lower() or None
    if not phase:
        return {
            "allow_ec": True,
            "allow_ph": True,
            "freeze_ec_pid": bool(getattr(corr, "ec_pid_frozen", False)),
            "active_component": component,
        }
    if phase in {PIPELINE_PHASE_FILL_CA, "fill_calcium"}:
        return {
            "allow_ec": True,
            "allow_ph": False,
            "freeze_ec_pid": False,
            "active_component": "calcium",
        }
    if phase in {"irrigation_ph", "irrigation"}:
        return {
            "allow_ec": False,
            "allow_ph": True,
            "freeze_ec_pid": True,
            "active_component": None,
        }
    if is_ph_gate_phase(phase):
        return {
            "allow_ec": False,
            "allow_ph": True,
            "freeze_ec_pid": True,
            "active_component": None,
        }
    if is_ec_step_phase(phase):
        return {
            "allow_ec": True,
            "allow_ph": False,
            "freeze_ec_pid": False,
            "active_component": component or component_for_phase(phase),
        }
    return {
        "allow_ec": True,
        "allow_ph": True,
        "freeze_ec_pid": bool(getattr(corr, "ec_pid_frozen", False)),
        "active_component": component,
    }


def step_targets_reached(
    *,
    corr: CorrectionState,
    current_ph: float,
    current_ec: float,
    target_ph: float,
    target_ec: float,
    ph_tol_pct: float,
    ec_tol_pct: float,
    planner: Any,
) -> bool:
    """Whether the *active pipeline step* is within tolerance."""
    flags = pipeline_dose_flags(corr)
    if flags["allow_ec"] and not flags["allow_ph"]:
        # EC-only step: ignore pH
        return planner.is_within_tolerance(
            current_ph=target_ph,
            current_ec=current_ec,
            target_ph=target_ph,
            target_ec=target_ec,
            ph_tolerance_pct=ph_tol_pct,
            ec_tolerance_pct=ec_tol_pct,
        )
    if flags["allow_ph"] and not flags["allow_ec"]:
        return planner.is_within_tolerance(
            current_ph=current_ph,
            current_ec=target_ec,
            target_ph=target_ph,
            target_ec=target_ec,
            ph_tolerance_pct=ph_tol_pct,
            ec_tolerance_pct=ec_tol_pct,
        )
    return planner.is_within_tolerance(
        current_ph=current_ph,
        current_ec=current_ec,
        target_ph=target_ph,
        target_ec=target_ec,
        ph_tolerance_pct=ph_tol_pct,
        ec_tolerance_pct=ec_tol_pct,
    )


def maybe_advance_pipeline(
    *,
    corr: CorrectionState,
    current_stage: str,
) -> tuple[CorrectionState, bool, Optional[dict[str, Any]]]:
    """Advance pipeline after step success.

    Returns (next_corr, finished, event_payload).
    finished=True means whole correction window should complete.
    """
    stage = str(current_stage or "").strip().lower()
    phase = str(getattr(corr, "pipeline_phase", None) or "").strip().lower()

    if stage == "solution_fill_check" or phase in {PIPELINE_PHASE_FILL_CA, "fill_calcium"}:
        # Fill calcium done → exit correction (parent decides prepare vs ready)
        return corr, True, {"from_phase": phase or PIPELINE_PHASE_FILL_CA, "to_phase": None, "reason": "fill_ca_done"}

    if stage == "irrigation_check":
        return corr, True, {"from_phase": phase or "irrigation_ph", "to_phase": None, "reason": "irrigation_ph_done"}

    if stage != "prepare_recirculation_check" and not phase.startswith("recirc_"):
        return corr, True, None

    next_phase = advance_pipeline_phase(phase if phase.startswith("recirc_") else None)
    if next_phase is None:
        return corr, True, {"from_phase": phase, "to_phase": None, "reason": "pipeline_complete"}

    prev_component = component_for_phase(phase) if phase else None
    next_component = component_for_phase(next_phase)
    # Reset EC I/D when entering an EC step with a different component than the
    # previous EC step (ph-gate has component=None → treat as switch).
    # fill_ca → recirc_ca is a new correction window (not this advance path).
    reset_ec_pid = bool(next_component) and (prev_component != next_component)

    next_corr = replace(
        corr,
        pipeline_phase=next_phase,
        active_component=next_component,
        ec_pid_frozen=is_ph_gate_phase(next_phase),
        corr_step="corr_check",
        needs_ec=False,
        needs_ph_up=False,
        needs_ph_down=False,
        ec_duration_ms=None,
        ph_duration_ms=None,
        wait_until=None,
    )
    payload = {
        "from_phase": phase or pipeline_phase_for_index(0),
        "to_phase": next_phase,
        "from_component": prev_component,
        "to_component": next_component,
        "reset_ec_pid": reset_ec_pid,
    }
    return next_corr, False, payload


def should_dilute(
    *,
    corr: CorrectionState,
    runtime: Any,
    current_ec: float,
    t_step: float,
    current_stage: str,
) -> bool:
    stage = str(current_stage or "").strip().lower()
    if stage != "prepare_recirculation_check":
        return False
    if not is_ec_step_phase(getattr(corr, "pipeline_phase", None)):
        return False
    recirc = getattr(runtime, "recirc", None)
    if recirc is None:
        return False
    pct = float(getattr(recirc, "ec_overshoot_dilute_pct", 15) or 15)
    max_attempts = int(getattr(recirc, "dilute_max_attempts", 3) or 3)
    attempts = int(getattr(corr, "dilute_attempts", 0) or 0)
    if attempts >= max_attempts:
        return False
    return ec_overshoot_requires_dilute(
        current_ec=current_ec,
        t_step=t_step,
        overshoot_pct=pct,
    )


def load_targets(corr: CorrectionState) -> ComponentTargets | None:
    return ComponentTargets.from_json(getattr(corr, "component_targets_json", None))
