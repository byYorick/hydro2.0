"""Shared manual-control contract for AE3-Lite public API."""

from __future__ import annotations

from typing import Final


AVAILABLE_CONTROL_MODES: Final[tuple[str, ...]] = ("auto", "semi", "manual")

_ALLOWED_MANUAL_STEPS_BY_STAGE: Final[dict[str, list[str]]] = {
    "startup": ["clean_fill_start", "solution_fill_start"],
    "clean_fill_check": ["clean_fill_stop"],
    "solution_fill_check": ["solution_fill_stop"],
    "prepare_recirculation_check": ["prepare_recirculation_stop"],
}


def normalize_control_mode(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in AVAILABLE_CONTROL_MODES:
        return normalized
    return "auto"


def allowed_manual_steps_for_stage(stage: object) -> list[str]:
    normalized_stage = str(stage or "").strip()
    return list(_ALLOWED_MANUAL_STEPS_BY_STAGE.get(normalized_stage, ()))


__all__ = [
    "AVAILABLE_CONTROL_MODES",
    "allowed_manual_steps_for_stage",
    "normalize_control_mode",
]
