"""Solver субстрата (water content).

Phase A: stub — линейный drainage без реальной модели irrigation.
Phase B (план): SmartSoil decisions, drainage с гистерезисом, evapotranspiration.
"""
from typing import Dict, Optional

from .state import SubstrateState


class SubstrateSolver:
    """Solver влажности субстрата (water content, %)."""

    DEFAULT_PARAMS: Dict[str, float] = {
        "drainage_pct_per_hour": 1.0,
    }

    def __init__(self, params: Optional[Dict[str, float]] = None) -> None:
        merged = dict(self.DEFAULT_PARAMS)
        if params:
            for key, value in params.items():
                if value is None:
                    continue
                try:
                    merged[key] = float(value)
                except (TypeError, ValueError):
                    continue
        self.params = merged

    def step(
        self,
        state: SubstrateState,
        flows: Optional[Dict[str, float]] = None,
        dt_hours: float = 0.0,
    ) -> SubstrateState:
        flows = flows or {}
        irrigation_in_pct = float(flows.get("irrigation_in_pct", 0.0))
        new_wc = (
            state.water_content_pct
            + irrigation_in_pct
            - self.params["drainage_pct_per_hour"] * dt_hours
        )
        return SubstrateState(water_content_pct=max(0.0, min(100.0, new_wc)))
