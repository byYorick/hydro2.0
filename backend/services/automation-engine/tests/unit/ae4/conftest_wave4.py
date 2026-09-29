"""Хелперы волны 4: доза и настройка протухшего EC."""

from __future__ import annotations

from ae4.config.zone_plan import DoseActuatorRef, ZoneDosePlan
from ae4.domain.dose_policy import ControllerDoseParams


def make_controller(
    *,
    gain: float | None = 0.1,
    max_dose_ml: float | None = 10.0,
    min_interval_sec: int | None = 60,
    decision_window_sec: int | None = 30,
    min_effect_fraction: float | None = 0.2,
    no_effect_limit: int | None = 3,
    min_dose_ms: int | None = None,
    ml_per_sec: float | None = None,
) -> ControllerDoseParams:
    return ControllerDoseParams(
        gain=gain,
        max_dose_ml=max_dose_ml,
        min_interval_sec=min_interval_sec,
        decision_window_sec=decision_window_sec,
        min_effect_fraction=min_effect_fraction,
        no_effect_limit=no_effect_limit,
        min_dose_ms=min_dose_ms,
        ml_per_sec=ml_per_sec,
    )


def make_dose_plan(
    *,
    stale_ec_allows_shot: bool | None = None,
    ec_gain: float | None = 0.1,
    ph_up_gain: float | None = 0.2,
    ph_down_gain: float | None = 0.2,
    max_dose_ml: float | None = 10.0,
) -> ZoneDosePlan:
    ctrl = make_controller(gain=ec_gain, max_dose_ml=max_dose_ml)
    ph_ctrl = make_controller(gain=ph_up_gain, max_dose_ml=max_dose_ml)
    return ZoneDosePlan(
        stale_ec_allows_shot=stale_ec_allows_shot,
        ec=ctrl,
        ph=ph_ctrl,
        ph_up_gain=ph_up_gain,
        ph_down_gain=ph_down_gain,
        actuators={
            "nutrition": DoseActuatorRef(
                node_uid="nd-ec",
                channel="pump_a",
                ml_per_sec=1.0,
            ),
            "ph_up": DoseActuatorRef(
                node_uid="nd-ph",
                channel="ph_up",
                ml_per_sec=1.0,
            ),
            "ph_down": DoseActuatorRef(
                node_uid="nd-ph",
                channel="ph_down",
                ml_per_sec=1.0,
            ),
        },
    )
