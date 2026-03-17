from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from ae3lite.application.dto import ZoneActuatorRef
from ae3lite.application.use_cases.execute_task import ExecuteTaskUseCase, TASK_EXECUTION_TIMEOUT_CANCEL_MSG
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.errors import PlannerConfigurationError, SnapshotBuildError


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

    async def get_by_id(self, *, task_id):
        return self._running_task


class _SnapshotReadModelOk:
    async def load(self, *, zone_id):
        return _SnapshotWithCorrectionConfig()


class _SnapshotReadModelFails:
    async def load(self, *, zone_id):
        raise SnapshotBuildError("snapshot_missing")


class _SnapshotWithCorrectionConfig:
    zone_id = 99
    correction_config = {"meta": {"version": 7}}


class _SnapshotWithIrrActuators:
    zone_id = 99
    correction_config = {"meta": {"version": 7}}
    actuators = (
        ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_clean_fill", node_channel_id=11, role="valve_clean_fill"),
        ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_clean_supply", node_channel_id=12, role="valve_clean_supply"),
        ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_solution_fill", node_channel_id=13, role="valve_solution_fill"),
        ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_solution_supply", node_channel_id=14, role="valve_solution_supply"),
        ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_irrigation", node_channel_id=15, role="valve_irrigation"),
        ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="pump_main", node_channel_id=16, role="pump_main"),
        ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="pump_base", node_channel_id=17, role="ph_base_pump"),
    )


class _SnapshotReadModelWithIrrActuators:
    async def load(self, *, zone_id):
        return _SnapshotWithIrrActuators()


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


class _PlannerMissingZoneCorrectionConfigCritical:
    def build(self, *, task, snapshot):
        raise PlannerConfigurationError(
            "Zone 99 has no correction_config; fail-closed for critical dosing parameters",
            code="zone_correction_config_missing_critical",
        )


class _PlannerMissingDosingCalibrationCritical:
    def build(self, *, task, snapshot):
        raise PlannerConfigurationError(
            "EC dosing pump calibration is required (channel=pump_a, node=nd-ec-1)",
            code="zone_dosing_calibration_missing_critical",
        )


class _PlannerMissingPidConfigCritical:
    def build(self, *, task, snapshot):
        raise PlannerConfigurationError(
            "Zone 99 missing required zone_pid_configs for pid_type=ec, ph; fail-closed for critical correction parameters",
            code="zone_pid_config_missing_critical",
        )


class _GatewayOk:
    async def run_batch(self, *, task, commands, now, **kwargs):
        return {"success": True, "task": task}


class _GatewayFails:
    async def run_batch(self, *, task, commands, now, **kwargs):
        return {"success": False, "error_code": "hw_error", "error_message": "device offline"}


class _GatewayRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def run_batch(self, *, task, commands, now, **kwargs):
        self.calls.append({"commands": tuple(commands), "kwargs": kwargs})
        return {"success": True, "task": task}


class _CorrectionConfigRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def mark_applied(self, *, zone_id, version, now):
        self.calls.append({"zone_id": zone_id, "version": version, "now": now})


class _WorkflowRouterOk:
    async def run(self, *, task, plan, now):
        return replace(task, status="completed")


class _WorkflowRouterFails:
    async def run(self, *, task, plan, now):
        return replace(task, status="failed")


class _WorkflowRouterPending:
    async def run(self, *, task, plan, now):
        return replace(
            task,
            status="pending",
            workflow=replace(task.workflow, current_stage="prepare_recirculation_check"),
        )


class _WorkflowRouterRaises:
    async def run(self, *, task, plan, now):
        raise RuntimeError("boom")


class _WorkflowRouterRaisesDecisionWindowNotReady:
    async def run(self, *, task, plan, now):
        from ae3lite.domain.errors import TaskExecutionError

        raise TaskExecutionError(
            "corr_decision_window_not_ready",
            "Correction decision window not ready: PH=insufficient_samples,samples=2; EC=insufficient_samples,samples=2",
        )


class _WorkflowRouterCancelledByTimeout:
    async def run(self, *, task, plan, now):
        raise asyncio.CancelledError(TASK_EXECUTION_TIMEOUT_CANCEL_MSG)


class _AlertRepositoryRecorder:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self._should_fail = should_fail

    async def create_or_update_active(self, **kwargs):
        self.calls.append(kwargs)
        if self._should_fail:
            raise RuntimeError("alert write failed")
        return 101


