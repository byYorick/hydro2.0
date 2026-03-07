"""Pure domain service for AE3-Lite correction dose planning.

Spec: doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md

Rules:
- EC corrected before PH (always).
- Dose duration computed from pump calibration (ml_per_sec).
- No hardcoded dose targets — all from correction_config.
- No IO — pure calculation only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ae3lite.domain.errors import PlannerConfigurationError


@dataclass(frozen=True)
class DosePlan:
    """What corrections are needed and the resolved pulse durations."""

    needs_ec: bool
    ec_node_uid: str
    ec_channel: str
    ec_duration_ms: int

    needs_ph_up: bool
    needs_ph_down: bool
    ph_node_uid: str
    ph_channel: str
    ph_duration_ms: int

    @property
    def needs_any(self) -> bool:
        return self.needs_ec or self.needs_ph_up or self.needs_ph_down

    @property
    def ph_direction(self) -> str:
        """Returns 'up', 'down', or 'none'."""
        if self.needs_ph_up:
            return "up"
        if self.needs_ph_down:
            return "down"
        return "none"


class CorrectionPlanner:
    """Pure domain service: decides what to dose and for how long.

    Used at: solution_fill, prepare_recirculation, irrigation.
    Caller must supply resolved actuator refs (with pump_calibration).
    """

    def is_within_tolerance(
        self,
        *,
        current_ph: float,
        current_ec: float,
        target_ph: float,
        target_ec: float,
        ph_tolerance_pct: float,
        ec_tolerance_pct: float,
    ) -> bool:
        """True if both PH and EC are within configured tolerance bands."""
        ec_tol = abs(target_ec) * (ec_tolerance_pct / 100.0)
        ph_tol = abs(target_ph) * (ph_tolerance_pct / 100.0)
        return abs(current_ec - target_ec) <= ec_tol and abs(current_ph - target_ph) <= ph_tol

    def build_dose_plan(
        self,
        *,
        current_ph: float,
        current_ec: float,
        target_ph: float,
        target_ec: float,
        ph_tolerance_pct: float,
        ec_tolerance_pct: float,
        correction_config: Mapping[str, Any],
        # Resolved actuator refs from plan.runtime["correction"]["actuators"]
        ec_actuator: Optional[Mapping[str, Any]],
        ph_up_actuator: Optional[Mapping[str, Any]],
        ph_down_actuator: Optional[Mapping[str, Any]],
    ) -> DosePlan:
        """Build a concrete dose plan with pulse durations in milliseconds.

        EC is always corrected before PH (spec §3.1, §3.2).
        Dose volume is clamped to max_ec_dose_ml / max_ph_dose_ml.
        """
        ec_tol = abs(target_ec) * (ec_tolerance_pct / 100.0)
        ph_tol = abs(target_ph) * (ph_tolerance_pct / 100.0)

        ec_error = target_ec - current_ec  # positive → need more EC
        ph_error = target_ph - current_ph  # positive → pH too low (need UP)

        needs_ec = ec_error > ec_tol
        needs_ph_up = ph_error > ph_tol
        needs_ph_down = (-ph_error) > ph_tol

        solution_volume_l = _positive_float(
            correction_config.get("solution_volume_l"), default=100.0
        )

        # --- EC dose ---
        ec_node_uid = ""
        ec_channel = str(correction_config.get("dose_ec_channel") or "dose_ec_a").strip().lower()
        ec_duration_ms = 0
        if needs_ec:
            if ec_actuator is None:
                raise PlannerConfigurationError(
                    f"EC correction needed but no actuator resolved for channel={ec_channel}"
                )
            ec_node_uid = str(ec_actuator["node_uid"])
            ec_channel = str(ec_actuator["channel"])
            calibration = ec_actuator.get("calibration")
            if not isinstance(calibration, Mapping):
                raise PlannerConfigurationError(
                    f"EC dosing pump calibration is required (channel={ec_channel}, node={ec_node_uid})"
                )
            sensitivity = _positive_float(
                correction_config.get("ec_dose_ml_per_mS_L"), default=1.0
            )
            max_ml = _positive_float(correction_config.get("max_ec_dose_ml"), default=50.0)
            dose_ml = min(ec_error * solution_volume_l * sensitivity, max_ml)
            ec_duration_ms = _dose_ml_to_ms(dose_ml, calibration)

        # --- PH dose ---
        ph_node_uid = ""
        ph_channel = ""
        ph_duration_ms = 0
        if needs_ph_up or needs_ph_down:
            ph_actuator = ph_up_actuator if needs_ph_up else ph_down_actuator
            default_channel = (
                correction_config.get("dose_ph_up_channel") if needs_ph_up
                else correction_config.get("dose_ph_down_channel")
            ) or ("dose_ph_up" if needs_ph_up else "dose_ph_down")
            ph_channel = str(default_channel).strip().lower()
            if ph_actuator is None:
                raise PlannerConfigurationError(
                    f"PH correction needed but no actuator resolved for channel={ph_channel}"
                )
            ph_node_uid = str(ph_actuator["node_uid"])
            ph_channel = str(ph_actuator["channel"])
            calibration = ph_actuator.get("calibration")
            if not isinstance(calibration, Mapping):
                raise PlannerConfigurationError(
                    f"PH dosing pump calibration is required (channel={ph_channel}, node={ph_node_uid})"
                )
            sensitivity = _positive_float(
                correction_config.get("ph_dose_ml_per_unit_L"), default=0.5
            )
            max_ml = _positive_float(correction_config.get("max_ph_dose_ml"), default=20.0)
            dose_ml = min(abs(ph_error) * solution_volume_l * sensitivity, max_ml)
            ph_duration_ms = _dose_ml_to_ms(dose_ml, calibration)

        return DosePlan(
            needs_ec=needs_ec and ec_duration_ms > 0,
            ec_node_uid=ec_node_uid,
            ec_channel=ec_channel,
            ec_duration_ms=ec_duration_ms,
            needs_ph_up=needs_ph_up and ph_duration_ms > 0,
            needs_ph_down=needs_ph_down and ph_duration_ms > 0,
            ph_node_uid=ph_node_uid,
            ph_channel=ph_channel,
            ph_duration_ms=ph_duration_ms,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dose_ml_to_ms(dose_ml: float, calibration: Mapping[str, Any]) -> int:
    """Convert dose volume (ml) to pump pulse duration (ms) via calibration.

    Uses ml_per_sec: flow rate of the dosing pump.
    duration_ms = (dose_ml / ml_per_sec) * 1000
    """
    raw = calibration.get("ml_per_sec")
    if raw is None:
        raise PlannerConfigurationError(
            "Pump calibration is missing ml_per_sec; cannot compute dose duration"
        )
    try:
        ml_per_sec = float(raw)
    except (TypeError, ValueError):
        raise PlannerConfigurationError(
            f"Pump calibration ml_per_sec is not numeric: {raw!r}"
        )
    if ml_per_sec <= 0:
        raise PlannerConfigurationError(
            f"Pump calibration ml_per_sec must be positive, got {ml_per_sec}"
        )
    return max(0, int(dose_ml / ml_per_sec * 1000))


def _positive_float(raw: Any, default: float) -> float:
    try:
        v = float(raw)
        if v > 0:
            return v
    except (TypeError, ValueError):
        pass
    return default
