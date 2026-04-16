from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from _test_support_runtime_plan import make_runtime_plan
from ae3lite.application.handlers.await_ready import AwaitReadyHandler
from ae3lite.domain.errors import TaskExecutionError


class _TaskRepoStub:
    def __init__(self, *, updated_task: object = True) -> None:
        self.calls: list[dict] = []
        self._updated_task = updated_task

    async def update_irrigation_runtime(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self._updated_task


def _plan(**runtime_overrides):
    return SimpleNamespace(runtime=make_runtime_plan(**runtime_overrides))


@pytest.mark.asyncio
async def test_await_ready_transitions_to_decision_gate_when_phase_is_ready() -> None:
    handler = AwaitReadyHandler(runtime_monitor=object(), command_gateway=object(), task_repository=_TaskRepoStub())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = SimpleNamespace(id=1, zone_id=7, claimed_by="worker", irrigation_wait_ready_deadline_at=None)
    plan = _plan(zone_workflow_phase="ready")
    out = await handler.run(task=task, plan=plan, stage_def=SimpleNamespace(), now=now)
    assert out.kind == "transition"
    assert out.next_stage == "decision_gate"


@pytest.mark.asyncio
async def test_await_ready_sets_deadline_and_polls_when_not_ready() -> None:
    repo = _TaskRepoStub()
    handler = AwaitReadyHandler(runtime_monitor=object(), command_gateway=object(), task_repository=repo)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = SimpleNamespace(id=1, zone_id=7, claimed_by="worker", irrigation_wait_ready_deadline_at=None)
    plan = _plan(zone_workflow_phase="tank_filling")
    out = await handler.run(task=task, plan=plan, stage_def=SimpleNamespace(), now=now)
    assert out.kind == "poll"
    assert repo.calls
    assert repo.calls[-1]["task_id"] == 1
    assert repo.calls[-1]["irrigation_wait_ready_deadline_at"] > now


@pytest.mark.asyncio
async def test_await_ready_raises_when_deadline_persist_fails() -> None:
    handler = AwaitReadyHandler(
        runtime_monitor=object(),
        command_gateway=object(),
        task_repository=_TaskRepoStub(updated_task=None),
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = SimpleNamespace(id=1, zone_id=7, claimed_by="worker", irrigation_wait_ready_deadline_at=None)
    plan = _plan(zone_workflow_phase="tank_filling")

    with pytest.raises(TaskExecutionError, match="Не удалось сохранить deadline wait_ready"):
        await handler.run(task=task, plan=plan, stage_def=SimpleNamespace(), now=now)


@pytest.mark.asyncio
async def test_await_ready_raises_when_owner_missing() -> None:
    handler = AwaitReadyHandler(runtime_monitor=object(), command_gateway=object(), task_repository=_TaskRepoStub())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = SimpleNamespace(id=1, zone_id=7, claimed_by=None, irrigation_wait_ready_deadline_at=None)
    plan = _plan(zone_workflow_phase="tank_filling")

    with pytest.raises(TaskExecutionError, match="отсутствует owner"):
        await handler.run(task=task, plan=plan, stage_def=SimpleNamespace(), now=now)


@pytest.mark.asyncio
async def test_await_ready_fails_on_deadline_exceeded() -> None:
    handler = AwaitReadyHandler(runtime_monitor=object(), command_gateway=object(), task_repository=_TaskRepoStub())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = SimpleNamespace(
        id=1,
        zone_id=7,
        claimed_by="worker",
        irrigation_wait_ready_deadline_at=now - timedelta(seconds=1),
    )
    plan = _plan(zone_workflow_phase="startup")
    out = await handler.run(task=task, plan=plan, stage_def=SimpleNamespace(), now=now)
    assert out.kind == "fail"
    assert out.error_code == "irrigation_wait_ready_timeout"


@pytest.mark.asyncio
async def test_await_ready_timeout_emits_zone_event_and_biz_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[int, str, dict | None]] = []

    async def fake_create_zone_event(zone_id: int, event_type: str, details=None):
        events.append((zone_id, event_type, details))

    alerts: list[dict] = []

    async def fake_send_biz_alert(**kwargs):
        alerts.append(dict(kwargs))
        return True

    monkeypatch.setattr(
        "ae3lite.application.handlers.await_ready.create_zone_event",
        fake_create_zone_event,
    )
    monkeypatch.setattr(
        "ae3lite.application.handlers.await_ready.send_biz_alert",
        fake_send_biz_alert,
    )

    handler = AwaitReadyHandler(runtime_monitor=object(), command_gateway=object(), task_repository=_TaskRepoStub())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = SimpleNamespace(
        id=42,
        zone_id=7,
        claimed_by="worker",
        irrigation_wait_ready_deadline_at=now - timedelta(seconds=1),
        topology="two_tank",
    )
    plan = _plan(zone_workflow_phase="startup", grow_cycle_id=99)
    out = await handler.run(task=task, plan=plan, stage_def=SimpleNamespace(), now=now)
    assert out.kind == "fail"
    assert len(events) == 1
    assert events[0][0] == 7
    assert events[0][1] == "IRRIGATION_WAIT_READY_TIMEOUT"
    assert events[0][2] is not None
    assert events[0][2]["task_id"] == 42
    assert events[0][2]["workflow_phase"] == "startup"
    assert events[0][2]["grow_cycle_id"] == 99
    assert len(alerts) == 1
    assert alerts[0]["code"] == "biz_irrigation_wait_ready_timeout"
    assert alerts[0]["zone_id"] == 7
    assert "ae3_irr_wait_ready_timeout|z7|t42" in (alerts[0].get("dedupe_key") or "")
