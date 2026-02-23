"""Canonical AE2-Lite correction gating exports."""

from services.zone_correction_gating import (
    build_correction_gating_state,
    build_stale_flag_reasons,
    collect_stale_correction_flags,
)

__all__ = [
    "build_correction_gating_state",
    "build_stale_flag_reasons",
    "collect_stale_correction_flags",
]
