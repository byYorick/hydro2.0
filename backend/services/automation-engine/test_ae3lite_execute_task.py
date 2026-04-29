from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from ae3lite.application.dto import ZoneActuatorRef
from ae3lite.application.use_cases.execute_task import (
    COMMAND_SEND_RETRY_EXHAUSTED_CODE,
    COMMAND_SEND_RETRY_SEC,
    ExecuteTaskUseCase,
    SNAPSHOT_RETRY_EXHAUSTED_CODE,
    SNAPSHOT_TRANSIENT_RETRY_SEC,
    TASK_EXECUTION_LEASE_LOST_CANCEL_MSG,
    TASK_EXECUTION_TIMEOUT_CANCEL_MSG,
)
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError, SnapshotBuildError, TaskTerminalStateReached


NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)


# ── Task factory (local — no cross-test-file import) ─────────────────────────

def _make_task(
    *,
    stage: str = "startup",
    topology: str = "two_tank",
    task_type: str = "cycle_start",
    irrigation_decision_strategy: str | None = None,
    irrigation_decision_config: dict | None = None,
    irrigation_bundle_revision: str | None = None,
) -> AutomationTask:
    return AutomationTask.from_row({
        "id": 99, "zone_id": 99, "task_type": task_type, "status": "running",
        "idempotency_key": "k99", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w1", "claimed_at": NOW, "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": topology, "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": stage, "workflow_phase": "idle",
        "stage_deadline_at": None, "stage_retry_count": 0,
        "stage_entered_at": NOW, "clean_fill_cycle": 0,
        "irrigation_decision_strategy": irrigation_decision_strategy,
        "irrigation_decision_config": irrigation_decision_config,
        "irrigation_bundle_revision": irrigation_bundle_revision,
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
        self.update_irrigation_runtime_calls: list[dict[str, object]] = []

    async def mark_running(self, *, task_id, owner, now):
        return self._running_task

    async def mark_completed(self, *, task_id, owner, now):
        return replace(self._running_task, status="completed")

    async def get_by_id(self, *, task_id):
        return self._running_task

    async def update_irrigation_runtime(self, *, task_id, owner, now, **kwargs):
        self.update_irrigation_runtime_calls.append({"task_id": task_id, "owner": owner, "now": now, **kwargs})
        self._running_task = replace(
            self._running_task,
            irrigation_mode=kwargs.get("irrigation_mode", self._running_task.irrigation_mode),
            irrigation_requested_duration_sec=kwargs.get(
                "irrigation_requested_duration_sec",
                self._running_task.irrigation_requested_duration_sec,
            ),
            irrigation_decision_strategy=kwargs.get(
                "irrigation_decision_strategy",
                self._running_task.irrigation_decision_strategy,
            ),
            irrigation_decision_config=kwargs.get(
                "irrigation_decision_config",
                self._running_task.irrigation_decision_config,
            ),
            irrigation_bundle_revision=kwargs.get(
                "irrigation_bundle_revision",
                self._running_task.irrigation_bundle_revision,
            ),
            irrigation_wait_ready_deadline_at=kwargs.get(
                "irrigation_wait_ready_deadline_at",
                self._running_task.irrigation_wait_ready_deadline_at,
            ),
        )
        return self._running_task

    async def mark_start_event_emitted(self, *, task_id):
        # Post-merge contract: AE3 помечает задачу как start_event_emitted
        # после успешной эмиссии start-события. Для тестовых сценариев —
        # фиксируем флаг в in-memory копии task (ровно тот же state transition,
        # что и реальный repo).
        self._running_task = replace(self._running_task, start_event_emitted=True)
        return self._running_task


class _TaskRepoRequeue(_TaskRepoRunning):
    def __init__(self, *, running_task: AutomationTask | None = None):
        super().__init__(running_task=running_task)
        self.update_stage_calls: list[dict[str, object]] = []

    async def update_stage(self, *, task_id, owner, workflow, correction, due_at, now):
        self.update_stage_calls.append(
            {
                "task_id": task_id,
                "owner": owner,
                "workflow": workflow,
                "correction": correction,
                "due_at": due_at,
                "now": now,
            }
        )
        return replace(
            self._running_task,
            status="pending",
            claimed_by=None,
            claimed_at=None,
            due_at=due_at,
            updated_at=now,
            workflow=workflow,
            correction=correction,
        )


class _SnapshotReadModelOk:
    async def load(self, *, zone_id):
        return _SnapshotWithCorrectionConfig()


class _SnapshotReadModelFails:
    async def load(self, *, zone_id):
        raise SnapshotBuildError(
            "snapshot_missing",
            code=ErrorCodes.AE3_SNAPSHOT_BUILD_FAILED,
        )


class _SnapshotReadModelNoOnlineActuators:
    async def load(self, *, zone_id):
        raise SnapshotBuildError(
            f"Zone {zone_id} has no online actuator channels",
            code=ErrorCodes.AE3_SNAPSHOT_NO_ONLINE_ACTUATOR_CHANNELS,
        )


class _SnapshotWithCorrectionConfig:
    zone_id = 99
    automation_runtime = "ae3"
    grow_cycle_id = 99
    current_phase_id = 99
    phase_name = "vegetation"
    workflow_phase = "idle"
    command_plans = {"schema_version": "1.0"}
    phase_targets = {"ph": 5.8, "ec": 1.7}
    pid_configs = {"ph": {"kp": 1}, "ec": {"kp": 1}}
    process_calibrations = {"transport_delay_sec": 12}
    actuators = ()
    correction_config = {"meta": {"version": 7}}


class _SnapshotWithIrrActuators:
    zone_id = 99
    automation_runtime = "ae3"
    grow_cycle_id = 19
    current_phase_id = 29
    phase_name = "VEG"
    bundle_revision = "bundle-live-1234567890"
    correction_config = {"meta": {"version": 7}}
    pid_configs = {}
    process_calibrations = {}
    actuators = (
        ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_clean_fill", node_channel_id=11, role="valve_clean_fill"),
        ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_clean_supply", node_channel_id=12, role="valve_clean_supply"),
        ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_solution_fill", node_channel_id=13, role="valve_solution_fill"),
        ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_solution_supply", node_channel_id=14, role="valve_solution_supply"),
        ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_irrigation", node_channel_id=15, role="valve_irrigation"),
        ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="pump_main", node_channel_id=16, role="pump_main"),
        ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="pump_base", node_channel_id=17, role="pump_base"),
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


class _PlannerIrrigationLockSnapshot:
    def build(self, *, task, snapshot):
        plan = _PlanWithSteps(steps=())
        plan.topology = "two_tank"
        # Post-merge: execute_task берёт irrigation_decision только если
        # plan.runtime — typed RuntimePlan (не dict); иначе snapshot-lock
        # пропускается без ошибки (см. `_lock_irrigation_decision_snapshot_if_needed`).
        from _test_support_runtime_plan import make_runtime_plan
        plan.runtime = make_runtime_plan(
            irrigation_decision={
                "strategy": "smart_soil_v1",
                "config": {
                    "lookback_sec": 1800,
                    "min_samples": 3,
                    "stale_after_sec": 600,
                },
            },
        )
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
            "Zone 99 missing required pid authority documents for pid_type=ec, ph; fail-closed for critical correction parameters",
            code="zone_pid_config_missing_critical",
        )


