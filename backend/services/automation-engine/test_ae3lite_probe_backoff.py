"""Тесты resilient probe backoff в BaseStageHandler.

Покрывает варианты B (защищённый probe с накапливающимся streak) и C
(skip probe при offline/stale heartbeat ноды).
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import TaskExecutionError


_EXHAUSTED = StageOutcome(kind="fail", error_code="probe_exhausted", error_message="exhausted")


class _TaskRepoStub:
    def __init__(self) -> None:
        self.streak = 0
        self.reset_calls = 0
        self.increment_calls = 0

    async def increment_irr_probe_failure_streak(self, *, task_id: int) -> int:  # noqa: ARG002
        self.streak += 1
        self.increment_calls += 1
        return self.streak

    async def reset_irr_probe_failure_streak(self, *, task_id: int) -> None:  # noqa: ARG002
        self.reset_calls += 1
        self.streak = 0


class _RuntimeMonitorWithLiveness:
    def __init__(self, *, status: str = "online", heartbeat_age_sec: float | None = 1.0) -> None:
        self._status = status
        self._heartbeat_age_sec = heartbeat_age_sec

    async def read_node_liveness(self, *, node_uid: str) -> dict[str, Any]:  # noqa: ARG002
        return {
            "found": True,
            "status": self._status,
            "heartbeat_age_sec": self._heartbeat_age_sec,
            "last_seen_age_sec": self._heartbeat_age_sec,
        }


def _make_task(*, irr_probe_failure_streak: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        id=42,
        zone_id=7,
        irr_probe_failure_streak=irr_probe_failure_streak,
        current_stage="irrigation_check",
        workflow=SimpleNamespace(workflow_phase="irrigating"),
    )


def _make_plan(*, node_uid: str = "nd-irr-1") -> SimpleNamespace:
    cmd = SimpleNamespace(node_uid=node_uid, channel="storage_state")
    return SimpleNamespace(named_plans={"irr_state_probe": (cmd,)}, runtime={})


@pytest.mark.asyncio
async def test_probe_backoff_returns_none_on_success(monkeypatch) -> None:
    repo = _TaskRepoStub()
    handler = BaseStageHandler(
        runtime_monitor=_RuntimeMonitorWithLiveness(),
        command_gateway=object(),
        task_repository=repo,
    )

    async def _probe(**_kwargs):
        return None

    monkeypatch.setattr(handler, "_probe_irr_state", _probe)
    task = _make_task(irr_probe_failure_streak=2)
    plan = _make_plan()

    out = await handler._probe_irr_state_with_backoff(
        task=task,
        plan=plan,
        now=datetime.now(timezone.utc).replace(tzinfo=None),
        expected={"valve_irrigation": True},
        poll_delay_sec=10,
        exhausted_outcome=_EXHAUSTED,
    )

    assert out is None
    assert repo.reset_calls == 1
    assert repo.increment_calls == 0


@pytest.mark.asyncio
async def test_probe_backoff_skips_reset_when_streak_already_zero(monkeypatch) -> None:
    repo = _TaskRepoStub()
    handler = BaseStageHandler(
        runtime_monitor=_RuntimeMonitorWithLiveness(),
        command_gateway=object(),
        task_repository=repo,
    )

    async def _probe(**_kwargs):
        return None

    monkeypatch.setattr(handler, "_probe_irr_state", _probe)

    out = await handler._probe_irr_state_with_backoff(
        task=_make_task(irr_probe_failure_streak=0),
        plan=_make_plan(),
        now=datetime.now(timezone.utc).replace(tzinfo=None),
        expected={"valve_irrigation": True},
        poll_delay_sec=10,
        exhausted_outcome=_EXHAUSTED,
    )

    assert out is None
    assert repo.reset_calls == 0


@pytest.mark.asyncio
async def test_probe_backoff_defers_on_unavailable(monkeypatch) -> None:
    repo = _TaskRepoStub()
    handler = BaseStageHandler(
        runtime_monitor=_RuntimeMonitorWithLiveness(),
        command_gateway=object(),
        task_repository=repo,
    )

    async def _probe(**_kwargs):
        raise TaskExecutionError("irr_state_unavailable", "no snapshot")

    monkeypatch.setattr(handler, "_probe_irr_state", _probe)

    with patch("ae3lite.application.handlers.base.create_zone_event") as zone_event_mock:
        zone_event_mock.return_value = None
        out = await handler._probe_irr_state_with_backoff(
            task=_make_task(),
            plan=_make_plan(),
            now=datetime.now(timezone.utc).replace(tzinfo=None),
            expected={"valve_irrigation": True},
            poll_delay_sec=15,
            exhausted_outcome=_EXHAUSTED,
        )

    assert out is not None
    assert out.kind == "poll"
    assert out.due_delay_sec == 15
    assert repo.increment_calls == 1
    assert repo.streak == 1
    zone_event_mock.assert_called_once()
    args, _ = zone_event_mock.call_args
    assert args[1] == "IRR_STATE_PROBE_DEFERRED"


@pytest.mark.asyncio
async def test_probe_backoff_escalates_on_streak_limit(monkeypatch) -> None:
    repo = _TaskRepoStub()
    repo.streak = BaseStageHandler._IRR_PROBE_FAILURE_STREAK_LIMIT - 1
    handler = BaseStageHandler(
        runtime_monitor=_RuntimeMonitorWithLiveness(),
        command_gateway=object(),
        task_repository=repo,
    )

    async def _probe(**_kwargs):
        raise TaskExecutionError("irr_state_unavailable", "no snapshot")

    monkeypatch.setattr(handler, "_probe_irr_state", _probe)

    with patch("ae3lite.application.handlers.base.create_zone_event") as zone_event_mock, \
            patch("ae3lite.application.handlers.base.send_biz_alert") as alert_mock:
        zone_event_mock.return_value = None
        alert_mock.return_value = True
        out = await handler._probe_irr_state_with_backoff(
            task=_make_task(),
            plan=_make_plan(),
            now=datetime.now(timezone.utc).replace(tzinfo=None),
            expected={"valve_irrigation": True},
            poll_delay_sec=10,
            exhausted_outcome=_EXHAUSTED,
        )

    assert out is _EXHAUSTED
    args, _ = zone_event_mock.call_args
    assert args[1] == "IRR_STATE_PROBE_STREAK_EXHAUSTED"
    alert_mock.assert_called_once()
    _, alert_kwargs = alert_mock.call_args
    assert alert_kwargs["code"] == "biz_irr_probe_streak_exhausted"
    assert alert_kwargs["severity"] == "warning"


@pytest.mark.asyncio
async def test_probe_backoff_skips_on_offline_node(monkeypatch) -> None:
    repo = _TaskRepoStub()
    handler = BaseStageHandler(
        runtime_monitor=_RuntimeMonitorWithLiveness(status="offline", heartbeat_age_sec=120.0),
        command_gateway=object(),
        task_repository=repo,
    )
    probe_calls = 0

    async def _probe(**_kwargs):
        nonlocal probe_calls
        probe_calls += 1

    monkeypatch.setattr(handler, "_probe_irr_state", _probe)

    with patch("ae3lite.application.handlers.base.create_zone_event") as zone_event_mock:
        zone_event_mock.return_value = None
        out = await handler._probe_irr_state_with_backoff(
            task=_make_task(),
            plan=_make_plan(),
            now=datetime.now(timezone.utc).replace(tzinfo=None),
            expected={"valve_irrigation": True},
            poll_delay_sec=10,
            exhausted_outcome=_EXHAUSTED,
        )

    assert out is not None
    assert out.kind == "poll"
    assert probe_calls == 0  # HL roundtrip skipped
    assert repo.increment_calls == 1


@pytest.mark.asyncio
async def test_probe_backoff_defers_on_stale_heartbeat(monkeypatch) -> None:
    repo = _TaskRepoStub()
    handler = BaseStageHandler(
        runtime_monitor=_RuntimeMonitorWithLiveness(status="online", heartbeat_age_sec=120.0),
        command_gateway=object(),
        task_repository=repo,
    )
    probe_calls = 0

    async def _probe(**_kwargs):
        nonlocal probe_calls
        probe_calls += 1

    monkeypatch.setattr(handler, "_probe_irr_state", _probe)

    with patch("ae3lite.application.handlers.base.create_zone_event") as zone_event_mock:
        zone_event_mock.return_value = None
        out = await handler._probe_irr_state_with_backoff(
            task=_make_task(),
            plan=_make_plan(),
            now=datetime.now(timezone.utc).replace(tzinfo=None),
            expected={"valve_irrigation": True},
            poll_delay_sec=10,
            exhausted_outcome=_EXHAUSTED,
        )

    assert out is not None
    assert out.kind == "poll"
    assert probe_calls == 0


@pytest.mark.asyncio
async def test_probe_backoff_propagates_mismatch(monkeypatch) -> None:
    repo = _TaskRepoStub()
    handler = BaseStageHandler(
        runtime_monitor=_RuntimeMonitorWithLiveness(),
        command_gateway=object(),
        task_repository=repo,
    )

    async def _probe(**_kwargs):
        raise TaskExecutionError("irr_state_mismatch", "valve mismatch")

    monkeypatch.setattr(handler, "_probe_irr_state", _probe)

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler._probe_irr_state_with_backoff(
            task=_make_task(),
            plan=_make_plan(),
            now=datetime.now(timezone.utc).replace(tzinfo=None),
            expected={"valve_irrigation": True},
            poll_delay_sec=10,
            exhausted_outcome=_EXHAUSTED,
        )

    assert exc_info.value.code == "irr_state_mismatch"
    assert repo.increment_calls == 0
    assert repo.reset_calls == 0


@pytest.mark.asyncio
async def test_probe_backoff_falls_back_to_strict_probe_without_repo(monkeypatch) -> None:
    """Если task_repository не передан — используется штатный _probe_irr_state."""
    handler = BaseStageHandler(
        runtime_monitor=_RuntimeMonitorWithLiveness(),
        command_gateway=object(),
        task_repository=None,
    )
    probe_calls = 0

    async def _probe(**_kwargs):
        nonlocal probe_calls
        probe_calls += 1

    monkeypatch.setattr(handler, "_probe_irr_state", _probe)

    out = await handler._probe_irr_state_with_backoff(
        task=_make_task(),
        plan=_make_plan(),
        now=datetime.now(timezone.utc).replace(tzinfo=None),
        expected={"valve_irrigation": True},
        poll_delay_sec=10,
        exhausted_outcome=_EXHAUSTED,
    )

    assert out is None
    assert probe_calls == 1