class _WorkflowRepoRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def upsert_phase(self, *, zone_id, workflow_phase, payload, scheduler_task_id, now):
        self.calls.append(
            {
                "zone_id": zone_id,
                "workflow_phase": workflow_phase,
                "payload": payload,
                "scheduler_task_id": scheduler_task_id,
                "now": now,
            }
        )


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
async def test_execute_task_expected_domain_errors_do_not_log_traceback(caplog: pytest.LogCaptureFixture) -> None:
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

    with caplog.at_level(logging.ERROR):
        await use_case.run(task=task, now=NOW)

    domain_logs = [
        record
        for record in caplog.records
        if "AE3 task execution domain error:" in record.getMessage()
    ]
    assert len(domain_logs) == 1
    assert domain_logs[0].exc_info is None
    assert "error_type=SnapshotBuildError" in domain_logs[0].getMessage()


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
async def test_execute_task_fail_closed_creates_task_failed_alert() -> None:
    task = _make_task(stage="startup", topology="generic_cycle_start")
    finalize = _FinalizeTaskUseCase()
    alerts = _AlertRepositoryRecorder()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerNoSteps(),
        command_gateway=object(),
        workflow_router=object(),
        alert_repository=alerts,
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == "unsupported_command_plan_steps"
    assert len(alerts.calls) == 1
    assert alerts.calls[0]["zone_id"] == 99
    assert alerts.calls[0]["code"] == "biz_ae3_task_failed"
    assert alerts.calls[0]["category"] == "operations"
    assert alerts.calls[0]["severity"] == "error"
    details = alerts.calls[0]["details"]
    assert details["task_id"] == 99
    assert details["task_status"] == "failed"
    assert details["error_code"] == "unsupported_command_plan_steps"
    assert details["stage"] == "startup"
    assert details["topology"] == "generic_cycle_start"


@pytest.mark.asyncio
async def test_execute_task_fail_closed_alert_write_error_does_not_block_fail_closed() -> None:
    task = _make_task(stage="startup", topology="generic_cycle_start")
    finalize = _FinalizeTaskUseCase()
    alerts = _AlertRepositoryRecorder(should_fail=True)
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerNoSteps(),
        command_gateway=object(),
        workflow_router=object(),
        alert_repository=alerts,
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert len(alerts.calls) == 1
    assert finalize.calls[0]["error_code"] == "unsupported_command_plan_steps"