class _PlannerMissingRecipePhaseTargetsCritical:
    def build(self, *, task, snapshot):
        raise PlannerConfigurationError(
            "Zone 99 current recipe phase has no target_ec; automation requires recipe-phase pH/EC targets and forbids defaults or runtime overrides",
            code="zone_recipe_phase_targets_missing_critical",
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


class _CorrectionAuthorityRepository:
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


class _WorkflowRouterCommandSendFailed:
    async def run(self, *, task, plan, now):
        from ae3lite.domain.errors import TaskExecutionError

        raise TaskExecutionError("command_send_failed", "ReadTimeout")



class _WorkflowRouterCancelledByTimeout:
    async def run(self, *, task, plan, now):
        raise asyncio.CancelledError(TASK_EXECUTION_TIMEOUT_CANCEL_MSG)


class _WorkflowRouterCancelledByLeaseLoss:
    async def run(self, *, task, plan, now):
        raise asyncio.CancelledError(TASK_EXECUTION_LEASE_LOST_CANCEL_MSG)


class _WorkflowRouterTerminalTask:
    def __init__(self, *, task):
        self._task = task

    async def run(self, *, task, plan, now):
        raise TaskTerminalStateReached(task=self._task, message="task cancelled externally")


class _AlertRepositoryRecorder:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self._should_fail = should_fail

    async def raise_active(self, **kwargs):
        self.calls.append(kwargs)
        if self._should_fail:
            raise RuntimeError("alert write failed")
        return 101


class _CommandRepositoryWithStartupProbeTimeout:
    async def get_latest_for_task(self, *, task_id):
        assert task_id == 99
        return {
            "id": 501,
            "task_id": task_id,
            "node_uid": "nd-test-irrig-1",
            "channel": "storage_state",
            "payload": {
                "cmd_id": "ae3-t99-z99-s1",
                "cmd": "state",
                "name": "irr_state_probe",
                "params": {},
            },
            "external_id": "77",
            "publish_status": "accepted",
            "terminal_status": "TIMEOUT",
        }

    async def get_legacy_command_by_id(self, *, external_id):
        assert external_id == "77"
        return {
            "id": 77,
            "status": "TIMEOUT",
            "sent_at": NOW,
            "ack_at": None,
            "failed_at": NOW,
            "node_uid": "nd-test-irrig-1",
        }

    async def get_legacy_command_by_cmd_id(self, *, zone_id, cmd_id):
        raise AssertionError("unexpected fallback lookup")

    async def get_node_runtime_context(self, *, node_uid):
        assert node_uid == "nd-test-irrig-1"
        return {
            "uid": node_uid,
            "node_type": "irrig",
            "node_status": "online",
            "last_seen_at": NOW - timedelta(seconds=120),
        }


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
async def test_execute_task_returns_cancelled_task_without_fail_closed_or_alert() -> None:
    finalize = _FinalizeTaskUseCase()
    alert_repo = _AlertRepositoryRecorder()
    task = _make_task(stage="startup")
    cancelled_task = replace(task, status="cancelled", error_code="grow_cycle_aborted", completed_at=NOW)
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerTwoTankOk(),
        command_gateway=object(),
        workflow_router=_WorkflowRouterTerminalTask(task=cancelled_task),
        alert_repository=alert_repo,
        finalize_task_use_case=finalize,
    )

    result = await use_case.run(task=task, now=NOW)

    assert result.status == "cancelled"
    assert finalize.calls == []
    assert alert_repo.calls == []


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
        if "AE3 domain error при выполнении задачи:" in record.getMessage()
    ]
    assert len(domain_logs) == 1
    assert domain_logs[0].exc_info is None
    assert "error_type=SnapshotBuildError" in domain_logs[0].getMessage()


