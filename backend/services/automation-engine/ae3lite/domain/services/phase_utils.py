"""Shared workflow-phase key normalisation for AE3-Lite domain services.

Canonical keys returned: ``"solution_fill"``, ``"tank_recirc"``,
``"irrigation"``, ``"generic"``.
"""

from __future__ import annotations

from typing import Any


def normalize_phase_key(raw: Any) -> str:
    """Return the canonical phase key for a raw workflow_phase string.

    Maps workflow phase names (including legacy aliases) to one of four
    canonical keys used by correction configs and process calibrations.
    """
    phase = str(raw or "").strip().lower()
    if phase in {"tank_filling", "solution_fill"}:
        return "solution_fill"
    if phase in {"tank_recirc", "prepare_recirculation"}:
        return "tank_recirc"
    if phase in {"irrigating", "irrigation", "irrig_recirc"}:
        return "irrigation"
    return phase or "generic"
