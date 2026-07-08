"""Тесты реактивного solution_topup по level_switch_changed."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ae3lite.application.use_cases.trigger_solution_topup_from_level_event import (
    TriggerSolutionTopupFromLevelEventUseCase,
)
from ae3lite.domain.errors import TaskCreateError

NOW = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)


def _level_event(*, channel: str = "level_solution_max", state: bool = False, initial: bool = False) -> dict:
    return {
        "zone_id": 5,
        "event_type": "LEVEL_SWITCH_CHANGED",
        "source": "node_event",
        "channel": channel,
        "state": state,
        "initial": initial,
    }


@pytest.mark.asyncio
async def test_trigger_skips_non_solution_max_channel() -> None:
    use_case = TriggerSolutionTopupFromLevelEventUseCase(
        zone_intent_repository=AsyncMock(),
        create_task_from_intent_use_case=AsyncMock(),
        fetch_fn=AsyncMock(),
    )
    result = await use_case.run(
        zone_id=5,
        event_data=_level_event(channel="level_solution_min", state=False),
        now=NOW,
    )
    assert result["triggered"] is False
    assert result["reason"] == "channel_not_solution_max"


@pytest.mark.asyncio
async def test_trigger_skips_initial_event() -> None:
    use_case = TriggerSolutionTopupFromLevelEventUseCase(
        zone_intent_repository=AsyncMock(),
        create_task_from_intent_use_case=AsyncMock(),
        fetch_fn=AsyncMock(),
    )
    result = await use_case.run(
        zone_id=5,
        event_data=_level_event(initial=True),
        now=NOW,
    )
    assert result["triggered"] is False
    assert result["reason"] == "initial_event_skipped"


@pytest.mark.asyncio
async def test_trigger_starts_topup_when_preconditions_met(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fetch_fn(query: str, *args: object):
        if "FROM zones z" in query:
            return [{"automation_runtime": "ae3", "workflow_phase": "ready"}]
        if "FROM ae_tasks" in query:
            return []
        if "FROM grow_cycles" in query or "FROM zone_automation_intents" in query:
            return []
        return []

    monkeypatch.setattr(
        "ae3lite.application.use_cases.trigger_solution_topup_from_level_event.load_zone_level_monitor_config",
        AsyncMock(return_value={
            "solution_min_sensor_labels": ("level_solution_min",),
            "solution_max_sensor_labels": ("level_solution_max",),
            "level_switch_on_threshold": 0.5,
            "telemetry_max_age_sec": 60,
        }),
    )
    runtime_monitor = AsyncMock()
    runtime_monitor.read_level_switch = AsyncMock(side_effect=[
        {"is_triggered": True, "has_level": True},
        {"is_triggered": False, "has_level": True},
    ])
    zone_intent_repository = AsyncMock()
    zone_intent_repository.upsert_solution_topup_intent = AsyncMock(return_value=91)
    zone_intent_repository.claim_start_solution_topup = AsyncMock(return_value={
        "decision": "claimed",
        "intent": {
            "id": 91,
            "zone_id": 5,
            "task_type": "solution_topup",
            "topology": "two_tank_drip_substrate_trays",
            "intent_type": "SOLUTION_TOPUP",
            "payload": {"mode": "normal", "trigger": "level_switch"},
        },
    })
    create_task = AsyncMock()
    create_task.run = AsyncMock(return_value=SimpleNamespace(task=SimpleNamespace(id=501)))
    use_case = TriggerSolutionTopupFromLevelEventUseCase(
        zone_intent_repository=zone_intent_repository,
        create_task_from_intent_use_case=create_task,
        runtime_monitor=runtime_monitor,
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=5, event_data=_level_event(), now=NOW)

    assert result["triggered"] is True
    assert result["task_id"] == 501
    zone_intent_repository.upsert_solution_topup_intent.assert_awaited_once()
    create_task.run.assert_awaited_once()
    assert create_task.run.await_args.kwargs["solution_topup_trigger"] == "level_switch"


@pytest.mark.asyncio
async def test_trigger_maps_task_create_precondition_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fetch_fn(query: str, *args: object):
        if "FROM zones z" in query:
            return [{"automation_runtime": "ae3", "workflow_phase": "ready"}]
        if "FROM ae_tasks" in query:
            return []
        return []

    monkeypatch.setattr(
        "ae3lite.application.use_cases.trigger_solution_topup_from_level_event.load_zone_level_monitor_config",
        AsyncMock(return_value={
            "solution_min_sensor_labels": ("level_solution_min",),
            "solution_max_sensor_labels": ("level_solution_max",),
            "level_switch_on_threshold": 0.5,
            "telemetry_max_age_sec": 60,
        }),
    )
    runtime_monitor = AsyncMock()
    runtime_monitor.read_level_switch = AsyncMock(side_effect=[
        {"is_triggered": True, "has_level": True},
        {"is_triggered": False, "has_level": True},
    ])
    zone_intent_repository = AsyncMock()
    zone_intent_repository.upsert_solution_topup_intent = AsyncMock(return_value=91)
    zone_intent_repository.claim_start_solution_topup = AsyncMock(return_value={
        "decision": "claimed",
        "intent": {
            "id": 91,
            "zone_id": 5,
            "task_type": "solution_topup",
            "topology": "two_tank_drip_substrate_trays",
        },
    })
    create_task = AsyncMock()
    create_task.run = AsyncMock(side_effect=TaskCreateError(
        "start_solution_topup_cooldown_active",
        "cooldown",
    ))
    use_case = TriggerSolutionTopupFromLevelEventUseCase(
        zone_intent_repository=zone_intent_repository,
        create_task_from_intent_use_case=create_task,
        runtime_monitor=runtime_monitor,
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=5, event_data=_level_event(), now=NOW)

    assert result["triggered"] is False
    assert result["reason"] == "start_solution_topup_cooldown_active"