@pytest.mark.asyncio
async def test_execute_task_transient_snapshot_gap_requeues_and_emits_observability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_events: list[tuple[int, str, dict]] = []
    recorded_infra_alerts: list[dict[str, object]] = []

    async def _record_zone_event(zone_id: int, event_type: str, payload: dict) -> None:
        recorded_events.append((zone_id, event_type, payload))

    async def _record_infra_alert(**kwargs):
        recorded_infra_alerts.append(kwargs)
        return True

    monkeypatch.setattr(
        "ae3lite.application.use_cases.execute_task.create_zone_event",
        _record_zone_event,
    )
    monkeypatch.setattr(
        "ae3lite.application.use_cases.execute_task.send_infra_alert",
        _record_infra_alert,
    )

    task = _make_task(stage="solution_fill_check", topology="two_tank")
    task_repo = _TaskRepoRequeue(running_task=task)
    finalize = _FinalizeTaskUseCase()
    alerts = _AlertRepositoryRecorder()
    use_case = ExecuteTaskUseCase(
        task_repository=task_repo,
        zone_snapshot_read_model=_SnapshotReadModelNoOnlineActuators(),
        planner=_PlannerFails(),
        command_gateway=object(),
        workflow_router=object(),
        alert_repository=alerts,
        finalize_task_use_case=finalize,
    )

    result = await use_case.run(task=task, now=NOW)

    assert result.status == "pending"
    assert finalize.calls == []
    assert alerts.calls == []
    assert len(task_repo.update_stage_calls) == 1
    assert task_repo.update_stage_calls[0]["due_at"] == NOW + timedelta(seconds=SNAPSHOT_TRANSIENT_RETRY_SEC)
    assert [event_type for _, event_type, _ in recorded_events] == ["AE_SNAPSHOT_RETRY_SCHEDULED"]
    payload = recorded_events[0][2]
    assert payload["snapshot_error_code"] == ErrorCodes.AE3_SNAPSHOT_NO_ONLINE_ACTUATOR_CHANNELS
    assert payload["snapshot_reason"] == "no_online_actuator_channels"
    assert payload["retry_after_sec"] == SNAPSHOT_TRANSIENT_RETRY_SEC
    assert len(recorded_infra_alerts) == 1
    assert recorded_infra_alerts[0]["code"] == "infra_ae3_snapshot_retry_scheduled"
    assert recorded_infra_alerts[0]["severity"] == "warning"


@pytest.mark.asyncio
async def test_execute_task_transient_snapshot_gap_exhausted_fails_closed_with_specific_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_events: list[tuple[int, str, dict]] = []
    recorded_infra_alerts: list[dict[str, object]] = []

    async def _record_zone_event(zone_id: int, event_type: str, payload: dict) -> None:
        recorded_events.append((zone_id, event_type, payload))

    async def _record_infra_alert(**kwargs):
        recorded_infra_alerts.append(kwargs)
        return True

    monkeypatch.setattr(
        "ae3lite.application.use_cases.execute_task.create_zone_event",
        _record_zone_event,
    )
    monkeypatch.setattr(
        "ae3lite.application.use_cases.execute_task.send_infra_alert",
        _record_infra_alert,
    )

    task = _make_task(stage="solution_fill_check", topology="two_tank")
    task = replace(
        task,
        workflow=replace(
            task.workflow,
            stage_entered_at=NOW - timedelta(seconds=91),
        ),
    )
    finalize = _FinalizeTaskUseCase()
    alerts = _AlertRepositoryRecorder()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelNoOnlineActuators(),
        planner=_PlannerFails(),
        command_gateway=object(),
        workflow_router=object(),
        alert_repository=alerts,
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == SNAPSHOT_RETRY_EXHAUSTED_CODE
    assert len(alerts.calls) == 1
    assert alerts.calls[0]["code"] == "biz_ae3_task_failed"
    assert [event_type for _, event_type, _ in recorded_events] == [
        "AE_SNAPSHOT_RETRY_EXHAUSTED",
        "AE_TASK_FAILED",
    ]
    assert len(recorded_infra_alerts) == 1
    assert recorded_infra_alerts[0]["code"] == "infra_ae3_snapshot_retry_exhausted"
    assert recorded_infra_alerts[0]["severity"] == "error"


