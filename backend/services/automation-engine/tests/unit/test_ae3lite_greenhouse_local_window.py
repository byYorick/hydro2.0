"""Окна полива, day/night и суточный сброс DLI считаются в поясе теплицы.

Naive datetime — это UTC, не местное время процесса. Невалидный IANA-пояс
отклоняет конфиг и не даёт команду.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from _test_support_runtime_plan import make_runtime_plan
from ae3lite.application.handlers.decision_gate import DecisionGateHandler
from ae3lite.config.errors import ConfigValidationError
from ae3lite.config.runtime_plan_targets import _build_day_night_config
from ae3lite.config.schema.runtime_plan import DayNightLighting
from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services.dli_integral import local_date_of, zone_timezone
from ae3lite.domain.services.greenhouse_clock import (
    DEFAULT_GREENHOUSE_TIMEZONE,
    InvalidGreenhouseTimezone,
    as_aware_utc,
    greenhouse_local_midnight_utc,
)
from ae3lite.domain.services.irrigation_decision_controller import IrrigationDecisionController
from ae3lite.greenhouse_climate.climate_tick_targets import ClimateTickTargets
from ae3lite.hydraulics.failure_report import close_upward_capture, drain_upward_reports, open_upward_capture


# 22:00 + 4 ч = [22:00, 02:00) по Europe/Simferopol (UTC+3).
_UTC_INSIDE = datetime(2026, 6, 15, 21, 30, tzinfo=timezone.utc)  # 00:30 местного
_UTC_AFTER_MIDNIGHT_END = datetime(2026, 6, 15, 23, 30, tzinfo=timezone.utc)  # 02:30 местного


class _Monitor:
    def __init__(self, value: float) -> None:
        self.value = value

    async def read_metric_windows(self, **_kwargs):
        return {
            "sensor_windows": ({"samples": ({"value": self.value},)},),
            "is_stale": False,
        }


def _curve_runtime(*, timezone_name: str | None) -> object:
    soil: dict[str, object] = {
        "day": 40.0,
        "night": 70.0,
        "day_start_time": "22:00",
        "day_hours": 4,
    }
    if timezone_name is not None:
        soil["timezone"] = timezone_name
    return make_runtime_plan(
        irrigation_decision={
            "strategy": "smart_soil_v1",
            "config": {
                "lookback_sec": 1800,
                "min_samples": 1,
                "stale_after_sec": 600,
                "hysteresis_pct": 0.0,
            },
        },
        soil_moisture_target=soil,
    )


async def _decide(now: datetime, *, timezone_name: str | None = DEFAULT_GREENHOUSE_TIMEZONE):
    return await IrrigationDecisionController().evaluate(
        zone_id=7,
        runtime_monitor=_Monitor(50.0),
        runtime=_curve_runtime(timezone_name=timezone_name),
        mode="normal",
        requested_duration_sec=120,
        now=now,
    )


@pytest.mark.asyncio
async def test_irrigation_window_around_midnight_uses_simferopol_not_utc() -> None:
    inside = await _decide(_UTC_INSIDE.replace(tzinfo=None))
    outside = await _decide(_UTC_AFTER_MIDNIGHT_END)

    assert inside.outcome == "skip"
    assert inside.reason_code == "smart_soil_above_max"
    assert inside.details is not None
    assert inside.details["target_profile"] == "day"
    assert outside.outcome == "run"
    assert outside.reason_code == "smart_soil_below_min"
    assert outside.details is not None
    assert outside.details["target_profile"] == "night"


@pytest.mark.asyncio
async def test_naive_irrigation_now_is_utc_not_process_local() -> None:
    naive = await _decide(_UTC_INSIDE.replace(tzinfo=None))
    aware = await _decide(_UTC_INSIDE)
    assert naive.outcome == aware.outcome
    assert naive.reason_code == aware.reason_code
    assert as_aware_utc(_UTC_INSIDE.replace(tzinfo=None)) == _UTC_INSIDE


@pytest.mark.asyncio
async def test_missing_timezone_defaults_to_simferopol() -> None:
    decision = await _decide(_UTC_INSIDE, timezone_name=None)
    assert decision.details is not None
    assert decision.details["timezone"] == DEFAULT_GREENHOUSE_TIMEZONE
    assert decision.details["target_profile"] == "day"


@pytest.mark.asyncio
async def test_invalid_timezone_fails_closed_without_irrigation() -> None:
    runtime = SimpleNamespace(
        irrigation_decision=SimpleNamespace(
            strategy="smart_soil_v1",
            config=SimpleNamespace(
                lookback_sec=60,
                min_samples=1,
                stale_after_sec=60,
                hysteresis_pct=0.0,
                spread_alert_threshold_pct=100.0,
            ),
        ),
        soil_moisture_target=SimpleNamespace(
            min=None,
            max=None,
            day=40.0,
            night=70.0,
            day_start_time="22:00",
            day_hours=4.0,
            timezone="Invalid/Zone",
        ),
        day_night_config=SimpleNamespace(lighting=SimpleNamespace(timezone=None)),
    )
    decision = await IrrigationDecisionController().evaluate(
        zone_id=7,
        runtime_monitor=_Monitor(10.0),
        runtime=runtime,
        mode="normal",
        requested_duration_sec=30,
        now=_UTC_INSIDE,
    )
    assert decision.outcome == "fail"
    assert decision.outcome != "run"
    assert decision.reason_code == "irrigation_timezone_invalid"


def test_runtime_plan_rejects_invalid_timezone() -> None:
    with pytest.raises(ValidationError):
        DayNightLighting(day_start_time="22:00", day_hours=4, timezone="Invalid/Zone")
    with pytest.raises((ConfigValidationError, ValidationError)):
        make_runtime_plan(
            day_night_config={
                "enabled": False,
                "lighting": {"day_start_time": "22:00", "day_hours": 4, "timezone": "Not/AZone"},
                "ph": {
                    "day": None, "night": None, "day_min": None, "day_max": None,
                    "night_min": None, "night_max": None,
                },
                "ec": {
                    "day": None, "night": None, "day_min": None, "day_max": None,
                    "night_min": None, "night_max": None,
                },
            }
        )


def test_day_night_config_uses_greenhouse_timezone_or_default() -> None:
    missing = _build_day_night_config(SimpleNamespace(phase_targets={}, targets={}))
    assert missing["lighting"]["timezone"] == "Europe/Simferopol"
    explicit = _build_day_night_config(
        SimpleNamespace(phase_targets={"greenhouse_timezone": "Europe/Moscow"}, targets={})
    )
    assert explicit["lighting"]["timezone"] == "Europe/Moscow"
    with pytest.raises(PlannerConfigurationError):
        _build_day_night_config(
            SimpleNamespace(phase_targets={"greenhouse_timezone": "Invalid/Zone"}, targets={})
        )


def test_dli_local_day_crosses_midnight_in_simferopol() -> None:
    assert local_date_of(_UTC_INSIDE, "Europe/Simferopol") == "2026-06-16"
    assert local_date_of(_UTC_INSIDE, None) == "2026-06-16"
    assert local_date_of(_UTC_INSIDE.replace(tzinfo=None), "Europe/Simferopol") == "2026-06-16"
    assert local_date_of(_UTC_INSIDE, "UTC") == "2026-06-15"
    midnight = greenhouse_local_midnight_utc(_UTC_INSIDE, "Europe/Simferopol")
    assert midnight == datetime(2026, 6, 15, 21, 0, tzinfo=timezone.utc)
    with pytest.raises(InvalidGreenhouseTimezone):
        zone_timezone("Invalid/Zone")


def test_climate_day_window_around_midnight_rejects_invalid_timezone() -> None:
    clock = ClimateTickTargets(
        ports=SimpleNamespace(as_float=lambda value: value, greenhouse_targets=lambda _execution: {}, fetch=None)
    )
    execution = {"day_schedule": {"start_local": "22:00", "end_local": "02:00"}}
    assert clock.schedule_day_for_greenhouse(
        greenhouse_tz="Europe/Simferopol",
        execution=execution,
        now=_UTC_INSIDE.replace(tzinfo=None),
    ) is True
    assert clock.schedule_day_for_greenhouse(
        greenhouse_tz="",
        execution=execution,
        now=_UTC_AFTER_MIDNIGHT_END,
    ) is False
    with pytest.raises(InvalidGreenhouseTimezone):
        clock.schedule_day_for_greenhouse(
            greenhouse_tz="Invalid/Zone",
            execution=execution,
            now=_UTC_INSIDE,
        )


@pytest.mark.asyncio
async def test_decision_gate_skips_pump_when_local_window_is_day(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop_event(*_args, **_kwargs):
        return None

    monkeypatch.setattr("ae3lite.application.handlers.decision_gate.create_zone_event", _noop_event)

    class _Repository:
        def __init__(self) -> None:
            self.saved: dict | None = None

        async def update_irrigation_runtime(self, **kwargs):
            self.saved = kwargs
            return SimpleNamespace(
                id=11,
                zone_id=7,
                current_stage="decision_gate",
                workflow_phase="ready",
                topology="two_tank",
                irrigation_decision_strategy="smart_soil_v1",
                irrigation_bundle_revision=None,
            )

    repository = _Repository()
    handler = DecisionGateHandler(
        runtime_monitor=_Monitor(50.0),
        command_gateway=object(),
        task_repository=repository,
        decision_controller=IrrigationDecisionController(),
    )
    token = open_upward_capture()
    try:
        outcome = await handler.run(
            task=SimpleNamespace(
                id=11,
                zone_id=7,
                claimed_by="worker",
                irrigation_mode="normal",
                irrigation_requested_duration_sec=120,
                topology="two_tank",
                claim_generation=1,
                current_stage="decision_gate",
                workflow_phase="ready",
            ),
            plan=SimpleNamespace(runtime=_curve_runtime(timezone_name="Europe/Simferopol")),
            stage_def=SimpleNamespace(),
            now=_UTC_INSIDE.replace(tzinfo=None),
        )
    finally:
        close_upward_capture(token)
        drain_upward_reports()

    assert outcome.kind == "transition"
    assert outcome.next_stage == "completed_skip"
    assert outcome.next_stage != "irrigation_start"
    assert repository.saved is not None
    assert repository.saved["irrigation_decision_outcome"] == "skip"
