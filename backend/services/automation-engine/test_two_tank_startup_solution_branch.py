from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from domain.policies.two_tank_safety_config import TwoTankSafetyConfig
from domain.workflows.two_tank_deps import TwoTankDeps
from domain.workflows.two_tank_startup_solution_branch import handle_two_tank_solution_fill_check


class _SolutionBranchExecutorStub:
    def __init__(self, *, solution_min_level: dict, telemetry_freshness_enforce: bool = True) -> None:
        self.solution_min_level = dict(solution_min_level)
        self.telemetry_freshness_enforce_flag = telemetry_freshness_enforce
        self.update_calls: list[dict] = []

    async def _find_zone_event_since(self, **_kwargs):
        return {"event": "SOLUTION_FILL_COMPLETED"}

    async def _read_level_switch(self, **_kwargs):
        return dict(self.solution_min_level)

    def _telemetry_freshness_enforce(self) -> bool:
        return self.telemetry_freshness_enforce_flag

    async def _dispatch_two_tank_command_plan(self, **_kwargs):
        return {
            "success": True,
            "commands_total": 1,
            "commands_failed": 0,
            "command_statuses": [],
        }

    async def _merge_with_sensor_mode_deactivate(self, *, stop_result, **_kwargs):
        return stop_result

    async def _evaluate_ph_ec_targets(self, **_kwargs):
        return {"targets_reached": True}

    async def _start_two_tank_prepare_recirculation(self, **_kwargs):
        raise AssertionError("unexpected call")

    async def _update_zone_workflow_phase(self, **kwargs):
        self.update_calls.append(dict(kwargs))

    def _two_tank_safety_guards_enabled(self) -> bool:
        return True

    def _log_two_tank_safety_guard(self, **_kwargs):
        raise AssertionError("unexpected call")

    def _build_two_tank_stop_not_confirmed_result(self, **_kwargs):
        raise AssertionError("unexpected call")

    async def _enqueue_two_tank_check(self, **_kwargs):
        raise AssertionError("unexpected call")


def _runtime_cfg() -> dict:
    return {
        "solution_fill_timeout_sec": 300,
        "poll_interval_sec": 30,
        "target_ph": 5.8,
        "target_ec_prepare": 1.2,
        "prepare_tolerance": {"ph_pct": 15.0, "ec_pct": 25.0},
        "level_switch_on_threshold": 0.5,
        "solution_min_labels": ["level_solution_min", "solution_min"],
        "commands": {"solution_fill_stop": [{"channel": "pump_main", "params": {"state": False}}]},
    }


def _build_deps(executor: _SolutionBranchExecutorStub, zone_id: int = 3) -> TwoTankDeps:
    return TwoTankDeps(
        zone_id=zone_id,
        find_zone_event_since=executor._find_zone_event_since,
        read_level_switch=executor._read_level_switch,
        telemetry_freshness_enforce=executor._telemetry_freshness_enforce,
        dispatch_two_tank_command_plan=executor._dispatch_two_tank_command_plan,
        merge_with_sensor_mode_deactivate=executor._merge_with_sensor_mode_deactivate,
        evaluate_ph_ec_targets=executor._evaluate_ph_ec_targets,
        start_two_tank_prepare_recirculation=executor._start_two_tank_prepare_recirculation,
        update_zone_workflow_phase=executor._update_zone_workflow_phase,
        enqueue_two_tank_check=executor._enqueue_two_tank_check,
        log_two_tank_safety_guard=executor._log_two_tank_safety_guard,
        build_two_tank_stop_not_confirmed_result=executor._build_two_tank_stop_not_confirmed_result,
        safety_config=TwoTankSafetyConfig.production(),
    )


@pytest.mark.asyncio
async def test_solution_fill_check_warns_and_continues_when_solution_min_sensor_missing(caplog):
    executor = _SolutionBranchExecutorStub(
        solution_min_level={
            "has_level": False,
            "is_stale": False,
            "is_triggered": False,
            "expected_labels": ["level_solution_min", "solution_min"],
        }
    )
    deps = _build_deps(executor)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with caplog.at_level("WARNING", logger="domain.workflows.two_tank_startup_solution_branch"):
        result = await handle_two_tank_solution_fill_check(
            deps,
            payload={
                "solution_fill_started_at": (now - timedelta(minutes=1)).isoformat(),
                "solution_fill_timeout_at": (now + timedelta(minutes=3)).isoformat(),
            },
            context={"task_id": "tt-solution-1"},
            runtime_cfg=_runtime_cfg(),
            workflow="solution_fill_check",
        )

    assert result["success"] is True
    assert result["mode"] == "two_tank_startup_completed"
    assert "solution min level sensor unavailable (non-blocking)" in caplog.text


@pytest.mark.asyncio
async def test_solution_fill_check_fails_when_solution_min_sensor_stale():
    executor = _SolutionBranchExecutorStub(
        solution_min_level={
            "has_level": True,
            "is_stale": True,
            "is_triggered": True,
            "expected_labels": ["level_solution_min"],
        }
    )
    deps = _build_deps(executor)

    result = await handle_two_tank_solution_fill_check(
        deps,
        payload={},
        context={"task_id": "tt-solution-2"},
        runtime_cfg=_runtime_cfg(),
        workflow="solution_fill_check",
    )

    assert result["success"] is False
    assert result["mode"] == "two_tank_solution_min_level_stale"
    assert result["error_code"] == "two_tank_solution_min_level_stale"


@pytest.mark.asyncio
async def test_solution_fill_check_fails_when_solution_min_sensor_inconsistent():
    executor = _SolutionBranchExecutorStub(
        solution_min_level={
            "has_level": True,
            "is_stale": False,
            "is_triggered": False,
            "expected_labels": ["level_solution_min"],
        }
    )
    deps = _build_deps(executor)

    result = await handle_two_tank_solution_fill_check(
        deps,
        payload={},
        context={"task_id": "tt-solution-3"},
        runtime_cfg=_runtime_cfg(),
        workflow="solution_fill_check",
    )

    assert result["success"] is False
    assert result["mode"] == "two_tank_sensor_state_inconsistent"
    assert result["reason_code"] == "sensor_state_inconsistent"
