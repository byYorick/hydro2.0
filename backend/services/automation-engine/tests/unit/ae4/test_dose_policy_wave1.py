"""Доза: арифметика и запреты протухших датчиков (волна 1, без публикации)."""

from __future__ import annotations

from datetime import datetime, timezone

from ae4.domain.dose_policy import dose_ml_for_error, evaluate_ec_pulse, evaluate_ph_pulse
from tests.unit.ae4.conftest_wave1 import sample


def test_dose_ml_capped_by_controller_max() -> None:
    ml = dose_ml_for_error(error_to_target=2.0, gain=0.1, max_dose_ml=5.0)
    assert ml == 5.0


def test_ph_below_uses_ph_up_above_uses_ph_down() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    low = evaluate_ph_pulse(
        ph_sample=sample(metric_type="PH", channel="ph_sensor", value=5.0, ts=now, unit="pH"),
        ph_target=5.8,
        ph_unit="pH",
        gain=1.0,
        max_dose_ml=10.0,
        now=now,
        telemetry_max_age_sec=60,
    )
    assert low.allow_pulse is True
    assert low.reagent == "ph_up"
    assert low.blocks_shot is False

    high = evaluate_ph_pulse(
        ph_sample=sample(metric_type="PH", channel="ph_sensor", value=6.5, ts=now, unit="pH"),
        ph_target=5.8,
        ph_unit="pH",
        gain=1.0,
        max_dose_ml=10.0,
        now=now,
        telemetry_max_age_sec=60,
    )
    assert high.reagent == "ph_down"


def test_stale_ph_blocks_pulse_not_shot() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    decision = evaluate_ph_pulse(
        ph_sample=None,
        ph_target=5.8,
        ph_unit="pH",
        gain=1.0,
        max_dose_ml=10.0,
        now=now,
        telemetry_max_age_sec=60,
    )
    assert decision.allow_pulse is False
    assert decision.blocks_shot is False
    assert decision.reason_code == "ph_stale"


def test_stale_ec_empty_setting_blocks_shot() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    blocked = evaluate_ec_pulse(
        ec_sample=None,
        ec_target=1.4,
        ec_unit="mS/cm",
        gain=1.0,
        max_dose_ml=10.0,
        now=now,
        telemetry_max_age_sec=60,
        stale_ec_allows_shot=None,
    )
    assert blocked.blocks_shot is True
    assert blocked.allow_pulse is False

    allowed = evaluate_ec_pulse(
        ec_sample=None,
        ec_target=1.4,
        ec_unit="mS/cm",
        gain=1.0,
        max_dose_ml=10.0,
        now=now,
        telemetry_max_age_sec=60,
        stale_ec_allows_shot=True,
    )
    assert allowed.blocks_shot is False
    assert allowed.allow_pulse is False