@pytest.mark.asyncio
async def test_execute_task_command_send_failed_requeues_and_emits_observability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_events: list[tuple[int, str, dict]] = []
    recorded_infra_alerts: list[dict[str, object]] = []

    async def _record_zone_event(zone_id: int, event_type: str, payload: dict) -> None:
        recorded_events.append((zone_id, event_type, payload))

    async def _record_infra_alert(**kwargs):
        recorded_infra_alerts.append(kwargs)
        return True

    monkeypatch.setattr(
        "ae3lite.application.use_cases.execute_task.create_zone_event",
        _record_zone_event,
    )
    monkeypatch.setattr(
        "ae3lite.application.use_cases.execute_task.send_infra_alert",
        _record_infra_alert,
    )

    task = _make_task(stage="irrigation_check", topology="two_tank")
    task_repo = _TaskRepoRequeue(running_task=task)
    finalize = _FinalizeTaskUseCase()
    alerts = _AlertRepositoryRecorder()
    use_case = ExecuteTaskUseCase(
        task_repository=task_repo,
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerTwoTankOk(),
        command_gateway=_GatewayOk(),
        workflow_router=_WorkflowRouterCommandSendFailed(),
        alert_repository=alerts,
        finalize_task_use_case=finalize,
    )

    result = await use_case.run(task=task, now=NOW)

    assert result.status == "pending"
    assert finalize.calls == []
    assert alerts.calls == []
    assert len(task_repo.update_stage_calls) == 1
    assert task_repo.update_stage_calls[0]["due_at"] == NOW + timedelta(seconds=COMMAND_SEND_RETRY_SEC)
    assert [event_type for _, event_type, _ in recorded_events] == ["AE_COMMAND_SEND_RETRY_SCHEDULED"]
    payload = recorded_events[0][2]
    assert payload["source_error_code"] == "command_send_failed"
    assert payload["retry_reason"] == "history_logger_transport_transient"
    assert payload["retry_after_sec"] == COMMAND_SEND_RETRY_SEC
    assert len(recorded_infra_alerts) == 1
    assert recorded_infra_alerts[0]["code"] == "infra_ae3_command_send_retry_scheduled"
    assert recorded_infra_alerts[0]["severity"] == "warning"


@pytest.mark.asyncio
async def test_execute_task_command_send_failed_retry_exhausted_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_events: list[tuple[int, str, dict]] = []
    recorded_infra_alerts: list[dict[str, object]] = []

    async def _record_zone_event(zone_id: int, event_type: str, payload: dict) -> None:
        recorded_events.append((zone_id, event_type, payload))

    async def _record_infra_alert(**kwargs):
        recorded_infra_alerts.append(kwargs)
        return True

    monkeypatch.setattr(
        "ae3lite.application.use_cases.execute_task.create_zone_event",
        _record_zone_event,
    )
    monkeypatch.setattr(
        "ae3lite.application.use_cases.execute_task.send_infra_alert",
        _record_infra_alert,
    )

    task = _make_task(stage="irrigation_check", topology="two_tank")
    task = replace(
        task,
        workflow=replace(
            task.workflow,
            stage_entered_at=NOW - timedelta(seconds=121),
        ),
    )
    finalize = _FinalizeTaskUseCase()
    alerts = _AlertRepositoryRecorder()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerTwoTankOk(),
        command_gateway=_GatewayOk(),
        workflow_router=_WorkflowRouterCommandSendFailed(),
        alert_repository=alerts,
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == COMMAND_SEND_RETRY_EXHAUSTED_CODE
    assert len(alerts.calls) == 1
    assert alerts.calls[0]["code"] == "biz_ae3_task_failed"
    assert [event_type for _, event_type, _ in recorded_events] == [
        "AE_COMMAND_SEND_RETRY_EXHAUSTED",
        "AE_TASK_FAILED",
    ]
    assert len(recorded_infra_alerts) == 1
    assert recorded_infra_alerts[0]["code"] == "infra_ae3_command_send_retry_exhausted"
    assert recorded_infra_alerts[0]["severity"] == "error"


