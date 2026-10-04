"""Регрессии S1: failure boundary и loss lease. На старой реализации падают."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from ae3lite.application.services.correction_interrupt_safety import (
    attempt_task_fail_safe_shutdown,
)
from ae3lite.application.use_cases.execute_task import (
    TASK_EXECUTION_TIMEOUT_CANCEL_MSG,
    ExecuteTaskUseCase,
)
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.errors import SnapshotBuildError
from ae3lite.greenhouse_climate.run_tick import _wait_command_terminal
from ae3lite.infrastructure.gateways.sequential_command_gateway import SequentialCommandGateway
from ae3lite.runtime.worker import Ae3RuntimeWorker

NOW = datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc)


def _task(*, stage: str = "irrigation_check") -> AutomationTask:
    return AutomationTask.from_row(
        {
            "id": 99,
            "zone_id": 99,
            "task_type": "irrigation_start",
            "status": "running",
            "idempotency_key": "k99",
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
            "current_stage": stage,
            "workflow_phase": "irrigating",
            "stage_deadline_at": None,
            "stage_retry_count": 0,
            "stage_entered_at": NOW,
            "clean_fill_cycle": 0,
            "corr_step": None,
        }
    )


class _Finalize:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def fail_closed(self, *, task: Any, owner: str, error_code: str, error_message: str, now: datetime) -> Any:
        self.calls.append({"error_code": error_code, "error_message": error_message, "owner": owner})
        return task

    async def complete(self, *, task: Any, owner: str, now: datetime) -> Any:
        raise AssertionError("ordinary complete is not a safety-path")


class _Gateway:
    def __init__(self, *, order: list[str] | None = None, raise_on_stop: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.order = order
        self.raise_on_stop = raise_on_stop

    async def run_batch(self, *, task: Any, commands: Any, now: datetime, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"method": "sequential", "commands": tuple(commands)})
        return {"success": True, "task": task}

    async def run_publish_only_batch(self, *, task: Any, commands: Any, now: datetime) -> dict[str, Any]:
        if self.order is not None:
            self.order.append("stop")
        self.calls.append({"method": "publish_only", "commands": tuple(commands)})
        if self.raise_on_stop:
            raise RuntimeError("stop transport down")
        return {"success": True, "task": task, "command_statuses": []}


def _use_case(gateway: _Gateway, finalize: _Finalize | None = None) -> ExecuteTaskUseCase:
    return ExecuteTaskUseCase(
        task_repository=SimpleNamespace(),
        zone_snapshot_read_model=SimpleNamespace(),
        planner=SimpleNamespace(),
        command_gateway=gateway,
        workflow_router=SimpleNamespace(),
        finalize_task_use_case=finalize or _Finalize(),
    )


def _irrig_actuators() -> tuple[dict[str, str], ...]:
    return (
        {"node_uid": "irr-pump", "node_type": "irrig", "channel": "pump_main"},
        {"node_uid": "irr-valve", "node_type": "irrig", "channel": "valve_irrigation"},
    )


def _patch_actuators(monkeypatch: pytest.MonkeyPatch, *, fail: bool = False) -> None:
    async def _load(*, zone_id: int) -> tuple[dict[str, str], ...]:
        if fail:
            raise RuntimeError("actuators unreadable")
        return _irrig_actuators()

    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.load_irrig_fail_safe_actuators",
        _load,
    )


def _assert_fail_safe_off(commands: tuple[Any, ...]) -> None:
    assert commands
    cmds = [str(command.payload.get("cmd") or "") for command in commands]
    assert "dose" not in cmds
    assert "run_pump" not in cmds
    channels = {command.channel for command in commands}
    assert "valve_irrigation" in channels
    for command in commands:
        assert command.payload.get("cmd") == "set_relay"
        assert command.payload.get("params", {}).get("state") is False
        assert command.payload.get("_ae3_fail_safe") is True
        assert command.payload.get("allow_no_effect") is True


@pytest.fixture
def _silence_zone_events(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("ae3lite.application.use_cases.execute_task.create_zone_event", _noop)
    monkeypatch.setattr("ae3lite.application.use_cases.execute_task.send_infra_alert", _noop)
    monkeypatch.setattr("ae3lite.application.use_cases.execute_task.send_biz_alert", _noop)


@pytest.mark.asyncio
async def test_preflight_snapshot_error_on_check_stage_runs_fail_safe_not_dose(
    monkeypatch: pytest.MonkeyPatch,
    _silence_zone_events: None,
) -> None:
    _patch_actuators(monkeypatch)
    gateway = _Gateway()
    finalize = _Finalize()
    use_case = _use_case(gateway, finalize)

    async def _boom(*, task: Any) -> None:
        raise SnapshotBuildError("required node offline", code="ae3_required_node_offline")

    monkeypatch.setattr(use_case, "_preflight_required_nodes_online", _boom)
    task = _task()

    class _Repo:
        async def mark_running(self, *, task_id: int, owner: str, now: datetime, claim_generation: int = 0) -> Any:
            return task

        async def get_by_id(self, *, task_id: int) -> Any:
            return task

    use_case._task_repository = _Repo()
    await use_case.run(task=task, now=NOW)

    assert finalize.calls
    assert finalize.calls[0]["error_code"] == "ae3_required_node_offline"
    publish = [call for call in gateway.calls if call["method"] == "publish_only"]
    sequential = [call for call in gateway.calls if call["method"] == "sequential"]
    assert sequential == []
    assert len(publish) == 1
    _assert_fail_safe_off(publish[0]["commands"])


@pytest.mark.asyncio
async def test_preflight_runtime_error_also_runs_safety_path(
    monkeypatch: pytest.MonkeyPatch,
    _silence_zone_events: None,
) -> None:
    _patch_actuators(monkeypatch)
    gateway = _Gateway()
    finalize = _Finalize()
    use_case = _use_case(gateway, finalize)

    async def _boom(*, task: Any) -> None:
        raise RuntimeError("diagnostics db down")

    monkeypatch.setattr(use_case, "_preflight_required_nodes_online", _boom)
    task = _task()

    class _Repo:
        async def mark_running(self, *, task_id: int, owner: str, now: datetime, claim_generation: int = 0) -> Any:
            return task

        async def get_by_id(self, *, task_id: int) -> Any:
            return task

    use_case._task_repository = _Repo()
    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == "ae3_task_execution_unhandled_exception"
    assert gateway.calls[0]["method"] == "publish_only"
    _assert_fail_safe_off(gateway.calls[0]["commands"])


@pytest.mark.asyncio
async def test_marked_timeout_during_preflight_runs_safety_path_bare_cancel_propagates(
    monkeypatch: pytest.MonkeyPatch,
    _silence_zone_events: None,
) -> None:
    _patch_actuators(monkeypatch)
    gateway = _Gateway()
    finalize = _Finalize()
    use_case = _use_case(gateway, finalize)
    task = _task()

    class _Repo:
        async def mark_running(self, *, task_id: int, owner: str, now: datetime, claim_generation: int = 0) -> Any:
            return task

        async def get_by_id(self, *, task_id: int) -> Any:
            return task

    use_case._task_repository = _Repo()

    async def _no_offline(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(use_case, "_resolve_offline_failure_instead_of_guard", _no_offline)

    async def _timeout(*, task: Any) -> None:
        raise asyncio.CancelledError(TASK_EXECUTION_TIMEOUT_CANCEL_MSG)

    monkeypatch.setattr(use_case, "_preflight_required_nodes_online", _timeout)
    await use_case.run(task=task, now=NOW)
    assert finalize.calls[0]["error_code"] == TASK_EXECUTION_TIMEOUT_CANCEL_MSG
    assert gateway.calls[0]["method"] == "publish_only"

    gateway.calls.clear()
    finalize.calls.clear()

    async def _bare(*, task: Any) -> None:
        raise asyncio.CancelledError()

    monkeypatch.setattr(use_case, "_preflight_required_nodes_online", _bare)
    with pytest.raises(asyncio.CancelledError):
        await use_case.run(task=task, now=NOW)
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_repeated_failure_completion_does_not_loop_or_start_batch(
    monkeypatch: pytest.MonkeyPatch,
    _silence_zone_events: None,
) -> None:
    _patch_actuators(monkeypatch)
    gateway = _Gateway()
    finalize = _Finalize()
    use_case = _use_case(gateway, finalize)
    task = _task()

    await use_case.complete_execution_failure(
        task=task,
        snapshot=None,
        plan=None,
        now=NOW,
        owner="w1",
        error_code="ae3_task_execution_crashed",
        error_message="boom",
    )
    await use_case.complete_execution_failure(
        task=task,
        snapshot=None,
        plan=None,
        now=NOW,
        owner="w1",
        error_code="ae3_task_execution_crashed",
        error_message="boom",
    )

    assert len(finalize.calls) == 1
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["method"] == "publish_only"
    assert all(call["method"] != "sequential" for call in gateway.calls)


@pytest.mark.asyncio
async def test_unconfirmed_stop_does_not_claim_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alerts: list[dict[str, Any]] = []

    async def _alert(**kwargs: Any) -> bool:
        alerts.append(kwargs)
        return True

    monkeypatch.setattr("ae3lite.application.use_cases.execute_task.send_biz_alert", _alert)
    task = _task()
    gateway = _Gateway(raise_on_stop=True)
    use_case = _use_case(gateway)

    _patch_actuators(monkeypatch, fail=True)
    await use_case._attempt_fail_safe_shutdown(task=task, snapshot=None, plan=None, now=NOW)
    assert gateway.calls == []
    assert alerts[-1]["code"] == "biz_flow_stop_failed_hardware_may_be_active"
    assert alerts[-1]["severity"] == "critical"
    assert alerts[-1]["details"]["reason"] == "actuators_load_failed"

    _patch_actuators(monkeypatch, fail=False)
    alerts.clear()
    await use_case._attempt_fail_safe_shutdown(task=task, snapshot=None, plan=None, now=NOW)
    assert alerts[-1]["details"]["reason"] == "fail_safe_shutdown_exception"
    assert getattr(task, "status", "") != "completed"

    result = await attempt_task_fail_safe_shutdown(
        task=task,
        now=NOW,
        command_gateway=_Gateway(),
        snapshot_actuators=_irrig_actuators(),
    )
    assert result.confirmed is False
    assert result.reason == "publish_accepted_unconfirmed"


@pytest.mark.asyncio
async def test_publish_only_fanout_continues_when_pump_node_fails() -> None:
    published: list[str] = []

    async def _publish(*, task: Any, command: PlannedCommand, now: datetime, seq_index: int) -> dict[str, Any]:
        published.append(command.channel)
        if command.channel == "pump_main":
            raise RuntimeError("pump node down")
        return {"success": True, "task": task, "command_statuses": [{"channel": command.channel}]}

    gateway = SequentialCommandGateway(
        task_repository=SimpleNamespace(),
        command_repository=SimpleNamespace(),
        history_logger_client=SimpleNamespace(),
        poll_interval_sec=0.05,
    )
    gateway._publish_without_terminal = _publish  # type: ignore[method-assign]
    commands = (
        PlannedCommand(
            step_no=1,
            node_uid="irr-pump",
            channel="pump_main",
            payload={"cmd": "set_relay", "params": {"state": False}, "allow_no_effect": True, "_ae3_fail_safe": True},
        ),
        PlannedCommand(
            step_no=2,
            node_uid="irr-valve",
            channel="valve_irrigation",
            payload={"cmd": "set_relay", "params": {"state": False}, "allow_no_effect": True, "_ae3_fail_safe": True},
        ),
    )
    result = await gateway.run_publish_only_batch(task=_task(), commands=commands, now=NOW)
    assert published[0] == "pump_main"
    assert "valve_irrigation" in published
    assert result["success"] is False
    assert result["command_statuses"]
    assert all(status.get("terminal_status") is None for status in result["command_statuses"])


@pytest.mark.asyncio
async def test_worker_crash_on_check_stage_stops_before_lease_release(
    monkeypatch: pytest.MonkeyPatch,
    _silence_zone_events: None,
) -> None:
    _patch_actuators(monkeypatch)
    order: list[str] = []
    gateway = _Gateway(order=order)
    finalize = _Finalize()
    use_case = _use_case(gateway, finalize)

    async def _boom(*, task: Any, now: datetime) -> Any:
        raise RuntimeError("check-stage preflight escaped")

    use_case.run = _boom  # type: ignore[method-assign]

    class _Lease:
        async def release(self, *, zone_id: int, owner: str, claim_generation: int = 0) -> bool:
            order.append("release")
            return True

        async def get(self, *, zone_id: int) -> None:
            return None

        async def extend(self, **_kwargs: Any) -> bool:
            return True

    worker = Ae3RuntimeWorker(
        owner="w1",
        claim_next_task_use_case=SimpleNamespace(),
        idle_poll_interval_sec=0.1,
        execute_task_use_case=use_case,
        startup_recovery_use_case=SimpleNamespace(),
        zone_lease_repository=_Lease(),
        zone_intent_repository=SimpleNamespace(),
        command_gateway=gateway,
        spawn_background_task_fn=lambda coro, **_: asyncio.create_task(coro),
        now_fn=lambda: NOW,
        logger=logging.getLogger("s1-worker"),
        lease_ttl_sec=90,
        max_task_execution_sec=5,
    )
    await worker._execute_claimed_task(task=_task())

    assert order[0] == "stop"
    assert "release" in order
    assert order.index("stop") < order.index("release")
    assert finalize.calls[0]["error_code"] == "ae3_task_execution_crashed"
    _assert_fail_safe_off(gateway.calls[0]["commands"])
    assert all(call["method"] != "sequential" for call in gateway.calls)


@pytest.mark.asyncio
async def test_wait_command_terminal_lease_false_and_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _done(*_args: Any, **_kwargs: Any) -> list[dict[str, str]]:
        return [{"status": "DONE"}]

    monkeypatch.setattr("ae3lite.greenhouse_climate.run_tick.fetch", _done)

    async def _false() -> bool:
        return False

    assert await _wait_command_terminal("cmd", timeout_sec=1, poll_sec=0.05, lease_renew=_false) == "LEASE_LOST"

    async def _retry_then_ok() -> bool | None:
        if not getattr(_retry_then_ok, "used", False):
            _retry_then_ok.used = True  # type: ignore[attr-defined]
            return None
        return True

    assert await _wait_command_terminal("cmd", timeout_sec=1, poll_sec=0.05, lease_renew=_retry_then_ok) == "DONE"

    async def _cancel() -> bool:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await _wait_command_terminal("cmd", timeout_sec=1, poll_sec=0.05, lease_renew=_cancel)

    async def _db_down() -> bool:
        raise RuntimeError("db")

    assert await _wait_command_terminal("cmd", timeout_sec=1, poll_sec=0.05, lease_renew=_db_down) == "LEASE_LOST"


@pytest.mark.asyncio
async def test_concurrent_failures_in_two_zones_each_stop_and_finalize(monkeypatch, _silence_zone_events):
    from dataclasses import replace
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    stopped = []
    finalize = _Finalize()
    use_case = _use_case(_Gateway(), finalize)

    async def stop(*, task, **kwargs):
        stopped.append(task.id)
        if task.id == 99:
            first_entered.set()
            await release_first.wait()

    monkeypatch.setattr(use_case, "_attempt_fail_safe_shutdown", stop)
    first = _task()
    second = replace(first, id=100, zone_id=100)

    async def fail(task):
        return await use_case.complete_execution_failure(
            task=task, snapshot=None, plan=None, now=NOW, owner="w1",
            error_code="test_failure", error_message="boom",
        )

    running = asyncio.create_task(fail(first))
    try:
        await asyncio.wait_for(first_entered.wait(), timeout=1)
        await asyncio.wait_for(fail(second), timeout=1)
        assert stopped == [99, 100]
        assert len(finalize.calls) == 1
    finally:
        release_first.set()
        await running
    assert len(finalize.calls) == 2


@pytest.mark.asyncio
async def test_stale_failure_never_borrows_new_claim_for_stop_or_workflow(monkeypatch, _silence_zone_events):
    from dataclasses import replace
    from unittest.mock import AsyncMock
    _patch_actuators(monkeypatch)
    task = _task()
    newer = replace(task, claim_generation=task.claim_generation + 1)
    gateway = _Gateway()
    finalize = _Finalize()
    use_case = _use_case(gateway, finalize)
    use_case._task_repository = SimpleNamespace(get_by_id=AsyncMock(return_value=newer))
    workflow = AsyncMock()
    monkeypatch.setattr(use_case, "_sync_workflow_failure_state", workflow)
    result = await use_case.complete_execution_failure(
        task=task, snapshot=None, plan=None, now=NOW, owner="w1",
        error_code="stale_failure", error_message="boom",
    )
    assert result is newer
    assert not gateway.calls
    assert not finalize.calls
    workflow.assert_not_awaited()
