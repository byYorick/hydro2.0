from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from ae3lite.application.handlers.irrigation_recovery import IrrigationRecoveryCheckHandler


@pytest.mark.asyncio
async def test_recovery_transitions_to_stop_when_targets_reached(monkeypatch) -> None:
    handler = IrrigationRecoveryCheckHandler(runtime_monitor=object(), command_gateway=object())

    async def _probe(**_kwargs):
        return None

    async def _targets(**_kwargs):
        return True

    monkeypatch.setattr(handler, "_probe_irr_state", _probe)
    monkeypatch.setattr(handler, "_targets_reached", _targets)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = SimpleNamespace(
        id=1,
        zone_id=7,
        current_stage="irrigation_recovery_check",
        topology="two_tank",
        workflow=SimpleNamespace(control_mode="auto", pending_manual_step=None, stage_deadline_at=now + timedelta(seconds=10)),
    )
    plan = SimpleNamespace(runtime={"level_poll_interval_sec": 5})
    out = await handler.run(task=task, plan=plan, stage_def=SimpleNamespace(on_corr_success=None, on_corr_fail=None), now=now)
    assert out.kind == "transition"
    assert out.next_stage == "irrigation_recovery_stop_to_ready"


@pytest.mark.asyncio
async def test_recovery_enters_correction_when_targets_not_met(monkeypatch) -> None:
    handler = IrrigationRecoveryCheckHandler(runtime_monitor=object(), command_gateway=object())

    async def _probe(**_kwargs):
        return None

    async def _targets(**_kwargs):
        return False

    monkeypatch.setattr(handler, "_probe_irr_state", _probe)
    monkeypatch.setattr(handler, "_targets_reached", _targets)
    monkeypatch.setattr(handler, "_correction_config_for_task", lambda **_kwargs: {"max_ec_correction_attempts": 2, "max_ph_correction_attempts": 3, "stabilization_sec": 1})

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = SimpleNamespace(
        id=1,
        zone_id=7,
        current_stage="irrigation_recovery_check",
        topology="two_tank",
        workflow=SimpleNamespace(control_mode="auto", pending_manual_step=None, stage_deadline_at=now + timedelta(seconds=10)),
    )
    plan = SimpleNamespace(runtime={"level_poll_interval_sec": 5})
    out = await handler.run(task=task, plan=plan, stage_def=SimpleNamespace(on_corr_success=None, on_corr_fail=None), now=now)
    assert out.kind == "enter_correction"
    assert out.correction is not None
    assert out.correction.corr_step == "corr_check"
    assert out.correction.return_stage_success == "irrigation_recovery_stop_to_ready"
    assert out.correction.return_stage_fail == "irrigation_recovery_stop_failed"


@pytest.mark.asyncio
async def test_recovery_fails_on_timeout(monkeypatch) -> None:
    handler = IrrigationRecoveryCheckHandler(runtime_monitor=object(), command_gateway=object())

    async def _probe(**_kwargs):
        return None

    monkeypatch.setattr(handler, "_probe_irr_state", _probe)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = SimpleNamespace(
        id=1,
        zone_id=7,
        current_stage="irrigation_recovery_check",
        topology="two_tank",
        workflow=SimpleNamespace(control_mode="auto", pending_manual_step=None, stage_deadline_at=now - timedelta(seconds=1)),
    )
    plan = SimpleNamespace(runtime={"level_poll_interval_sec": 5})
    out = await handler.run(task=task, plan=plan, stage_def=SimpleNamespace(on_corr_success=None, on_corr_fail=None), now=now)
    assert out.kind == "fail"
    assert out.error_code == "irrigation_recovery_timeout"
