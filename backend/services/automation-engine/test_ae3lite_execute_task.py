from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from ae3lite.application.use_cases.execute_task import ExecuteTaskUseCase
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.errors import SnapshotBuildError


NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)


# ── Task factory (local — no cross-test-file import) ─────────────────────────

def _make_task(*, stage: str = "startup", topology: str = "two_tank") -> AutomationTask:
    return AutomationTask.from_row({
        "id": 99, "zone_id": 99, "task_type": "cycle_start", "status": "running",
        "idempotency_key": "k99", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w1", "claimed_at": NOW, "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": topology, "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": stage, "workflow_phase": "idle",
        "stage_deadline_at": None, "stage_retry_count": 0,
        "stage_entered_at": NOW, "clean_fill_cycle": 0,
        "corr_step": None,
    })


# ── Shared stubs ──────────────────────────────────────────────────────────────

class _FinalizeTaskUseCase:
    def __init__(self):
        self.calls: list[dict] = []

    async def fail_closed(self, *, task, owner, error_code, error_message, now):
        self.calls.append({
            "task_id": task.id, "owner": owner,
            "error_code": error_code, "error_message": error_message, "now": now,
        })
        return task

    async def complete(self, *, task, owner, now):
        return replace(task, status="completed")


class _TaskRepoRunning:
    """mark_running succeeds, mark_completed also."""
    def __init__(self, *, running_task: AutomationTask | None = None):
        self._running_task = running_task

    async def mark_running(self, *, task_id, owner, now):
        return self._running_task

    async def mark_completed(self, *, task_id, owner, now):
        return replace(self._running_task, status="completed")


class _SnapshotReadModelOk:
    async def load(self, *, zone_id):
        return _SnapshotWithCorrectionConfig()


class _SnapshotReadModelFails:
    async def load(self, *, zone_id):
        raise SnapshotBuildError("snapshot_missing")


class _SnapshotWithCorrectionConfig:
    zone_id = 99
    correction_config = {"meta": {"version": 7}}


class _PlanWithSteps:
    def __init__(self, *, steps=()):
        self.steps = steps
        self.topology = "generic"

    def build(self, **kwargs):
        return self


class _PlannerOk:
    def build(self, *, task, snapshot):
        return _PlanWithSteps(steps=("step1",))


class _PlannerTwoTankOk:
    def build(self, *, task, snapshot):
        plan = _PlanWithSteps(steps=())
        plan.topology = "two_tank_drip_substrate_trays"
        return plan


class _PlannerNoSteps:
    def build(self, *, task, snapshot):
        return _PlanWithSteps(steps=())


class _PlannerFails:
    def build(self, *, task, snapshot):
        raise AssertionError("planner should not be called when snapshot load fails")


class _GatewayOk:
    async def run_batch(self, *, task, commands, now):
        return {"success": True, "task": task}


class _GatewayFails:
    async def run_batch(self, *, task, commands, now):
        return {"success": False, "error_code": "hw_error", "error_message": "device offline"}


class _CorrectionConfigRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def mark_applied(self, *, zone_id, version, now):
        self.calls.append({"zone_id": zone_id, "version": version, "now": now})


class _WorkflowRouterOk:
    async def run(self, *, task, plan, now):
        return replace(task, status="completed")


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_task_uses_passed_now_for_fail_closed() -> None:
    """SnapshotBuildError → fail_closed called with the exact now passed to run()."""
    finalize = _FinalizeTaskUseCase()
    task = _make_task(stage="startup")
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelFails(),
        planner=_PlannerFails(),
        command_gateway=object(),
        workflow_router=object(),
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["now"] == NOW


@pytest.mark.asyncio
async def test_execute_task_fallback_non_two_tank_happy_path() -> None:
    """Non-two-tank topology with valid plan → commands run → task completed."""
    task = _make_task(stage="startup", topology="generic_cycle_start")
    finalize = _FinalizeTaskUseCase()
    correction_config_repository = _CorrectionConfigRepository()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerOk(),
        command_gateway=_GatewayOk(),
        workflow_router=object(),
        zone_correction_config_repository=correction_config_repository,
        finalize_task_use_case=finalize,
    )

    result = await use_case.run(task=task, now=NOW)

    assert result.status == "completed"
    assert finalize.calls == []  # complete(), not fail_closed()
    assert correction_config_repository.calls == []


@pytest.mark.asyncio
async def test_execute_task_fallback_non_two_tank_empty_steps_fails() -> None:
    """Non-two-tank topology with empty plan steps → fail_closed with unsupported_command_plan_steps."""
    task = _make_task(stage="startup", topology="generic_cycle_start")
    finalize = _FinalizeTaskUseCase()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerNoSteps(),
        command_gateway=object(),
        workflow_router=object(),
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == "unsupported_command_plan_steps"


@pytest.mark.asyncio
async def test_execute_task_does_not_mark_correction_config_applied_when_snapshot_load_fails() -> None:
    finalize = _FinalizeTaskUseCase()
    correction_config_repository = _CorrectionConfigRepository()
    task = _make_task(stage="startup")
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelFails(),
        planner=_PlannerFails(),
        command_gateway=object(),
        workflow_router=object(),
        zone_correction_config_repository=correction_config_repository,
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert correction_config_repository.calls == []


@pytest.mark.asyncio
async def test_execute_task_marks_correction_config_applied_for_native_two_tank_plan() -> None:
    task = _make_task(stage="startup", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    correction_config_repository = _CorrectionConfigRepository()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerTwoTankOk(),
        command_gateway=_GatewayOk(),
        workflow_router=_WorkflowRouterOk(),
        zone_correction_config_repository=correction_config_repository,
        finalize_task_use_case=finalize,
    )

    result = await use_case.run(task=task, now=NOW)

    assert result.status == "completed"
    assert correction_config_repository.calls == [{"zone_id": 99, "version": 7, "now": NOW}]


@pytest.mark.asyncio
async def test_execute_task_fallback_non_two_tank_gateway_failure_fails() -> None:
    """Non-two-tank topology with command failure → fail_closed with gateway error code."""
    task = _make_task(stage="startup", topology="generic_cycle_start")
    finalize = _FinalizeTaskUseCase()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerOk(),
        command_gateway=_GatewayFails(),
        workflow_router=object(),
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == "hw_error"
