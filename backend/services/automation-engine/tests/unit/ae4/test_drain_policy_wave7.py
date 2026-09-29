"""EC стока выше коридора — соли нет. Возврат без ёмкостей — команды нет."""

from __future__ import annotations

from datetime import datetime, timezone

from ae4.domain.dose_policy import ControllerDoseParams, evaluate_tick_dose
from ae4.domain.drain_policy import evaluate_drain_return
from ae4.domain.planting import TelemetrySample


def test_ec_drain_above_corridor_blocks_salt() -> None:
    now = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    ec_feed = TelemetrySample(
        metric_type="EC",
        channel="ec_sensor",
        value=1.0,
        ts=now,
        unit="mS/cm",
    )
    ec_drain = TelemetrySample(
        metric_type="EC",
        channel="ec_drain_sensor",
        value=2.5,
        ts=now,
        unit="mS/cm",
    )
    params = ControllerDoseParams(
        gain=0.5,
        max_dose_ml=10.0,
        min_interval_sec=60,
        decision_window_sec=30,
        min_effect_fraction=0.2,
        no_effect_limit=3,
        min_dose_ms=100,
        ml_per_sec=1.0,
    )
    decision = evaluate_tick_dose(
        ec_sample=ec_feed,
        ph_sample=None,
        ec_target=1.4,
        ph_target=None,
        ec_unit="mS/cm",
        ph_unit=None,
        ec_params=params,
        ph_params=params,
        now=now,
        telemetry_max_age_sec=300,
        stale_ec_allows_shot=None,
        ec_drain_sample=ec_drain,
        ec_max=1.8,
    )
    assert decision.allow_pulse is False
    assert decision.reagent is None
    assert decision.dose_ml is None
    assert decision.reason_code == "ec_drain_above_corridor"


def test_drain_return_without_volumes_does_not_allow_command() -> None:
    now = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    sample = TelemetrySample(
        metric_type="EC",
        channel="ec_drain_sensor",
        value=1.2,
        ts=now,
        unit="mS/cm",
    )
    decision = evaluate_drain_return(
        feed_volume_l=50.0,
        drain_volume_l=None,
        ec_drain=sample,
        now=now,
        telemetry_max_age_sec=300,
        ec_min=1.0,
        ec_max=1.8,
        feed_ec=1.4,
    )
    assert decision.allow is False
    assert decision.reason_code == "drain_return_drain_volume_unknown"

    decision_feed = evaluate_drain_return(
        feed_volume_l=None,
        drain_volume_l=20.0,
        ec_drain=sample,
        now=now,
        telemetry_max_age_sec=300,
        ec_min=1.0,
        ec_max=1.8,
        feed_ec=1.4,
    )
    assert decision_feed.allow is False
    assert decision_feed.reason_code == "drain_return_feed_volume_unknown"
