"""Shared manual-control contract for AE3-Lite public API."""

from __future__ import annotations

import logging
from typing import Final

logger = logging.getLogger(__name__)


AVAILABLE_CONTROL_MODES: Final[tuple[str, ...]] = ("auto", "semi", "manual")

_ALLOWED_MANUAL_STEPS_BY_STAGE: Final[dict[str, list[str]]] = {
    "startup": ["clean_fill_start", "solution_fill_start"],
    "clean_fill_check": ["clean_fill_stop"],
    "solution_fill_check": ["solution_fill_stop"],
    "prepare_recirculation_check": ["prepare_recirculation_stop"],
    "irrigation_check": ["irrigation_stop"],
    "irrigation_recovery_check": ["irrigation_recovery_stop"],
}


def normalize_control_mode(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in AVAILABLE_CONTROL_MODES:
        return normalized
    if normalized:
        logger.warning("AE3 unknown control_mode=%s; falling back to auto", normalized)
    return "auto"


def allowed_manual_steps_for_stage(stage: object) -> list[str]:
    normalized_stage = str(stage or "").strip()
    return list(_ALLOWED_MANUAL_STEPS_BY_STAGE.get(normalized_stage, ()))


__all__ = [
    "AVAILABLE_CONTROL_MODES",
    "allowed_manual_steps_for_stage",
    "normalize_control_mode",
]
