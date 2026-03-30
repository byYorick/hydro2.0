from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ae3lite.domain.services.irrigation_decision_controller import IrrigationDecisionController


NOW = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)


class _RuntimeMonitor:
    def __init__(self, sensor_windows: tuple[dict, ...], *, is_stale: bool = False) -> None:
        self.sensor_windows = sensor_windows
        self.is_stale = is_stale

    async def read_metric_windows(self, **_kwargs):
        return {
            "has_sensors": bool(self.sensor_windows),
            "sensor_windows": self.sensor_windows,
            "latest_sample_ts": NOW,
            "sample_age_sec": 0.0,
            "is_stale": self.is_stale,
        }


@pytest.mark.asyncio
async def test_smart_soil_runs_when_below_target_band() -> None:
    controller = IrrigationDecisionController()
    runtime = {
        "irrigation_decision": {
            "strategy": "smart_soil_v1",
            "config": {"lookback_sec": 1800, "min_samples": 3, "stale_after_sec": 600, "hysteresis_pct": 2.0},
        },
        "soil_moisture_target": {"min": 38.0, "max": 48.0, "target": 43.0},
    }
    monitor = _RuntimeMonitor((
        {"sensor_label": "soil-1", "samples": ({"value": 30.0}, {"value": 31.0})},
        {"sensor_label": "soil-2", "samples": ({"value": 32.0}, {"value": 33.0})},
    ))

    result = await controller.evaluate(
        zone_id=7,
        runtime_monitor=monitor,
        runtime=runtime,
        mode="normal",
        requested_duration_sec=120,
        now=NOW,
    )

    assert result.outcome == "run"
    assert result.reason_code == "smart_soil_below_min"


@pytest.mark.asyncio
async def test_smart_soil_skips_inside_target_band() -> None:
    controller = IrrigationDecisionController()
    runtime = {
        "irrigation_decision": {
            "strategy": "smart_soil_v1",
            "config": {"lookback_sec": 1800, "min_samples": 2, "stale_after_sec": 600, "hysteresis_pct": 0.0},
        },
        "soil_moisture_target": {"min": 38.0, "max": 48.0, "target": 43.0},
    }
    monitor = _RuntimeMonitor((
        {"sensor_label": "soil-1", "samples": ({"value": 41.0}, {"value": 42.0})},
    ))

    result = await controller.evaluate(
        zone_id=7,
        runtime_monitor=monitor,
        runtime=runtime,
        mode="normal",
        requested_duration_sec=120,
        now=NOW,
    )

    assert result.outcome == "skip"
    assert result.reason_code == "smart_soil_within_band"


@pytest.mark.asyncio
async def test_smart_soil_returns_degraded_run_when_samples_missing() -> None:
    controller = IrrigationDecisionController()
    runtime = {
        "irrigation_decision": {
            "strategy": "smart_soil_v1",
            "config": {"lookback_sec": 1800, "min_samples": 3, "stale_after_sec": 600},
        },
        "soil_moisture_target": {"min": 38.0, "max": 48.0, "target": 43.0},
    }
    monitor = _RuntimeMonitor((
        {"sensor_label": "soil-1", "samples": ({"value": 34.0},)},
    ), is_stale=True)

    result = await controller.evaluate(
        zone_id=7,
        runtime_monitor=monitor,
        runtime=runtime,
        mode="normal",
        requested_duration_sec=120,
        now=NOW,
    )

    assert result.outcome == "degraded_run"
    assert result.degraded is True
    assert result.reason_code == "smart_soil_telemetry_missing_or_stale"


@pytest.mark.asyncio
async def test_force_mode_bypasses_decision_strategy() -> None:
    controller = IrrigationDecisionController()

    result = await controller.evaluate(
        zone_id=7,
        runtime_monitor=_RuntimeMonitor(()),
        runtime={},
        mode="force",
        requested_duration_sec=120,
        now=NOW,
    )

    assert result.outcome == "run"
    assert result.reason_code == "irrigation_force_mode"
