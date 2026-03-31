from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from ae3lite.application.handlers.await_ready import AwaitReadyHandler


class _TaskRepoStub:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def update_irrigation_runtime(self, **kwargs):
        self.calls.append(dict(kwargs))
        return True


@pytest.mark.asyncio
async def test_await_ready_transitions_to_decision_gate_when_phase_is_ready() -> None:
    handler = AwaitReadyHandler(runtime_monitor=object(), command_gateway=object(), task_repository=_TaskRepoStub())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = SimpleNamespace(id=1, zone_id=7, claimed_by="worker", irrigation_wait_ready_deadline_at=None)
    plan = SimpleNamespace(runtime={"zone_workflow_phase": "ready"})
    out = await handler.run(task=task, plan=plan, stage_def=SimpleNamespace(), now=now)
    assert out.kind == "transition"
    assert out.next_stage == "decision_gate"


@pytest.mark.asyncio
async def test_await_ready_sets_deadline_and_polls_when_not_ready() -> None:
    repo = _TaskRepoStub()
    handler = AwaitReadyHandler(runtime_monitor=object(), command_gateway=object(), task_repository=repo)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = SimpleNamespace(id=1, zone_id=7, claimed_by="worker", irrigation_wait_ready_deadline_at=None)
    plan = SimpleNamespace(runtime={"zone_workflow_phase": "tank_filling"})
    out = await handler.run(task=task, plan=plan, stage_def=SimpleNamespace(), now=now)
    assert out.kind == "poll"
    assert repo.calls
    assert repo.calls[-1]["task_id"] == 1
    assert repo.calls[-1]["irrigation_wait_ready_deadline_at"] > now


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
    plan = SimpleNamespace(runtime={"zone_workflow_phase": "startup"})
    out = await handler.run(task=task, plan=plan, stage_def=SimpleNamespace(), now=now)
    assert out.kind == "fail"
    assert out.error_code == "irrigation_wait_ready_timeout"

