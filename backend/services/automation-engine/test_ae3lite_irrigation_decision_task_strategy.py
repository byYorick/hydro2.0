from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ae3lite.domain.services.irrigation_decision_controller import IrrigationDecisionController


class _RuntimeMonitor:
    async def read_metric_windows(self, **_kwargs):
        return {"has_sensors": False, "sensor_windows": (), "latest_sample_ts": None, "sample_age_sec": None, "is_stale": False}


@pytest.mark.asyncio
async def test_task_strategy_always_returns_run() -> None:
    controller = IrrigationDecisionController()
    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    runtime = {"irrigation_decision": {"strategy": "task"}}
    result = await controller.evaluate(
        zone_id=7,
        runtime_monitor=_RuntimeMonitor(),
        runtime=runtime,
        mode="normal",
        requested_duration_sec=120,
        now=now,
    )
    assert result.outcome == "run"
    assert result.reason_code == "irrigation_task_strategy_run"

