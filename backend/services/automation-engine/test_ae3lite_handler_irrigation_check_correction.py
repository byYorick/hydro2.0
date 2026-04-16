from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from unittest.mock import AsyncMock

from _test_support_runtime_plan import make_runtime_plan
from ae3lite.application.handlers.irrigation_check import IrrigationCheckHandler
from ae3lite.domain.errors import TaskExecutionError


class _TaskRepoStub:
    async def update_irrigation_runtime(self, **_kwargs):
        return True


class _ProbeGatewayStub:
    async def run_batch(self, **_kwargs):
        return {
            "success": True,
            "error_code": None,
            "error_message": None,
            "command_statuses": [{"legacy_cmd_id": "probe-1"}],
        }


class _RuntimeMonitorStub:
    def __init__(
        self,
        *,
        irr_state: dict[str, Any],
        level_states: list[dict[str, Any]] | None = None,
        recent_storage_event: dict[str, Any] | None = None,
    ) -> None:
        self._irr_state = irr_state
        self._level_states = list(level_states or [])
        self._recent_storage_event = recent_storage_event
        self.level_call_count = 0

    async def read_latest_irr_state(self, **_kwargs):
        return self._irr_state

    async def read_latest_zone_event(self, **_kwargs):
        return dict(self._recent_storage_event) if self._recent_storage_event is not None else None

    async def read_level_switch(self, **_kwargs):
        self.level_call_count += 1
        idx = min(self.level_call_count - 1, len(self._level_states) - 1)
        if self._level_states:
            return dict(self._level_states[idx])
        return {
            "has_level": True,
            "is_stale": False,
            "is_triggered": True,
            "sample_ts": datetime.now(timezone.utc),
            "sample_age_sec": 0.0,
        }


