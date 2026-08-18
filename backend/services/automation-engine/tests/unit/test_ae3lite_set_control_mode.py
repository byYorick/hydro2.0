from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from ae3lite.application.use_cases.set_control_mode import SetControlModeUseCase


NOW = datetime(2026, 3, 14, 15, 20, 0, tzinfo=timezone.utc)


class _TaskRepository:
    def __init__(self, *, active_task: object | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_calls: list[dict[str, object]] = []
        self._active_task = active_task

    async def update_control_mode_snapshot_for_zone(self, *, zone_id: int, control_mode: str, now: datetime) -> None:
        self.calls.append({"zone_id": zone_id, "control_mode": control_mode, "now": now})

    async def get_active_for_zone(self, *, zone_id: int) -> object | None:
        return self._active_task

    async def fail_for_recovery(self, *, task_id, error_code, error_message, now) -> object:
        self.fail_calls.append(
            {"task_id": task_id, "error_code": error_code, "error_message": error_message, "now": now}
        )
        return self._active_task


async def test_set_control_mode_updates_zone_and_active_snapshot(monkeypatch) -> None:
    executed: list[tuple[str, tuple[object, ...]]] = []

    async def execute_fn(query: str, *args: object) -> str:
        executed.append((query, args))
        return "UPDATE 1"

    async def fetch_fn(query: str, *args: object):
        return [{"control_mode": "auto"}]

    monkeypatch.setattr(
        "ae3lite.application.use_cases.set_control_mode.create_zone_event",
        AsyncMock(return_value=None),
    )

    repo = _TaskRepository()
    result = await SetControlModeUseCase(
        task_repository=repo,
        execute_fn=execute_fn,
        fetch_fn=fetch_fn,
        command_gateway=SimpleNamespace(run_publish_only_batch=AsyncMock()),
    ).run(zone_id=7, control_mode="manual", now=NOW)

    assert result == "manual"
    assert executed
    assert repo.calls == [{"zone_id": 7, "control_mode": "manual", "now": NOW}]
    assert repo.fail_calls == []


async def test_set_control_mode_manual_publishes_fail_safe_stop_before_failing_irrigation_task(
    monkeypatch,
) -> None:
    published: list[dict[str, object]] = []

    async def execute_fn(query: str, *args: object) -> str:
        return "UPDATE 1"

    async def fetch_fn(query: str, *args: object):
        return [{"control_mode": "auto"}]

    async def run_publish_only_batch(*, task, commands, now):
        published.append(
            {
                "task_id": getattr(task, "id", None),
                "channels": [cmd.channel for cmd in commands],
                "now": now,
            }
        )
        return {"success": True}

    monkeypatch.setattr(
        "ae3lite.application.use_cases.set_control_mode.create_zone_event",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.load_irrig_fail_safe_actuators",
        AsyncMock(
            return_value=(
                {"node_uid": "irrig-1", "node_type": "irrig", "channel": "pump_main"},
                {"node_uid": "irrig-1", "node_type": "irrig", "channel": "valve_irrigation"},
                {"node_uid": "irrig-1", "node_type": "irrig", "channel": "valve_solution_supply"},
            )
        ),
    )

    active_task = SimpleNamespace(
        id=42,
        zone_id=7,
        topology="two_tank",
        current_stage="irrigation_check",
        task_type="irrigation_start",
        claimed_by="w1",
        correction=None,
        workflow=SimpleNamespace(control_mode="auto", workflow_phase="irrigating", stage_entered_at=None, corr_step=None),
    )
    repo = _TaskRepository(active_task=active_task)
    result = await SetControlModeUseCase(
        task_repository=repo,
        execute_fn=execute_fn,
        fetch_fn=fetch_fn,
        command_gateway=SimpleNamespace(run_publish_only_batch=run_publish_only_batch),
    ).run(zone_id=7, control_mode="manual", now=NOW)

    assert result == "manual"
    assert published, "fail-safe shutdown must publish stop commands before fail"
    assert published[0]["channels"][0] == "pump_main"
    assert "valve_irrigation" in published[0]["channels"]
    assert repo.fail_calls
    assert repo.fail_calls[0]["error_code"] == "control_mode_switched_to_manual"
    assert repo.fail_calls[0]["task_id"] == 42