@pytest.mark.asyncio
async def test_execute_task_fallback_non_two_tank_happy_path() -> None:
    """Non-two-tank topology with valid plan → commands run → task completed."""
    task = _make_task(stage="startup", topology="generic_cycle_start")
    finalize = _FinalizeTaskUseCase()
    correction_authority_repository = _CorrectionAuthorityRepository()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerOk(),
        command_gateway=_GatewayOk(),
        workflow_router=object(),
        correction_authority_repository=correction_authority_repository,
        finalize_task_use_case=finalize,
    )

    result = await use_case.run(task=task, now=NOW)

    assert result.status == "completed"
    assert finalize.calls == []  # complete(), not fail_closed()
    assert correction_authority_repository.calls == []


@pytest.mark.asyncio
async def test_execute_task_first_run_emits_start_readiness_event_and_service_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_events: list[tuple[int, str, dict]] = []
    recorded_service_logs: list[dict[str, object]] = []

    async def _record_zone_event(zone_id: int, event_type: str, payload: dict) -> None:
        recorded_events.append((zone_id, event_type, payload))

    def _record_service_log(*, service, level, message, context=None, async_mode=True) -> None:
        recorded_service_logs.append({
            "service": service,
            "level": level,
            "message": message,
            "context": context or {},
            "async_mode": async_mode,
        })

    monkeypatch.setattr(
        "ae3lite.application.use_cases.execute_task.create_zone_event",
        _record_zone_event,
    )
    monkeypatch.setattr(
        "ae3lite.application.use_cases.execute_task.send_service_log",
        _record_service_log,
    )

    claimed_task = replace(_make_task(stage="startup", topology="generic_cycle_start"), status="claimed")
    running_task = replace(claimed_task, status="running")
    finalize = _FinalizeTaskUseCase()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=running_task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerOk(),
        command_gateway=_GatewayOk(),
        workflow_router=object(),
        finalize_task_use_case=finalize,
    )

    result = await use_case.run(task=claimed_task, now=NOW)

    assert result.status == "completed"
    assert [event_type for _, event_type, _ in recorded_events] == ["AE_TASK_STARTED"]
    assert recorded_events[0][2]["event_schema_version"] == 2


@pytest.mark.asyncio
async def test_execute_task_irrigation_first_run_locks_decision_snapshot_and_emits_event(monkeypatch) -> None:
    recorded_events: list[tuple[int, str, dict]] = []

    async def _record_zone_event(zone_id: int, event_type: str, payload: dict) -> None:
        recorded_events.append((zone_id, event_type, payload))

    monkeypatch.setattr(
        "ae3lite.application.use_cases.execute_task.create_zone_event",
        _record_zone_event,
    )

    claimed_task = replace(
        _make_task(stage="await_ready", topology="two_tank", task_type="irrigation_start"),
        status="claimed",
    )
    task_repo = _TaskRepoRunning(running_task=claimed_task)
    use_case = ExecuteTaskUseCase(
        task_repository=task_repo,
        zone_snapshot_read_model=_SnapshotReadModelWithIrrActuators(),
        planner=_PlannerIrrigationLockSnapshot(),
        command_gateway=_GatewayOk(),
        workflow_router=_WorkflowRouterPending(),
    )

    result = await use_case.run(task=claimed_task, now=NOW)

    assert result.irrigation_decision_strategy == "smart_soil_v1"
    # Post-merge IrrigationDecisionConfig Pydantic включает все 5 обязательных
    # полей; snapshot lock сериализует весь config через model_dump().
    assert result.irrigation_decision_config["lookback_sec"] == 1800
    assert result.irrigation_decision_config["min_samples"] == 3
    assert result.irrigation_decision_config["stale_after_sec"] == 600
    assert result.irrigation_bundle_revision == "bundle-live-1234567890"
    assert any(event_type == "IRRIGATION_DECISION_SNAPSHOT_LOCKED" for _, event_type, _ in recorded_events)
    assert task_repo.update_irrigation_runtime_calls[0]["irrigation_decision_strategy"] == "smart_soil_v1"
    snapshot_payload = next(payload for _, event_type, payload in recorded_events if event_type == "IRRIGATION_DECISION_SNAPSHOT_LOCKED")
    assert snapshot_payload["task_id"] == 99
    assert snapshot_payload["zone_id"] == 99
    assert snapshot_payload["grow_cycle_id"] == 19
    assert snapshot_payload["strategy"] == "smart_soil_v1"
    assert snapshot_payload["bundle_revision"] == "bundle-live-1234567890"
    assert snapshot_payload["event_schema_version"] == 2
    # Post-merge: config.model_dump() сериализует все обязательные поля
    # IrrigationDecisionConfig, включая hysteresis_pct/spread_alert_threshold_pct.
    assert snapshot_payload["config"]["lookback_sec"] == 1800
    assert snapshot_payload["config"]["min_samples"] == 3
    assert snapshot_payload["config"]["stale_after_sec"] == 600


