"""Общий контракт manual-control для публичного API AE3-Lite."""

from __future__ import annotations

import logging
from typing import Final

logger = logging.getLogger(__name__)


AVAILABLE_CONTROL_MODES: Final[tuple[str, ...]] = ("auto", "semi", "manual")

SOLUTION_CHANGE_ABORT_STEP: Final[str] = "solution_change_abort"

SOLUTION_CHANGE_GATE_CONFIRM_BY_STAGE: Final[dict[str, str]] = {
    "await_operator_drain_confirm": "solution_drain_confirm",
    "await_operator_refill_confirm": "solution_refill_confirm",
}

SOLUTION_CHANGE_GATE_STEPS: Final[frozenset[str]] = frozenset({
    "solution_drain_confirm",
    "solution_refill_confirm",
    SOLUTION_CHANGE_ABORT_STEP,
})

_ALLOWED_MANUAL_STEPS_BY_STAGE: Final[dict[str, list[str]]] = {
    "startup": [
        "clean_fill_start",
        "solution_fill_start",
        # (b) force: пропустить clean_max check и принудительно начать solution_fill.
        # Agronomist в manual подтверждает что вода в баке уже есть.
        "force_solution_fill_start",
    ],
    # Стопы доступны на активной task (CONTROL_MODES_SPEC §5.1) — в т.ч. command-stage.
    "clean_fill_start": ["clean_fill_stop", SOLUTION_CHANGE_ABORT_STEP],
    "clean_fill_check": ["clean_fill_stop", SOLUTION_CHANGE_ABORT_STEP],
    "solution_fill_start": ["solution_fill_stop", SOLUTION_CHANGE_ABORT_STEP],
    "solution_fill_check": ["solution_fill_stop", SOLUTION_CHANGE_ABORT_STEP],
    "prepare_recirculation_start": ["prepare_recirculation_stop"],
    "prepare_recirculation_check": ["prepare_recirculation_stop"],
    "irrigation_start": ["irrigation_stop"],
    "irrigation_check": ["irrigation_stop"],
    "irrigation_recovery_check": ["irrigation_recovery_stop"],
    "manual_hold": [],
    "await_operator_drain_confirm": ["solution_drain_confirm", SOLUTION_CHANGE_ABORT_STEP],
    "await_operator_refill_confirm": ["solution_refill_confirm", SOLUTION_CHANGE_ABORT_STEP],
    "solution_drain_check": [SOLUTION_CHANGE_ABORT_STEP],
}


def normalize_control_mode(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in AVAILABLE_CONTROL_MODES:
        return normalized
    if normalized:
        logger.warning("AE3 получил неизвестный control_mode=%s; используется auto", normalized)
    return "auto"


def solution_change_gate_confirm_step_for_stage(stage: object) -> str | None:
    normalized = str(stage or "").strip()
    return SOLUTION_CHANGE_GATE_CONFIRM_BY_STAGE.get(normalized)


def allowed_manual_steps_for_stage(stage: object) -> list[str]:
    normalized_stage = str(stage or "").strip()
    return list(_ALLOWED_MANUAL_STEPS_BY_STAGE.get(normalized_stage, ()))


def resolve_manual_control_stage(
    *,
    current_stage: object,
    pending_manual_step: object = None,
) -> str:
    """Stage для allowed_manual_steps: в manual_hold — return check-stage."""
    normalized_stage = str(current_stage or "").strip()
    if normalized_stage == "manual_hold":
        from ae3lite.application.handlers.flow_path_guard import decode_manual_hold_return_stage

        return_stage = decode_manual_hold_return_stage(pending_manual_step)
        if return_stage:
            return return_stage
    return normalized_stage


def allowed_manual_steps_for_workflow(
    *,
    current_stage: object,
    pending_manual_step: object = None,
) -> list[str]:
    effective_stage = resolve_manual_control_stage(
        current_stage=current_stage,
        pending_manual_step=pending_manual_step,
    )
    return allowed_manual_steps_for_stage(effective_stage)


def allowed_manual_steps_for_task(
    *,
    task_type: object,
    control_mode: object,
    current_stage: object,
    pending_manual_step: object = None,
) -> list[str]:
    """Gate steps solution_change доступны даже в control_mode=auto (semi-auto v1)."""
    normalized_task_type = str(task_type or "").strip().lower()
    normalized_mode = normalize_control_mode(control_mode)
    steps = allowed_manual_steps_for_workflow(
        current_stage=current_stage,
        pending_manual_step=pending_manual_step,
    )
    if normalized_task_type == "solution_change" and normalized_mode == "auto":
        gate_steps = [
            step
            for step in steps
            if step in SOLUTION_CHANGE_GATE_STEPS
        ]
        return gate_steps
    if normalized_mode in ("manual", "semi"):
        return steps
    return []


def is_solution_change_gate_manual_step(
    *,
    task_type: object,
    manual_step: object,
) -> bool:
    if str(task_type or "").strip().lower() != "solution_change":
        return False
    return str(manual_step or "").strip() in SOLUTION_CHANGE_GATE_STEPS


__all__ = [
    "AVAILABLE_CONTROL_MODES",
    "SOLUTION_CHANGE_ABORT_STEP",
    "SOLUTION_CHANGE_GATE_CONFIRM_BY_STAGE",
    "SOLUTION_CHANGE_GATE_STEPS",
    "allowed_manual_steps_for_stage",
    "allowed_manual_steps_for_task",
    "allowed_manual_steps_for_workflow",
    "is_solution_change_gate_manual_step",
    "normalize_control_mode",
    "resolve_manual_control_stage",
    "solution_change_gate_confirm_step_for_stage",
]
