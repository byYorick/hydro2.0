from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from unittest.mock import AsyncMock

from ae3lite.application.handlers.clean_fill import CleanFillCheckHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.errors import TaskExecutionError


NOW = datetime(2026, 3, 14, 15, 30, 0, tzinfo=timezone.utc)


def _task(
    *,
    control_mode: str = "auto",
    pending_manual_step: str | None = None,
    clean_fill_cycle: int = 1,
    stage_entered_at: datetime = NOW,
) -> AutomationTask:
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
        "stage_entered_at": stage_entered_at,
        "clean_fill_cycle": clean_fill_cycle,
        "control_mode_snapshot": control_mode,
        "pending_manual_step": pending_manual_step,
        "corr_step": None,
    })


class _Monitor:
    def __init__(
        self,
        *,
        level_states: list[dict[str, object]] | None = None,
        recent_storage_event: dict[str, object] | None = None,
    ) -> None:
        self._level_states = level_states or [
            {
                "has_level": True,
                "is_stale": False,
                "is_triggered": False,
                "sample_ts": NOW,
                "sample_age_sec": 0.0,
            }
        ]
        self._recent_storage_event = recent_storage_event
        self.level_call_count = 0
        self.zone_event_reads = 0

    async def read_level_switch(self, **_kwargs: Any) -> dict[str, object]:
        idx = min(self.level_call_count, len(self._level_states) - 1)
        self.level_call_count += 1
        return dict(self._level_states[idx])

    async def read_latest_zone_event(self, **_kwargs: Any) -> dict[str, object] | None:
        self.zone_event_reads += 1
        return dict(self._recent_storage_event) if self._recent_storage_event is not None else None

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
        "fail_safe_guards": {"clean_fill_min_check_delay_ms": 5000},
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


@pytest.mark.asyncio
async def test_clean_fill_recent_source_empty_retries_two_cycles_then_fail_closed() -> None:
    monitor = _Monitor(
        recent_storage_event={
            "event_type": "CLEAN_FILL_SOURCE_EMPTY",
            "event_id": 11,
            "created_at": NOW,
            "payload": {"channel": "storage_state"},
        }
    )
    handler = CleanFillCheckHandler(runtime_monitor=monitor, command_gateway=_Gateway())

    first = await handler.run(task=_task(clean_fill_cycle=1), plan=_Plan(), stage_def=None, now=NOW)
    second = await handler.run(task=_task(clean_fill_cycle=2), plan=_Plan(), stage_def=None, now=NOW)
    third = await handler.run(task=_task(clean_fill_cycle=3), plan=_Plan(), stage_def=None, now=NOW)

    assert first.kind == "transition"
    assert first.next_stage == "clean_fill_retry_stop"
    assert first.clean_fill_cycle == 2
    assert second.kind == "transition"
    assert second.next_stage == "clean_fill_retry_stop"
    assert second.clean_fill_cycle == 3
    assert third.kind == "transition"
    assert third.next_stage == "clean_fill_source_empty_stop"


@pytest.mark.asyncio
async def test_clean_fill_recent_completed_event_finishes_without_clean_max_sensor() -> None:
    monitor = _Monitor(
        level_states=[
            {
                "has_level": True,
                "is_stale": False,
                "is_triggered": True,
                "sample_ts": NOW,
                "sample_age_sec": 0.0,
            },
            {
                "has_level": False,
                "is_stale": False,
                "is_triggered": False,
                "sample_ts": NOW,
                "sample_age_sec": 0.0,
            },
        ],
        recent_storage_event={
            "event_type": "CLEAN_FILL_COMPLETED",
            "event_id": 12,
            "created_at": NOW,
            "payload": {"channel": "storage_state"},
        },
    )

    outcome = await CleanFillCheckHandler(runtime_monitor=monitor, command_gateway=_Gateway()).run(
        task=_task(),
        plan=_Plan(),
        stage_def=None,
        now=NOW,
    )

    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_stop_to_solution"
    assert monitor.level_call_count == 1


