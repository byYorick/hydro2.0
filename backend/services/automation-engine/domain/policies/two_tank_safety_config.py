"""Explicit safety configuration for two-tank workflows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TwoTankSafetyConfig:
    """Per-concern safety switches for two-tank runtime behavior."""

    pump_interlock: bool = True
    stop_confirmation_required: bool = True
    irr_state_validation: bool = True

    @classmethod
    def production(cls) -> "TwoTankSafetyConfig":
        return cls()

    @classmethod
    def testing(cls) -> "TwoTankSafetyConfig":
        return cls(pump_interlock=False)


__all__ = ["TwoTankSafetyConfig"]
