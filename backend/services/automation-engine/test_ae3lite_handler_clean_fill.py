from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from unittest.mock import AsyncMock

from ae3lite.application.handlers.clean_fill import CleanFillCheckHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.errors import TaskExecutionError


NOW = datetime(2026, 3, 14, 15, 30, 0, tzinfo=timezone.utc)


def _task(*, control_mode: str = "auto", pending_manual_step: str | None = None) -> AutomationTask:
    return AutomationTask.from_row({
        "id": 8,
        "zone_id": 80,
        "task_type": "cycle_start",
        "status": "running",
        "idempotency_key": "k8",
        "scheduled_for": NOW,
        "due_at": NOW,
        "claimed_by": "w1",
        "claimed_at": NOW,
        "error_code": None,
        "error_message": None,
        "created_at": NOW,
        "updated_at": NOW,
        "completed_at": None,
        "topology": "two_tank",
        "intent_source": None,
        "intent_trigger": None,
        "intent_id": None,
        "intent_meta": {},
        "current_stage": "clean_fill_check",
        "workflow_phase": "tank_filling",
        "stage_deadline_at": None,
        "stage_retry_count": 0,
        "stage_entered_at": NOW,
        "clean_fill_cycle": 1,
        "control_mode_snapshot": control_mode,
        "pending_manual_step": pending_manual_step,
        "corr_step": None,
    })


class _Monitor:
    def __init__(self, *, level_states: list[dict[str, object]] | None = None) -> None:
        self._level_states = level_states or [
            {
                "has_level": True,
                "is_stale": False,
                "is_triggered": False,
                "sample_ts": NOW,
                "sample_age_sec": 0.0,
            }
        ]
        self.level_call_count = 0

    async def read_level_switch(self, **_kwargs: Any) -> dict[str, object]:
        idx = min(self.level_call_count, len(self._level_states) - 1)
        self.level_call_count += 1
        return dict(self._level_states[idx])

    async def read_metric(self, **_kwargs: Any) -> dict[str, object]:
        return {"has_value": True, "is_stale": False, "value": 5.8}


class _Gateway:
    async def run_batch(self, **_kwargs: Any) -> dict[str, object]:
        return {"success": True, "error_code": None, "error_message": None}


class _Plan:
    runtime = {
        "clean_max_sensor_labels": ["clean_max"],
        "clean_min_sensor_labels": ["clean_min"],
        "level_switch_on_threshold": 0.5,
        "telemetry_max_age_sec": 300,
        "level_poll_interval_sec": 10,
    }


def _handler() -> CleanFillCheckHandler:
    return CleanFillCheckHandler(runtime_monitor=_Monitor(), command_gateway=_Gateway())


@pytest.mark.asyncio
async def test_manual_clean_fill_without_pending_step_polls() -> None:
    outcome = await _handler().run(task=_task(control_mode="manual"), plan=_Plan(), stage_def=None, now=NOW)
    assert outcome.kind == "poll"
    assert outcome.due_delay_sec == 10


@pytest.mark.asyncio
async def test_manual_clean_fill_stop_transitions_to_solution() -> None:
    outcome = await _handler().run(
        task=_task(control_mode="manual", pending_manual_step="clean_fill_stop"),
        plan=_Plan(),
        stage_def=None,
        now=NOW,
    )
    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_stop_to_solution"


@pytest.mark.asyncio
async def test_clean_fill_stale_level_recovers_on_safe_recheck(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monitor = _Monitor(level_states=[
        {
            "has_level": True,
            "is_stale": True,
            "is_triggered": False,
            "sample_ts": NOW,
            "sample_age_sec": 10.5,
        },
        {
            "has_level": True,
            "is_stale": False,
            "is_triggered": False,
            "sample_ts": NOW,
            "sample_age_sec": 0.0,
        },
    ])
    handler = CleanFillCheckHandler(runtime_monitor=monitor, command_gateway=_Gateway())
    sleep_mock = AsyncMock()
    monkeypatch.setattr("ae3lite.application.handlers.base.asyncio.sleep", sleep_mock)

    with caplog.at_level("INFO"):
        outcome = await handler.run(task=_task(), plan=_Plan(), stage_def=None, now=NOW)

    assert outcome.kind == "poll"
    assert monitor.level_call_count == 2
    sleep_mock.assert_awaited_once_with(handler._STALE_RECHECK_DELAY_SEC)
    assert "sample_ts=" in caplog.text
    assert "sample_age_sec=10.5" in caplog.text
    assert "stale_recheck_recovered" in caplog.text


@pytest.mark.asyncio
async def test_clean_fill_stale_level_raises_after_failed_safe_recheck(monkeypatch: pytest.MonkeyPatch) -> None:
    monitor = _Monitor(level_states=[
        {
            "has_level": True,
            "is_stale": True,
            "is_triggered": False,
            "sample_ts": NOW,
            "sample_age_sec": 12.0,
        },
        {
            "has_level": True,
            "is_stale": True,
            "is_triggered": False,
            "sample_ts": NOW,
            "sample_age_sec": 12.2,
        },
    ])
    handler = CleanFillCheckHandler(runtime_monitor=monitor, command_gateway=_Gateway())
    monkeypatch.setattr("ae3lite.application.handlers.base.asyncio.sleep", AsyncMock())

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=_task(), plan=_Plan(), stage_def=None, now=NOW)

    assert exc_info.value.code == "two_tank_clean_level_stale"
    assert monitor.level_call_count == 2