@pytest.mark.asyncio
async def test_execute_task_irrigation_first_run_emits_lock_event_for_prelocked_snapshot(monkeypatch) -> None:
    # The IRRIGATION_DECISION_SNAPSHOT_LOCKED event must fire exactly once per task
    # lifetime: when the task is at the irrigation_start stage (commands about to be
    # sent).  All irrigation_start tasks begin at await_ready; the event must NOT
    # fire there (await_ready polls N times before the zone becomes ready, which
    # would produce N duplicates).  Similarly, it must NOT fire on subsequent
    # re-claims in irrigation_check.
    recorded_events: list[tuple[int, str, dict]] = []

    async def _record_zone_event(zone_id: int, event_type: str, payload: dict) -> None:
        recorded_events.append((zone_id, event_type, payload))

    monkeypatch.setattr(
        "ae3lite.application.use_cases.execute_task.create_zone_event",
        _record_zone_event,
    )

    claimed_task = replace(
        _make_task(
            stage="irrigation_start",
            topology="two_tank",
            task_type="irrigation_start",
            irrigation_decision_strategy="smart_soil_v1",
            irrigation_decision_config={
                "lookback_sec": 1800,
                "min_samples": 3,
                "stale_after_sec": 600,
            },
            irrigation_bundle_revision="bundle-locked-123456",
        ),
        status="claimed",
    )
    task_repo = _TaskRepoRunning(running_task=claimed_task)
    use_case = ExecuteTaskUseCase(
        task_repository=task_repo,
        zone_snapshot_read_model=_SnapshotReadModelWithIrrActuators(),
        planner=_PlannerIrrigationLockSnapshot(),
        command_gateway=_GatewayOk(),
        workflow_router=_WorkflowRouterPending(),
    )

    result = await use_case.run(task=claimed_task, now=NOW)

    assert result.irrigation_decision_strategy == "smart_soil_v1"
    assert task_repo.update_irrigation_runtime_calls == []
    snapshot_payload = next(payload for _, event_type, payload in recorded_events if event_type == "IRRIGATION_DECISION_SNAPSHOT_LOCKED")
    assert snapshot_payload["event_schema_version"] == 2
    assert snapshot_payload["strategy"] == "smart_soil_v1"
    assert snapshot_payload["bundle_revision"] == "bundle-locked-123456"
    assert snapshot_payload["config"] == {
        "lookback_sec": 1800,
        "min_samples": 3,
        "stale_after_sec": 600,
    }


