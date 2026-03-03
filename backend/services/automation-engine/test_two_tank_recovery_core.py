from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from domain.policies.two_tank_safety_config import TwoTankSafetyConfig
from domain.workflows.two_tank_deps import TwoTankDeps
from domain.workflows.two_tank_recovery_core import execute_two_tank_recovery_branch


class _RecoveryExecutorStub:
    def __init__(self) -> None:
        self._evaluate_calls = 0
        self.events: list[dict] = []
        self.phase_updates: list[dict] = []

    def _resolve_int(self, value: object, default: int, minimum: int) -> int:
        try:
            resolved = int(value)
        except Exception:
            resolved = int(default)
        return max(int(minimum), resolved)

    async def _start_two_tank_irrigation_recovery(self, **_kwargs):
        raise AssertionError("unexpected call")

    async def _evaluate_ph_ec_targets(self, **_kwargs):
        self._evaluate_calls += 1
        if self._evaluate_calls == 1:
            return {"targets_reached": False, "source": "recovery"}
        return {"targets_reached": True, "source": "degraded"}

    async def _dispatch_two_tank_command_plan(self, **_kwargs):
        return {
            "success": True,
            "commands_total": 1,
            "commands_failed": 0,
            "command_statuses": [],
        }

    async def _merge_with_sensor_mode_deactivate(self, *, stop_result, **_kwargs):
        return stop_result

    def _two_tank_safety_guards_enabled(self) -> bool:
        return True

    def _log_two_tank_safety_guard(self, **_kwargs):
        raise AssertionError("unexpected call")

    def _build_two_tank_stop_not_confirmed_result(self, **_kwargs):
        raise AssertionError("unexpected call")

    async def _emit_task_event(self, **kwargs):
        self.events.append(dict(kwargs))

    async def _update_zone_workflow_phase(self, **kwargs):
        self.phase_updates.append(dict(kwargs))

    async def _enqueue_two_tank_check(self, **_kwargs):
        raise AssertionError("unexpected call")


def _build_deps(executor: _RecoveryExecutorStub, zone_id: int = 3) -> TwoTankDeps:
    return TwoTankDeps(
        zone_id=zone_id,
        resolve_int=executor._resolve_int,
        start_two_tank_irrigation_recovery=executor._start_two_tank_irrigation_recovery,
        evaluate_ph_ec_targets=executor._evaluate_ph_ec_targets,
        dispatch_two_tank_command_plan=executor._dispatch_two_tank_command_plan,
        merge_with_sensor_mode_deactivate=executor._merge_with_sensor_mode_deactivate,
        log_two_tank_safety_guard=executor._log_two_tank_safety_guard,
        build_two_tank_stop_not_confirmed_result=executor._build_two_tank_stop_not_confirmed_result,
        emit_task_event=executor._emit_task_event,
        update_zone_workflow_phase=executor._update_zone_workflow_phase,
        enqueue_two_tank_check=executor._enqueue_two_tank_check,
        safety_config=TwoTankSafetyConfig.production(),
    )


@pytest.mark.asyncio
async def test_recovery_degraded_marks_action_required_and_emits_event():
    executor = _RecoveryExecutorStub()
    deps = _build_deps(executor)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    timeout_at = now - timedelta(seconds=1)
    started_at = now - timedelta(minutes=3)

    result = await execute_two_tank_recovery_branch(
        deps,
        payload={
            "irrigation_recovery_attempt": 1,
            "irrigation_recovery_started_at": started_at.isoformat(),
            "irrigation_recovery_timeout_at": timeout_at.isoformat(),
        },
        context={"task_id": "tt-recovery-1"},
        runtime_cfg={
            "target_ph": 5.8,
            "target_ec": 1.6,
            "recovery_tolerance": {"ph_pct": 5.0, "ec_pct": 10.0},
            "degraded_tolerance": {"ph_pct": 10.0, "ec_pct": 20.0},
            "poll_interval_sec": 30,
            "irrigation_recovery_timeout_sec": 300,
            "irrigation_recovery_max_attempts": 2,
            "commands": {"irrigation_recovery_stop": [{"channel": "pump_main", "params": {"state": False}}]},
        },
        workflow="irrigation_recovery_check",
    )

    assert result["success"] is True
    assert result["mode"] == "two_tank_irrigation_recovery_degraded"
    assert result["action_required"] is True
    assert result["degraded"] is True
    assert result["reason_code"] == "irrigation_recovery_degraded"

    assert len(executor.events) == 1
    event = executor.events[0]
    assert event["event_type"] == "IRRIGATION_RECOVERY_DEGRADED"
    assert event["payload"]["action_required_human"] is True

    assert len(executor.phase_updates) == 1