@pytest.mark.asyncio
async def test_execute_task_critical_missing_zone_config_emits_critical_alert_and_shutdown() -> None:
    task = _make_task(stage="startup", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    gateway = _GatewayRecorder()
    alerts = _AlertRepositoryRecorder()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelWithIrrActuators(),
        planner=_PlannerMissingZoneCorrectionConfigCritical(),
        command_gateway=gateway,
        workflow_router=object(),
        alert_repository=alerts,
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == "zone_correction_config_missing_critical"
    assert len(alerts.calls) == 1
    assert alerts.calls[0]["code"] == "biz_zone_correction_config_missing"
    assert alerts.calls[0]["severity"] == "critical"
    assert alerts.calls[0]["details"]["error_code"] == "zone_correction_config_missing_critical"
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["kwargs"] == {"track_task_state": False}
    assert all(
        command.payload.get("params", {}).get("state") is False
        for command in gateway.calls[0]["commands"]
    )


@pytest.mark.asyncio
async def test_execute_task_missing_dosing_calibration_emits_blocking_alert_and_shutdown() -> None:
    task = _make_task(stage="startup", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    gateway = _GatewayRecorder()
    alerts = _AlertRepositoryRecorder()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelWithIrrActuators(),
        planner=_PlannerMissingDosingCalibrationCritical(),
        command_gateway=gateway,
        workflow_router=object(),
        alert_repository=alerts,
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == "zone_dosing_calibration_missing_critical"
    assert len(alerts.calls) == 1
    assert alerts.calls[0]["code"] == "biz_zone_dosing_calibration_missing"
    assert alerts.calls[0]["severity"] == "critical"
    assert alerts.calls[0]["details"]["task_status"] == "failed"
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["kwargs"] == {"track_task_state": False}
    assert all(
        command.payload.get("params", {}).get("state") is False
        for command in gateway.calls[0]["commands"]
    )


@pytest.mark.asyncio
async def test_execute_task_missing_pid_config_emits_blocking_alert_and_shutdown() -> None:
    task = _make_task(stage="startup", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    gateway = _GatewayRecorder()
    alerts = _AlertRepositoryRecorder()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelWithIrrActuators(),
        planner=_PlannerMissingPidConfigCritical(),
        command_gateway=gateway,
        workflow_router=object(),
        alert_repository=alerts,
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == "zone_pid_config_missing_critical"
    assert len(alerts.calls) == 1
    assert alerts.calls[0]["code"] == "biz_zone_pid_config_missing"
    assert alerts.calls[0]["severity"] == "critical"
    assert alerts.calls[0]["details"]["error_code"] == "zone_pid_config_missing_critical"
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["kwargs"] == {"track_task_state": False}
    assert all(
        command.payload.get("params", {}).get("state") is False
        for command in gateway.calls[0]["commands"]
    )


@pytest.mark.asyncio
async def test_execute_task_skips_fail_safe_shutdown_when_task_was_cleaned_up() -> None:
    task = _make_task(stage="startup", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    gateway = _GatewayRecorder()

    class _TaskRepoDeletedDuringUnwind(_TaskRepoRunning):
        async def get_by_id(self, *, task_id):
            assert task_id == task.id
            return None

    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoDeletedDuringUnwind(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelWithIrrActuators(),
        planner=_PlannerMissingDosingCalibrationCritical(),
        command_gateway=gateway,
        workflow_router=object(),
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == "zone_dosing_calibration_missing_critical"
    assert gateway.calls == []


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
async def test_execute_task_marks_correction_config_applied_for_failed_two_tank_task() -> None:
    """Failed two-tank task still marks correction config as applied (config was loaded and used)."""
    task = _make_task(stage="startup", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    correction_config_repository = _CorrectionConfigRepository()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerTwoTankOk(),
        command_gateway=_GatewayOk(),
        workflow_router=_WorkflowRouterFails(),
        zone_correction_config_repository=correction_config_repository,
        finalize_task_use_case=finalize,
    )

    result = await use_case.run(task=task, now=NOW)

    assert result.status == "failed"
    assert correction_config_repository.calls == [{"zone_id": 99, "version": 7, "now": NOW}]


@pytest.mark.asyncio
async def test_execute_task_decision_window_not_ready_emits_task_failed_alert() -> None:
    task = _make_task(stage="solution_fill_check", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    alerts = _AlertRepositoryRecorder()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerTwoTankOk(),
        command_gateway=_GatewayOk(),
        workflow_router=_WorkflowRouterRaisesDecisionWindowNotReady(),
        alert_repository=alerts,
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == "corr_decision_window_not_ready"
    assert len(alerts.calls) == 1
    assert alerts.calls[0]["code"] == "biz_ae3_task_failed"
    assert alerts.calls[0]["details"]["error_code"] == "corr_decision_window_not_ready"
    assert alerts.calls[0]["details"]["stage"] == "solution_fill_check"


@pytest.mark.asyncio
async def test_execute_task_marks_correction_config_applied_for_pending_two_tank_task() -> None:
    """Hot-reload ack must persist while the two-tank task is still active."""
    task = _make_task(stage="solution_fill_check", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    correction_config_repository = _CorrectionConfigRepository()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerTwoTankOk(),
        command_gateway=_GatewayOk(),
        workflow_router=_WorkflowRouterPending(),
        zone_correction_config_repository=correction_config_repository,
        finalize_task_use_case=finalize,
    )

    result = await use_case.run(task=task, now=NOW)

    assert result.status == "pending"
    assert result.current_stage == "prepare_recirculation_check"
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


@pytest.mark.asyncio
async def test_execute_task_two_tank_failure_triggers_fail_safe_shutdown() -> None:
    task = _make_task(stage="solution_fill_check", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    gateway = _GatewayRecorder()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelWithIrrActuators(),
        planner=_PlannerTwoTankOk(),
        command_gateway=gateway,
        workflow_router=_WorkflowRouterRaises(),
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == "ae3_task_execution_unhandled_exception"
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["kwargs"] == {"track_task_state": False}
    sent_channels = [command.channel for command in gateway.calls[0]["commands"]]
    assert sent_channels == [
        "valve_clean_fill",
        "valve_clean_supply",
        "valve_solution_fill",
        "valve_solution_supply",
        "valve_irrigation",
        "pump_main",
    ]
    assert all(
        command.payload.get("params", {}).get("state") is False
        for command in gateway.calls[0]["commands"]
    )


@pytest.mark.asyncio
async def test_execute_task_timeout_cancellation_fails_closed_and_runs_fail_safe_shutdown() -> None:
    task = _make_task(stage="solution_fill_check", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    gateway = _GatewayRecorder()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelWithIrrActuators(),
        planner=_PlannerTwoTankOk(),
        command_gateway=gateway,
        workflow_router=_WorkflowRouterCancelledByTimeout(),
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == TASK_EXECUTION_TIMEOUT_CANCEL_MSG
    assert finalize.calls[0]["error_message"] == "Task execution exceeded runtime timeout"
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["kwargs"] == {"track_task_state": False}
    assert [command.channel for command in gateway.calls[0]["commands"]] == [
        "valve_clean_fill",
        "valve_clean_supply",
        "valve_solution_fill",
        "valve_solution_supply",
        "valve_irrigation",
        "pump_main",
    ]


@pytest.mark.asyncio
async def test_execute_task_fail_closed_syncs_zone_workflow_state_to_idle() -> None:
    task = _make_task(stage="solution_fill_start", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    workflow_repo = _WorkflowRepoRecorder()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelFails(),
        planner=_PlannerFails(),
        command_gateway=object(),
        workflow_router=object(),
        workflow_repository=workflow_repo,
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == "ae3_task_execution_failed"
    assert finalize.calls[0]["error_message"] == "snapshot_missing"
    assert workflow_repo.calls == [
        {
            "zone_id": 99,
            "workflow_phase": "idle",
            "payload": {"ae3_cycle_start_stage": "solution_fill_start"},
            "scheduler_task_id": "99",
            "now": NOW,
        }
    ]