@pytest.mark.asyncio
async def test_execute_task_irrigation_prelocked_snapshot_no_duplicate_events_on_poll_reclaim(monkeypatch) -> None:
    # Regression: IRRIGATION_DECISION_SNAPSHOT_LOCKED was emitted on every re-claim
    # after a poll because update_stage() resets status to 'pending' and re-claim
    # sets status back to 'claimed' (first_run=True).  Verify that stages OTHER
    # than irrigation_start (specifically await_ready and irrigation_check) do NOT
    # emit the event even on the first claimed pick-up.
    for poll_stage in ("await_ready", "irrigation_check"):
        recorded_events: list[tuple[int, str, dict]] = []

        async def _record_zone_event(zone_id: int, event_type: str, payload: dict) -> None:
            recorded_events.append((zone_id, event_type, payload))

        monkeypatch.setattr(
            "ae3lite.application.use_cases.execute_task.create_zone_event",
            _record_zone_event,
        )

        claimed_task = replace(
            _make_task(
                stage=poll_stage,
                topology="two_tank",
                task_type="irrigation_start",
                irrigation_decision_strategy="smart_soil_v1",
                irrigation_decision_config={"lookback_sec": 1800},
                irrigation_bundle_revision="bundle-locked-123456",
            ),
            status="claimed",
        )
        task_repo = _TaskRepoRunning(running_task=claimed_task)
        use_case = ExecuteTaskUseCase(
            task_repository=task_repo,
            zone_snapshot_read_model=_SnapshotReadModelWithIrrActuators(),
            planner=_PlannerIrrigationLockSnapshot(),
            command_gateway=_GatewayOk(),
            workflow_router=_WorkflowRouterPending(),
        )

        await use_case.run(task=claimed_task, now=NOW)

        snapshot_events = [evt for _, evt, _ in recorded_events if evt == "IRRIGATION_DECISION_SNAPSHOT_LOCKED"]
        assert snapshot_events == [], (
            f"IRRIGATION_DECISION_SNAPSHOT_LOCKED emitted unexpectedly at stage={poll_stage!r}: "
            f"got {snapshot_events}"
        )


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
async def test_execute_task_first_run_config_failure_emits_error_service_log_without_started_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_events: list[tuple[int, str, dict]] = []
    recorded_service_logs: list[dict[str, object]] = []

    async def _record_zone_event(zone_id: int, event_type: str, payload: dict) -> None:
        recorded_events.append((zone_id, event_type, payload))

    def _record_service_log(*, service, level, message, context=None, async_mode=True) -> None:
        recorded_service_logs.append({
            "service": service,
            "level": level,
            "message": message,
            "context": context or {},
            "async_mode": async_mode,
        })

    monkeypatch.setattr(
        "ae3lite.application.use_cases.execute_task.create_zone_event",
        _record_zone_event,
    )
    monkeypatch.setattr(
        "ae3lite.application.use_cases.execute_task.send_service_log",
        _record_service_log,
    )

    claimed_task = replace(_make_task(stage="startup", topology="two_tank"), status="claimed")
    running_task = replace(claimed_task, status="running")
    finalize = _FinalizeTaskUseCase()
    alerts = _AlertRepositoryRecorder()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=running_task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerMissingRecipePhaseTargetsCritical(),
        command_gateway=object(),
        workflow_router=object(),
        alert_repository=alerts,
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=claimed_task, now=NOW)

    assert finalize.calls[0]["error_code"] == "zone_recipe_phase_targets_missing_critical"
    assert [event_type for _, event_type, _ in recorded_events] == ["AE_TASK_FAILED"]
    assert len(recorded_service_logs) == 1
    assert recorded_service_logs[0]["level"] == "error"
    assert recorded_service_logs[0]["message"] == "AE3 не подтвердил готовность к старту задачи"
    assert recorded_service_logs[0]["context"]["error_code"] == "zone_recipe_phase_targets_missing_critical"
    assert recorded_service_logs[0]["context"]["snapshot_loaded"] is True


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
async def test_execute_task_command_timeout_enriches_alert_and_emits_startup_probe_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_events: list[tuple[int, str, dict]] = []

    async def _record_zone_event(zone_id: int, event_type: str, payload: dict) -> None:
        recorded_events.append((zone_id, event_type, payload))

    monkeypatch.setattr(
        "ae3lite.application.use_cases.execute_task.create_zone_event",
        _record_zone_event,
    )

    task = _make_task(stage="startup", topology="two_tank_drip_substrate_trays")
    finalize = _FinalizeTaskUseCase()
    alerts = _AlertRepositoryRecorder()

    class _PlannerCommandTimeout:
        def build(self, *, task, snapshot):
            raise PlannerConfigurationError("TIMEOUT", code="command_timeout")

    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerCommandTimeout(),
        command_gateway=object(),
        workflow_router=object(),
        alert_repository=alerts,
        command_repository=_CommandRepositoryWithStartupProbeTimeout(),
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == "command_timeout"
    details = alerts.calls[0]["details"]
    assert details["error_code"] == "command_timeout"
    assert details["timed_out_command"]["cmd_id"] == "ae3-t99-z99-s1"
    assert details["timed_out_command"]["channel"] == "storage_state"
    assert details["timed_out_command"]["node_uid"] == "nd-test-irrig-1"
    assert details["timed_out_command"]["node_status"] == "online"
    assert details["timed_out_command"]["node_last_seen_age_sec"] == 120
    assert details["timed_out_command"]["node_stale_online_candidate"] is True
    assert details["startup_probe_timeout"]["probe_name"] == "irr_state_probe"

    assert [event[1] for event in recorded_events] == [
        "AE_STARTUP_PROBE_TIMEOUT",
        "AE_TASK_FAILED",
    ]
    assert recorded_events[0][2]["cmd_id"] == "ae3-t99-z99-s1"
    assert recorded_events[0][2]["node_stale_online_candidate"] is True
    assert recorded_events[1][2]["timed_out_command"]["node_last_seen_age_sec"] == 120


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
async def test_execute_task_missing_recipe_phase_targets_emits_critical_alert_and_shutdown() -> None:
    task = _make_task(stage="startup", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    gateway = _GatewayRecorder()
    alerts = _AlertRepositoryRecorder()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelWithIrrActuators(),
        planner=_PlannerMissingRecipePhaseTargetsCritical(),
        command_gateway=gateway,
        workflow_router=object(),
        alert_repository=alerts,
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == "zone_recipe_phase_targets_missing_critical"
    assert len(alerts.calls) == 1
    assert alerts.calls[0]["code"] == "biz_zone_recipe_phase_targets_missing"
    assert alerts.calls[0]["severity"] == "critical"
    assert alerts.calls[0]["details"]["error_code"] == "zone_recipe_phase_targets_missing_critical"
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["kwargs"] == {"track_task_state": False}


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
    correction_authority_repository = _CorrectionAuthorityRepository()
    task = _make_task(stage="startup")
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelFails(),
        planner=_PlannerFails(),
        command_gateway=object(),
        workflow_router=object(),
        correction_authority_repository=correction_authority_repository,
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert correction_authority_repository.calls == []


@pytest.mark.asyncio
async def test_execute_task_marks_correction_config_applied_for_native_two_tank_plan() -> None:
    task = _make_task(stage="startup", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    correction_authority_repository = _CorrectionAuthorityRepository()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerTwoTankOk(),
        command_gateway=_GatewayOk(),
        workflow_router=_WorkflowRouterOk(),
        correction_authority_repository=correction_authority_repository,
        finalize_task_use_case=finalize,
    )

    result = await use_case.run(task=task, now=NOW)

    assert result.status == "completed"
    assert correction_authority_repository.calls == [{"zone_id": 99, "version": 7, "now": NOW}]


@pytest.mark.asyncio
async def test_execute_task_marks_correction_config_applied_for_failed_two_tank_task() -> None:
    """Failed two-tank task still marks correction config as applied (config was loaded and used)."""
    task = _make_task(stage="startup", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    correction_authority_repository = _CorrectionAuthorityRepository()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerTwoTankOk(),
        command_gateway=_GatewayOk(),
        workflow_router=_WorkflowRouterFails(),
        correction_authority_repository=correction_authority_repository,
        finalize_task_use_case=finalize,
    )

    result = await use_case.run(task=task, now=NOW)

    assert result.status == "failed"
    assert correction_authority_repository.calls == [{"zone_id": 99, "version": 7, "now": NOW}]


@pytest.mark.asyncio
async def test_execute_task_decision_window_retry_does_not_emit_task_failed_alert() -> None:
    """Decision-window retry requeues task and must not look like fail_closed."""
    task = _make_task(stage="solution_fill_check", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    alerts = _AlertRepositoryRecorder()
    correction_authority_repository = _CorrectionAuthorityRepository()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerTwoTankOk(),
        command_gateway=_GatewayOk(),
        workflow_router=_WorkflowRouterPending(),
        correction_authority_repository=correction_authority_repository,
        alert_repository=alerts,
        finalize_task_use_case=finalize,
    )

    result = await use_case.run(task=task, now=NOW)

    assert result.status == "pending"
    assert result.current_stage == "prepare_recirculation_check"
    assert finalize.calls == []
    assert alerts.calls == []
    assert correction_authority_repository.calls == [{"zone_id": 99, "version": 7, "now": NOW}]


@pytest.mark.asyncio
async def test_execute_task_marks_correction_config_applied_for_pending_two_tank_task() -> None:
    """Hot-reload ack must persist while the two-tank task is still active."""
    task = _make_task(stage="solution_fill_check", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    correction_authority_repository = _CorrectionAuthorityRepository()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelOk(),
        planner=_PlannerTwoTankOk(),
        command_gateway=_GatewayOk(),
        workflow_router=_WorkflowRouterPending(),
        correction_authority_repository=correction_authority_repository,
        finalize_task_use_case=finalize,
    )

    result = await use_case.run(task=task, now=NOW)

    assert result.status == "pending"
    assert result.current_stage == "prepare_recirculation_check"
    assert correction_authority_repository.calls == [{"zone_id": 99, "version": 7, "now": NOW}]


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
    assert finalize.calls[0]["error_message"] == "Выполнение задачи превысило runtime timeout"
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
async def test_execute_task_lease_lost_cancellation_fails_closed_and_runs_fail_safe_shutdown() -> None:
    task = _make_task(stage="solution_fill_check", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    gateway = _GatewayRecorder()
    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoRunning(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelWithIrrActuators(),
        planner=_PlannerTwoTankOk(),
        command_gateway=gateway,
        workflow_router=_WorkflowRouterCancelledByLeaseLoss(),
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == TASK_EXECUTION_LEASE_LOST_CANCEL_MSG
    assert finalize.calls[0]["error_message"] == "Во время выполнения задачи был потерян zone lease"
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["kwargs"] == {"track_task_state": False}


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

    assert finalize.calls[0]["error_code"] == ErrorCodes.AE3_SNAPSHOT_BUILD_FAILED
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


@pytest.mark.asyncio
async def test_execute_task_fail_closed_skips_zone_bound_side_effects_when_zone_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_events: list[tuple[int, str, dict]] = []

    async def _record_zone_event(zone_id: int, event_type: str, payload: dict) -> None:
        recorded_events.append((zone_id, event_type, payload))

    monkeypatch.setattr(
        "ae3lite.application.use_cases.execute_task.create_zone_event",
        _record_zone_event,
    )

    task = _make_task(stage="solution_fill_start", topology="two_tank")
    finalize = _FinalizeTaskUseCase()
    workflow_repo = _WorkflowRepoRecorder()
    alerts = _AlertRepositoryRecorder()

    class _TaskRepoDeletedDuringFailClosed(_TaskRepoRunning):
        async def get_by_id(self, *, task_id):
            assert task_id == task.id
            return None

    use_case = ExecuteTaskUseCase(
        task_repository=_TaskRepoDeletedDuringFailClosed(running_task=task),
        zone_snapshot_read_model=_SnapshotReadModelFails(),
        planner=_PlannerFails(),
        command_gateway=object(),
        workflow_router=object(),
        workflow_repository=workflow_repo,
        alert_repository=alerts,
        finalize_task_use_case=finalize,
    )

    await use_case.run(task=task, now=NOW)

    assert finalize.calls[0]["error_code"] == ErrorCodes.AE3_SNAPSHOT_BUILD_FAILED
    assert workflow_repo.calls == []
    assert alerts.calls == []
    assert recorded_events == []