@pytest.mark.asyncio
async def test_manual_clean_fill_still_obeys_source_empty_event() -> None:
    monitor = _Monitor(
        recent_storage_event={
            "event_type": "CLEAN_FILL_SOURCE_EMPTY",
            "event_id": 15,
            "created_at": NOW,
            "payload": {"channel": "storage_state"},
        }
    )

    outcome = await CleanFillCheckHandler(runtime_monitor=monitor, command_gateway=_Gateway()).run(
        task=_task(control_mode="manual"),
        plan=_Plan(),
        stage_def=None,
        now=NOW,
    )

    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_retry_stop"


@pytest.mark.asyncio
async def test_manual_clean_fill_still_obeys_completed_event() -> None:
    monitor = _Monitor(
        level_states=[
            {
                "has_level": True,
                "is_stale": False,
                "is_triggered": True,
                "sample_ts": NOW,
                "sample_age_sec": 0.0,
            }
        ],
        recent_storage_event={
            "event_type": "CLEAN_FILL_COMPLETED",
            "event_id": 16,
            "created_at": NOW,
            "payload": {"channel": "storage_state"},
        },
    )

    outcome = await CleanFillCheckHandler(runtime_monitor=monitor, command_gateway=_Gateway()).run(
        task=_task(control_mode="manual"),
        plan=_Plan(),
        stage_def=None,
        now=NOW,
    )

    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_stop_to_solution"


@pytest.mark.asyncio
async def test_clean_fill_low_clean_min_after_guard_delay_uses_source_empty_path() -> None:
    entered_at = NOW.replace(hour=15, minute=29, second=50)
    monitor = _Monitor(
        level_states=[
            {
                "has_level": True,
                "is_stale": False,
                "is_triggered": False,
                "sample_ts": NOW,
                "sample_age_sec": 0.0,
            },
            {
                "has_level": True,
                "is_stale": False,
                "is_triggered": False,
                "sample_ts": NOW,
                "sample_age_sec": 0.0,
            },
        ]
    )

    outcome = await CleanFillCheckHandler(runtime_monitor=monitor, command_gateway=_Gateway()).run(
        task=_task(stage_entered_at=entered_at, clean_fill_cycle=3),
        plan=_Plan(),
        stage_def=None,
        now=NOW,
    )

    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_source_empty_stop"


@pytest.mark.asyncio
async def test_clean_fill_recent_estop_reconcile_failure_raises_emergency_stop() -> None:
    monitor = _Monitor(
        recent_storage_event={
            "event_type": "EMERGENCY_STOP_ACTIVATED",
            "event_id": 13,
            "created_at": NOW,
            "payload": {"channel": "storage_state"},
        }
    )
    handler = CleanFillCheckHandler(runtime_monitor=monitor, command_gateway=_Gateway())
    handler._probe_irr_state = AsyncMock(side_effect=TaskExecutionError("irr_state_mismatch", "pump off"))

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=_task(), plan=_Plan(), stage_def=None, now=NOW)

    assert exc_info.value.code == "emergency_stop_activated"


@pytest.mark.asyncio
async def test_clean_fill_recent_estop_reconcile_success_continues() -> None:
    monitor = _Monitor(
        recent_storage_event={
            "event_type": "EMERGENCY_STOP_ACTIVATED",
            "event_id": 14,
            "created_at": NOW,
            "payload": {"channel": "storage_state"},
        }
    )
    handler = CleanFillCheckHandler(runtime_monitor=monitor, command_gateway=_Gateway())
    handler._probe_irr_state = AsyncMock(return_value=None)

    outcome = await handler.run(task=_task(control_mode="manual"), plan=_Plan(), stage_def=None, now=NOW)

    assert outcome.kind == "poll"
    handler._probe_irr_state.assert_awaited_once()
