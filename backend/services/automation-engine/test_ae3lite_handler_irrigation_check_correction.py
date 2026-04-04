from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from ae3lite.application.handlers.irrigation_check import IrrigationCheckHandler


class _TaskRepoStub:
    async def update_irrigation_runtime(self, **_kwargs):
        return True


@pytest.mark.asyncio
async def test_irrigation_check_enters_correction_when_targets_not_met_and_flag_enabled(monkeypatch) -> None:
    handler = IrrigationCheckHandler(runtime_monitor=object(), command_gateway=object(), task_repository=_TaskRepoStub())

    async def _probe(**_kwargs):
        return None

    async def _targets(**_kwargs):
        return False

    monkeypatch.setattr(handler, "_probe_irr_state", _probe)
    monkeypatch.setattr(handler, "_targets_reached", _targets)
    monkeypatch.setattr(handler, "_correction_config_for_task", lambda **_kwargs: {"max_ec_correction_attempts": 2, "max_ph_correction_attempts": 2, "stabilization_sec": 1})

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = SimpleNamespace(
        id=1,
        zone_id=7,
        topology="two_tank",
        claimed_by="worker",
        irrigation_replay_count=0,
        workflow=SimpleNamespace(
            control_mode="auto",
            pending_manual_step=None,
            stage_deadline_at=now + timedelta(seconds=60),
            stage_retry_count=0,
            stage_entered_at=now - timedelta(seconds=10),
        ),
    )
    plan = SimpleNamespace(
        runtime={
            "level_poll_interval_sec": 5,
            "irrigation_execution": {"correction_during_irrigation": True},
            "irrigation_safety": {"stop_on_solution_min": False},
        }
    )
    stage_def = SimpleNamespace(on_corr_success="irrigation_check", on_corr_fail="irrigation_check")
    out = await handler.run(task=task, plan=plan, stage_def=stage_def, now=now)
    assert out.kind == "enter_correction"
    assert out.correction is not None
    assert out.correction.return_stage_success == "irrigation_check"


@pytest.mark.asyncio
async def test_irrigation_check_skips_correction_when_flag_disabled(monkeypatch) -> None:
    handler = IrrigationCheckHandler(runtime_monitor=object(), command_gateway=object(), task_repository=_TaskRepoStub())

    async def _probe(**_kwargs):
        return None

    async def _targets(**_kwargs):
        return False

    monkeypatch.setattr(handler, "_probe_irr_state", _probe)
    monkeypatch.setattr(handler, "_targets_reached", _targets)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = SimpleNamespace(
        id=1,
        zone_id=7,
        topology="two_tank",
        claimed_by="worker",
        irrigation_replay_count=0,
        workflow=SimpleNamespace(
            control_mode="auto",
            pending_manual_step=None,
            stage_deadline_at=now + timedelta(seconds=60),
            stage_retry_count=0,
            stage_entered_at=now - timedelta(seconds=10),
        ),
    )
    plan = SimpleNamespace(
        runtime={
            "level_poll_interval_sec": 5,
            "irrigation_execution": {"correction_during_irrigation": False},
            "irrigation_safety": {"stop_on_solution_min": False},
        }
    )
    stage_def = SimpleNamespace(on_corr_success="irrigation_check", on_corr_fail="irrigation_check")
    out = await handler.run(task=task, plan=plan, stage_def=stage_def, now=now)
    assert out.kind == "poll"


@pytest.mark.asyncio
async def test_irrigation_check_skips_correction_when_already_exhausted(monkeypatch) -> None:
    handler = IrrigationCheckHandler(runtime_monitor=object(), command_gateway=object(), task_repository=_TaskRepoStub())

    async def _probe(**_kwargs):
        return None

    async def _targets(**_kwargs):
        return False

    monkeypatch.setattr(handler, "_probe_irr_state", _probe)
    monkeypatch.setattr(handler, "_targets_reached", _targets)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = SimpleNamespace(
        id=1,
        zone_id=7,
        topology="two_tank",
        claimed_by="worker",
        irrigation_replay_count=0,
        workflow=SimpleNamespace(
            control_mode="auto",
            pending_manual_step=None,
            stage_deadline_at=now + timedelta(seconds=60),
            stage_retry_count=1,
            stage_entered_at=now - timedelta(seconds=10),
        ),
    )
    plan = SimpleNamespace(
        runtime={
            "level_poll_interval_sec": 5,
            "irrigation_execution": {"correction_during_irrigation": True},
            "irrigation_safety": {"stop_on_solution_min": False},
        }
    )
    stage_def = SimpleNamespace(on_corr_success="irrigation_check", on_corr_fail="irrigation_check")
    out = await handler.run(task=task, plan=plan, stage_def=stage_def, now=now)
    assert out.kind == "poll"


@pytest.mark.asyncio
async def test_irrigation_check_deadline_reached_does_not_probe_before_stop(monkeypatch) -> None:
    handler = IrrigationCheckHandler(runtime_monitor=object(), command_gateway=object(), task_repository=_TaskRepoStub())

    async def _probe(**_kwargs):
        raise AssertionError("probe should not run after irrigation deadline is reached")

    async def _targets(**_kwargs):
        return True

    monkeypatch.setattr(handler, "_probe_irr_state", _probe)
    monkeypatch.setattr(handler, "_targets_reached", _targets)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = SimpleNamespace(
        id=1,
        zone_id=7,
        topology="two_tank",
        claimed_by="worker",
        irrigation_replay_count=0,
        workflow=SimpleNamespace(
            control_mode="auto",
            pending_manual_step=None,
            stage_deadline_at=now,
            stage_retry_count=0,
            stage_entered_at=now - timedelta(seconds=10),
        ),
    )
    plan = SimpleNamespace(
        runtime={
            "level_poll_interval_sec": 5,
            "irrigation_execution": {"correction_during_irrigation": True},
            "irrigation_safety": {"stop_on_solution_min": False},
        }
    )
    stage_def = SimpleNamespace(on_corr_success="irrigation_check", on_corr_fail="irrigation_check")

    out = await handler.run(task=task, plan=plan, stage_def=stage_def, now=now)

    assert out.kind == "transition"
    assert out.next_stage == "irrigation_stop_to_ready"