def _plan(*, named_plans=None, **runtime_overrides):
    return SimpleNamespace(
        runtime=make_runtime_plan(**runtime_overrides),
        named_plans=named_plans or {},
    )


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
    plan = _plan(
        level_poll_interval_sec=5,
        irrigation_execution={"correction_during_irrigation": True},
        irrigation_safety={"stop_on_solution_min": False},
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
    plan = _plan(
        level_poll_interval_sec=5,
        irrigation_execution={"correction_during_irrigation": False},
        irrigation_safety={"stop_on_solution_min": False},
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
    plan = _plan(
        level_poll_interval_sec=5,
        irrigation_execution={"correction_during_irrigation": True},
        irrigation_safety={"stop_on_solution_min": False},
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
    plan = _plan(
        level_poll_interval_sec=5,
        irrigation_execution={"correction_during_irrigation": True},
        irrigation_safety={"stop_on_solution_min": False},
    )
    stage_def = SimpleNamespace(on_corr_success="irrigation_check", on_corr_fail="irrigation_check")

    out = await handler.run(task=task, plan=plan, stage_def=stage_def, now=now)

    assert out.kind == "transition"
    assert out.next_stage == "irrigation_stop_to_ready"


@pytest.mark.asyncio
async def test_irrigation_check_uses_probe_snapshot_for_solution_min() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    monitor = _RuntimeMonitorStub(
        irr_state={
            "has_snapshot": True,
            "is_stale": False,
            "sample_age_sec": 0.0,
            "created_at": now,
            "cmd_id": "probe-1",
            "snapshot": {
                "valve_solution_supply": True,
                "valve_irrigation": True,
                "pump_main": True,
                "level_solution_min": True,
            },
        },
        level_states=[
            {
                "has_level": True,
                "is_stale": True,
                "is_triggered": True,
                "sample_ts": now,
                "sample_age_sec": 11.2,
            }
        ],
    )
    handler = IrrigationCheckHandler(
        runtime_monitor=monitor,
        command_gateway=_ProbeGatewayStub(),
        task_repository=_TaskRepoStub(),
    )
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
    plan = _plan(
        named_plans={"irr_state_probe": ("probe_cmd",)},
        level_poll_interval_sec=5,
        level_switch_on_threshold=0.5,
        telemetry_max_age_sec=10,
        solution_min_sensor_labels=["level_solution_min"],
        irr_state_max_age_sec=60,
        irr_state_wait_timeout_sec=0.0,
        irr_state_wait_poll_interval_sec=0.05,
        irrigation_execution={"correction_during_irrigation": False},
        irrigation_safety={"stop_on_solution_min": True},
    )
    stage_def = SimpleNamespace(on_corr_success="irrigation_check", on_corr_fail="irrigation_check")

    out = await handler.run(task=task, plan=plan, stage_def=stage_def, now=now)

    assert out.kind == "poll"
    assert monitor.level_call_count == 1


@pytest.mark.asyncio
async def test_irrigation_check_stale_level_recovers_on_safe_recheck(monkeypatch) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    monitor = _RuntimeMonitorStub(
        irr_state={
            "has_snapshot": True,
            "is_stale": False,
            "sample_age_sec": 0.0,
            "created_at": now,
            "cmd_id": "probe-1",
            "snapshot": {
                "valve_solution_supply": True,
                "valve_irrigation": True,
                "pump_main": True,
            },
        },
        level_states=[
            {
                "has_level": True,
                "is_stale": True,
                "is_triggered": True,
                "sample_ts": now,
                "sample_age_sec": 10.7,
            },
            {
                "has_level": True,
                "is_stale": False,
                "is_triggered": True,
                "sample_ts": now,
                "sample_age_sec": 0.0,
            },
        ],
    )
    handler = IrrigationCheckHandler(
        runtime_monitor=monitor,
        command_gateway=_ProbeGatewayStub(),
        task_repository=_TaskRepoStub(),
    )
    monkeypatch.setattr("ae3lite.application.handlers.base.asyncio.sleep", AsyncMock())
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
    plan = _plan(
        named_plans={"irr_state_probe": ("probe_cmd",)},
        level_poll_interval_sec=5,
        level_switch_on_threshold=0.5,
        telemetry_max_age_sec=10,
        solution_min_sensor_labels=["level_solution_min"],
        irr_state_max_age_sec=60,
        irr_state_wait_timeout_sec=0.0,
        irr_state_wait_poll_interval_sec=0.05,
        irrigation_execution={"correction_during_irrigation": False},
        irrigation_safety={"stop_on_solution_min": True},
    )
    stage_def = SimpleNamespace(on_corr_success="irrigation_check", on_corr_fail="irrigation_check")

    out = await handler.run(task=task, plan=plan, stage_def=stage_def, now=now)

    assert out.kind == "poll"
    assert monitor.level_call_count == 2


@pytest.mark.asyncio
async def test_irrigation_check_stale_level_still_fails_when_recheck_is_stale(monkeypatch) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    monitor = _RuntimeMonitorStub(
        irr_state={
            "has_snapshot": True,
            "is_stale": False,
            "sample_age_sec": 0.0,
            "created_at": now,
            "cmd_id": "probe-1",
            "snapshot": {
                "valve_solution_supply": True,
                "valve_irrigation": True,
                "pump_main": True,
            },
        },
        level_states=[
            {
                "has_level": True,
                "is_stale": True,
                "is_triggered": True,
                "sample_ts": now,
                "sample_age_sec": 10.7,
            },
            {
                "has_level": True,
                "is_stale": True,
                "is_triggered": True,
                "sample_ts": now,
                "sample_age_sec": 10.9,
            },
        ],
    )
    handler = IrrigationCheckHandler(
        runtime_monitor=monitor,
        command_gateway=_ProbeGatewayStub(),
        task_repository=_TaskRepoStub(),
    )
    monkeypatch.setattr("ae3lite.application.handlers.base.asyncio.sleep", AsyncMock())
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
    plan = _plan(
        named_plans={"irr_state_probe": ("probe_cmd",)},
        level_poll_interval_sec=5,
        level_switch_on_threshold=0.5,
        telemetry_max_age_sec=10,
        solution_min_sensor_labels=["level_solution_min"],
        irr_state_max_age_sec=60,
        irr_state_wait_timeout_sec=0.0,
        irr_state_wait_poll_interval_sec=0.05,
        irrigation_execution={"correction_during_irrigation": False},
        irrigation_safety={"stop_on_solution_min": True},
    )
    stage_def = SimpleNamespace(on_corr_success="irrigation_check", on_corr_fail="irrigation_check")

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=plan, stage_def=stage_def, now=now)

    assert exc_info.value.code == "two_tank_solution_min_level_stale"
    assert monitor.level_call_count == 2


@pytest.mark.asyncio
async def test_irrigation_check_recent_solution_low_event_uses_setup_replay_path(monkeypatch) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    monitor = _RuntimeMonitorStub(
        irr_state={
            "has_snapshot": True,
            "is_stale": False,
            "sample_age_sec": 0.0,
            "created_at": now,
            "cmd_id": "probe-1",
            "snapshot": {
                "valve_solution_supply": True,
                "valve_irrigation": True,
                "pump_main": True,
            },
        },
        recent_storage_event={
            "event_type": "IRRIGATION_SOLUTION_LOW",
            "event_id": 41,
            "created_at": now,
            "payload": {
                "channel": "storage_state",
                "snapshot": {
                    "valve_solution_supply": True,
                    "valve_irrigation": True,
                    "pump_main": True,
                    "solution_level_min": False,
                },
                "state": {
                    "level_solution_min": 0,
                },
            },
        },
    )
    task_repo = _TaskRepoStub()
    task_repo.update_irrigation_runtime = AsyncMock(return_value=True)
    handler = IrrigationCheckHandler(
        runtime_monitor=monitor,
        command_gateway=_ProbeGatewayStub(),
        task_repository=task_repo,
    )
    monkeypatch.setattr("ae3lite.application.handlers.irrigation_check.create_zone_event", AsyncMock(return_value=True))
    monkeypatch.setattr("ae3lite.application.handlers.irrigation_check.send_biz_alert", AsyncMock(return_value=None))
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
    plan = _plan(
        named_plans={"irr_state_probe": ("probe_cmd",)},
        level_poll_interval_sec=5,
        level_switch_on_threshold=0.5,
        telemetry_max_age_sec=10,
        solution_min_sensor_labels=["level_solution_min"],
        irr_state_max_age_sec=60,
        irr_state_wait_timeout_sec=0.0,
        irr_state_wait_poll_interval_sec=0.05,
        irrigation_execution={"correction_during_irrigation": False},
        irrigation_safety={"stop_on_solution_min": True},
        irrigation_recovery={"max_setup_replays": 2},
    )
    stage_def = SimpleNamespace(on_corr_success="irrigation_check", on_corr_fail="irrigation_check")

    out = await handler.run(task=task, plan=plan, stage_def=stage_def, now=now)

    assert out.kind == "transition"
    assert out.next_stage == "irrigation_stop_to_setup"
    task_repo.update_irrigation_runtime.assert_awaited_once()


@pytest.mark.asyncio
async def test_irrigation_check_ignores_stale_solution_low_event_when_probe_and_level_are_healthy(monkeypatch) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    monitor = _RuntimeMonitorStub(
        irr_state={
            "has_snapshot": True,
            "is_stale": False,
            "sample_age_sec": 0.0,
            "created_at": now,
            "cmd_id": "probe-1",
            "snapshot": {
                "valve_solution_supply": True,
                "valve_irrigation": True,
                "pump_main": True,
                "solution_level_min": True,
            },
        },
        recent_storage_event={
            "event_type": "IRRIGATION_SOLUTION_LOW",
            "event_id": 44,
            "created_at": now,
            "payload": {
                "channel": "storage_state",
                "snapshot": {
                    "valve_solution_supply": False,
                    "valve_irrigation": False,
                    "pump_main": False,
                    "solution_level_min": False,
                },
                "state": {
                    "level_solution_min": 0,
                },
            },
        },
        level_states=[
            {
                "has_level": True,
                "is_stale": False,
                "is_triggered": True,
                "sample_ts": now,
                "sample_age_sec": 0.0,
            }
        ],
    )
    task_repo = _TaskRepoStub()
    task_repo.update_irrigation_runtime = AsyncMock(return_value=True)
    handler = IrrigationCheckHandler(
        runtime_monitor=monitor,
        command_gateway=_ProbeGatewayStub(),
        task_repository=task_repo,
    )
    monkeypatch.setattr(handler, "_targets_reached", AsyncMock(return_value=False))
    monkeypatch.setattr(
        handler,
        "_correction_config_for_task",
        lambda **_kwargs: {
            "max_ec_correction_attempts": 2,
            "max_ph_correction_attempts": 2,
            "stabilization_sec": 1,
        },
    )
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
    plan = _plan(
        named_plans={"irr_state_probe": ("probe_cmd",)},
        level_poll_interval_sec=5,
        level_switch_on_threshold=0.5,
        telemetry_max_age_sec=10,
        solution_min_sensor_labels=["level_solution_min"],
        irr_state_max_age_sec=60,
        irr_state_wait_timeout_sec=0.0,
        irr_state_wait_poll_interval_sec=0.05,
        irrigation_execution={"correction_during_irrigation": True},
        irrigation_safety={"stop_on_solution_min": True},
        irrigation_recovery={"max_setup_replays": 0},
    )
    stage_def = SimpleNamespace(on_corr_success="irrigation_check", on_corr_fail="irrigation_check")

    out = await handler.run(task=task, plan=plan, stage_def=stage_def, now=now)

    assert out.kind == "enter_correction"
    assert out.correction is not None
    assert out.correction.corr_step == "corr_check"
    task_repo.update_irrigation_runtime.assert_not_awaited()


@pytest.mark.asyncio
async def test_irrigation_check_ignores_solution_low_event_when_guard_disabled() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    monitor = _RuntimeMonitorStub(
        irr_state={
            "has_snapshot": True,
            "is_stale": False,
            "sample_age_sec": 0.0,
            "created_at": now,
            "cmd_id": "probe-1",
            "snapshot": {
                "valve_solution_supply": True,
                "valve_irrigation": True,
                "pump_main": True,
            },
        },
        recent_storage_event={
            "event_type": "IRRIGATION_SOLUTION_LOW",
            "event_id": 43,
            "created_at": now,
            "payload": {"channel": "storage_state"},
        },
    )
    handler = IrrigationCheckHandler(
        runtime_monitor=monitor,
        command_gateway=_ProbeGatewayStub(),
        task_repository=_TaskRepoStub(),
    )
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
    plan = _plan(
        named_plans={"irr_state_probe": ("probe_cmd",)},
        level_poll_interval_sec=5,
        level_switch_on_threshold=0.5,
        telemetry_max_age_sec=10,
        solution_min_sensor_labels=["level_solution_min"],
        irr_state_max_age_sec=60,
        irr_state_wait_timeout_sec=0.0,
        irr_state_wait_poll_interval_sec=0.05,
        irrigation_execution={"correction_during_irrigation": False},
        irrigation_safety={"stop_on_solution_min": False},
        irrigation_recovery={"max_setup_replays": 2},
    )
    stage_def = SimpleNamespace(on_corr_success="irrigation_check", on_corr_fail="irrigation_check")

    out = await handler.run(task=task, plan=plan, stage_def=stage_def, now=now)

    assert out.kind == "poll"


@pytest.mark.asyncio
async def test_irrigation_check_recent_estop_reconcile_failure_raises_emergency_stop() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    monitor = _RuntimeMonitorStub(
        irr_state={"has_snapshot": False, "is_stale": False, "snapshot": {}},
        recent_storage_event={
            "event_type": "EMERGENCY_STOP_ACTIVATED",
            "event_id": 42,
            "created_at": now,
            "payload": {"channel": "storage_state"},
        },
    )
    handler = IrrigationCheckHandler(
        runtime_monitor=monitor,
        command_gateway=_ProbeGatewayStub(),
        task_repository=_TaskRepoStub(),
    )
    handler._probe_irr_state = AsyncMock(side_effect=TaskExecutionError("irr_state_mismatch", "pump off"))
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
    plan = _plan(
        named_plans={"irr_state_probe": ("probe_cmd",)},
        level_poll_interval_sec=5,
        level_switch_on_threshold=0.5,
        telemetry_max_age_sec=10,
        solution_min_sensor_labels=["level_solution_min"],
        irr_state_max_age_sec=60,
        irr_state_wait_timeout_sec=0.0,
        irr_state_wait_poll_interval_sec=0.05,
        irrigation_execution={"correction_during_irrigation": False},
        irrigation_safety={"stop_on_solution_min": True},
        irrigation_recovery={"max_setup_replays": 2},
    )
    stage_def = SimpleNamespace(on_corr_success="irrigation_check", on_corr_fail="irrigation_check")

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=plan, stage_def=stage_def, now=now)

    assert exc_info.value.code == "emergency_stop_activated"
