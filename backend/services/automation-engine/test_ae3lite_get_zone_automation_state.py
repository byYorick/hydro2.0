from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from ae3lite.application.use_cases.get_zone_automation_state import GetZoneAutomationStateUseCase
from ae3lite.domain.entities.workflow_state import CorrectionState, WorkflowState
from ae3lite.domain.entities.zone_workflow import ZoneWorkflow


NOW = datetime(2026, 3, 14, 9, 30, 0, tzinfo=timezone.utc)


class _TaskRepo:
    def __init__(self, active_task=None, last_task=None, transitions=None):
        self.active_task = active_task
        self.last_task = last_task
        self.transitions = transitions or []

    async def get_active_for_zone(self, *, zone_id: int):
        return self.active_task

    async def get_last_for_zone(self, *, zone_id: int):
        return self.last_task

    async def get_transitions_for_task(self, *, task_id: int):
        return self.transitions


class _WorkflowRepo:
    def __init__(self, workflow: ZoneWorkflow):
        self.workflow = workflow

    async def get(self, *, zone_id: int):
        return self.workflow


class _Guard:
    def __init__(self, result=None):
        self.calls: list[dict] = []
        self.result = result or {"reset": True}

    async def run(self, *, zone_id: int, now):
        self.calls.append({"zone_id": zone_id, "now": now})
        return dict(self.result)


async def test_state_prefers_startup_workflow_snapshot_without_active_task():
    workflow = ZoneWorkflow(
        zone_id=7,
        workflow_phase="idle",
        version=5,
        scheduler_task_id="21",
        started_at=NOW.replace(tzinfo=None),
        updated_at=NOW.replace(tzinfo=None),
        payload={
            "ae3_cycle_start_stage": "startup",
            "guard_reason": "solution_tank_depleted",
            "guard_sensor_label": "level_solution_min",
            "guard_sample_ts": NOW.isoformat(),
        },
    )
    guard = _Guard(
        result={
            "reset": True,
            "reason": "solution_tank_depleted",
            "level": {
                "sensor_label": "level_solution_min",
                "sample_ts": NOW,
            },
        },
    )

    async def fetch_fn(query, *args):
        if "FROM sensors s" in query:
            return []
        return []

    use_case = GetZoneAutomationStateUseCase(
        task_repository=_TaskRepo(),
        workflow_repository=_WorkflowRepo(workflow),
        fetch_fn=fetch_fn,
        startup_reset_guard_use_case=guard,
    )

    result = await use_case.run(zone_id=7)

    assert result["state"] == "IDLE"
    assert result["state_label"] == "Инициализация"
    assert result["workflow_phase"] == "idle"
    assert result["current_stage"] == "startup"
    assert result["current_stage_label"] == "Инициализация"
    assert result["solution_tank_guard"] == {
        "checked": True,
        "reset": True,
        "reason": "solution_tank_depleted",
        "sensor_label": "level_solution_min",
        "sample_ts": NOW.isoformat(),
    }
    assert len(guard.calls) == 1


async def test_telemetry_sql_failure_exposes_telemetry_fetch_ok_false() -> None:
    async def fetch_fn_boom(_query: str, *_args: object):
        raise RuntimeError("telemetry db unavailable")

    use_case = GetZoneAutomationStateUseCase(
        task_repository=_TaskRepo(),
        workflow_repository=None,
        fetch_fn=fetch_fn_boom,
        startup_reset_guard_use_case=None,
    )
    result = await use_case.run(zone_id=42)
    assert result.get("telemetry_fetch_ok") is False
    assert result.get("zone_id") == 42


async def test_workflow_state_stale_check_normalizes_aware_timestamps_to_utc() -> None:
    use_case = GetZoneAutomationStateUseCase(
        task_repository=_TaskRepo(),
        workflow_repository=None,
        fetch_fn=lambda *_args, **_kwargs: [],
    )
    workflow_state = ZoneWorkflow(
        zone_id=7,
        workflow_phase="ready",
        version=5,
        scheduler_task_id="21",
        started_at=NOW.replace(tzinfo=None),
        updated_at=datetime(2026, 3, 14, 12, 0, 0, tzinfo=timezone.utc),
        payload={"ae3_cycle_start_stage": "complete_ready"},
    )
    last_task = SimpleNamespace(
        id=99,
        is_active=False,
        updated_at=datetime(2026, 3, 14, 14, 0, 0, tzinfo=timezone(timedelta(hours=2))),
    )

    assert use_case._workflow_state_is_stale(workflow_state=workflow_state, last_task=last_task) is True


async def test_idle_state_includes_non_blocking_solution_tank_guard_reason() -> None:
    guard = _Guard(
        result={
            "reset": False,
            "reason": "solution_min_unavailable",
            "level": {
                "sensor_label": "level_solution_min",
                "sample_ts": NOW,
            },
        },
    )

    async def fetch_fn(query, *args):
        return []

    use_case = GetZoneAutomationStateUseCase(
        task_repository=_TaskRepo(),
        workflow_repository=None,
        fetch_fn=fetch_fn,
        startup_reset_guard_use_case=guard,
    )

    result = await use_case.run(zone_id=7)

    assert result["state"] == "IDLE"
    assert result["solution_tank_guard"] == {
        "checked": True,
        "reset": False,
        "reason": "solution_min_unavailable",
        "sensor_label": "level_solution_min",
        "sample_ts": NOW.isoformat(),
    }


async def test_state_marks_ec_correction_active_during_solution_fill() -> None:
    task = SimpleNamespace(
        id=22,
        status="pending",
        error_code=None,
        error_message=None,
        workflow=WorkflowState(
            current_stage="solution_fill_check",
            workflow_phase="tank_filling",
            stage_deadline_at=None,
            stage_retry_count=0,
            stage_entered_at=NOW.replace(tzinfo=None),
            clean_fill_cycle=0,
            control_mode="auto",
            pending_manual_step=None,
        ),
        correction=CorrectionState(
            corr_step="corr_wait_ec",
            attempt=2,
            max_attempts=5,
            ec_attempt=2,
            ec_max_attempts=5,
            ph_attempt=1,
            ph_max_attempts=5,
            activated_here=False,
            stabilization_sec=60,
            return_stage_success="solution_fill_stop_to_ready",
            return_stage_fail="solution_fill_stop_to_prepare",
            outcome_success=None,
            needs_ec=True,
            ec_node_uid="nd-test-ec-1",
            ec_channel="pump_a",
            ec_duration_ms=50000,
            needs_ph_up=False,
            needs_ph_down=False,
            ph_node_uid=None,
            ph_channel=None,
            ph_duration_ms=None,
            wait_until=None,
        ),
    )

    async def fetch_fn(query, *args):
        return []

    use_case = GetZoneAutomationStateUseCase(
        task_repository=_TaskRepo(active_task=task),
        workflow_repository=None,
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=1)

    assert result["active_processes"]["pump_in"] is True
    assert result["active_processes"]["ec_correction"] is True
    assert result["active_processes"]["ph_correction"] is False


async def test_state_marks_ph_correction_active_during_solution_fill() -> None:
    task = SimpleNamespace(
        id=22,
        status="pending",
        error_code=None,
        error_message=None,
        workflow=WorkflowState(
            current_stage="solution_fill_check",
            workflow_phase="tank_filling",
            stage_deadline_at=None,
            stage_retry_count=0,
            stage_entered_at=NOW.replace(tzinfo=None),
            clean_fill_cycle=0,
            control_mode="auto",
            pending_manual_step=None,
        ),
        correction=CorrectionState(
            corr_step="corr_wait_ph",
            attempt=2,
            max_attempts=5,
            ec_attempt=2,
            ec_max_attempts=5,
            ph_attempt=2,
            ph_max_attempts=5,
            activated_here=False,
            stabilization_sec=60,
            return_stage_success="solution_fill_stop_to_ready",
            return_stage_fail="solution_fill_stop_to_prepare",
            outcome_success=None,
            needs_ec=False,
            ec_node_uid=None,
            ec_channel=None,
            ec_duration_ms=None,
            needs_ph_up=False,
            needs_ph_down=True,
            ph_node_uid="nd-test-ph-1",
            ph_channel="pump_acid",
            ph_duration_ms=40000,
            wait_until=None,
        ),
    )

    async def fetch_fn(query, *args):
        return []

    use_case = GetZoneAutomationStateUseCase(
        task_repository=_TaskRepo(active_task=task),
        workflow_repository=None,
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=1)

    assert result["active_processes"]["pump_in"] is True
    assert result["active_processes"]["ec_correction"] is False
    assert result["active_processes"]["ph_correction"] is True


async def test_state_returns_irrigation_decision_metadata() -> None:
    task = SimpleNamespace(
        id=31,
        status="completed",
        error_code=None,
        error_message=None,
        irrigation_decision_strategy="smart_soil_v1",
        irrigation_decision_config={"lookback_sec": 1800, "min_samples": 3},
        irrigation_bundle_revision="bundle-abc123456789",
        irrigation_decision_outcome="degraded_run",
        irrigation_decision_reason_code="smart_soil_telemetry_missing_or_stale",
        irrigation_decision_degraded=True,
        workflow=WorkflowState(
            current_stage="completed_run",
            workflow_phase="ready",
            stage_deadline_at=None,
            stage_retry_count=0,
            stage_entered_at=NOW.replace(tzinfo=None),
            clean_fill_cycle=0,
            control_mode="auto",
            pending_manual_step=None,
        ),
        correction=None,
    )

    async def fetch_fn(query, *args):
        return []

    use_case = GetZoneAutomationStateUseCase(
        task_repository=_TaskRepo(active_task=task),
        workflow_repository=None,
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=7)

    assert result["decision"] == {
        "outcome": "degraded_run",
        "reason_code": "smart_soil_telemetry_missing_or_stale",
        "strategy": "smart_soil_v1",
        "config": {"lookback_sec": 1800, "min_samples": 3},
        "bundle_revision": "bundle-abc123456789",
        "degraded": True,
    }


async def test_state_timeline_labels_solution_fill_self_transition_as_inflow_correction() -> None:
    task = SimpleNamespace(
        id=22,
        status="pending",
        error_code=None,
        error_message=None,
        workflow=WorkflowState(
            current_stage="solution_fill_check",
            workflow_phase="tank_filling",
            stage_deadline_at=None,
            stage_retry_count=0,
            stage_entered_at=NOW.replace(tzinfo=None),
            clean_fill_cycle=0,
            control_mode="auto",
            pending_manual_step=None,
        ),
        correction=None,
    )

    transitions = [
        {
            "from_stage": "solution_fill_check",
            "to_stage": "solution_fill_check",
            "workflow_phase": "tank_filling",
            "triggered_at": NOW.replace(tzinfo=None),
            "metadata": {},
        }
    ]

    async def fetch_fn(query, *args):
        return []

    use_case = GetZoneAutomationStateUseCase(
        task_repository=_TaskRepo(active_task=task, transitions=transitions),
        workflow_repository=None,
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=1)

    assert result["timeline"][0]["event"] == "SOLUTION_FILL_CORRECTION"
    assert result["timeline"][0]["label"] == "Коррекция раствора при наполнении"


async def test_state_timeline_labels_new_fail_safe_transitions() -> None:
    task = SimpleNamespace(
        id=55,
        status="failed",
        error_code="solution_fill_leak_detected",
        error_message="Solution minimum level dropped during solution fill",
        workflow=WorkflowState(
            current_stage="solution_fill_leak_stop",
            workflow_phase="tank_filling",
            stage_deadline_at=None,
            stage_retry_count=0,
            stage_entered_at=NOW.replace(tzinfo=None),
            clean_fill_cycle=0,
            control_mode="auto",
            pending_manual_step=None,
        ),
        correction=None,
    )

    async def fetch_fn(query, *args):
        if "FROM sensors s" in query:
            return []
        if "FROM zone_events" in query:
            return []
        return []

    use_case = GetZoneAutomationStateUseCase(
        task_repository=_TaskRepo(
            active_task=task,
            transitions=[
                {
                    "from_stage": "clean_fill_check",
                    "to_stage": "clean_fill_retry_stop",
                    "triggered_at": NOW.replace(tzinfo=None),
                },
                {
                    "from_stage": "solution_fill_check",
                    "to_stage": "solution_fill_leak_stop",
                    "triggered_at": (NOW + timedelta(seconds=1)).replace(tzinfo=None),
                },
            ],
        ),
        workflow_repository=None,
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=7)

    assert result["timeline"][0]["event"] == "CLEAN_FILL_SOURCE_EMPTY"
    assert "безопасная остановка и повтор" in result["timeline"][0]["label"]
    assert result["timeline"][1]["event"] == "SOLUTION_FILL_LEAK_DETECTED"
    assert "нижний уровень раствора пропал" in result["timeline"][1]["label"]


async def test_state_timeline_includes_node_level_switch_events() -> None:
    task = SimpleNamespace(
        id=22,
        status="pending",
        updated_at=NOW.replace(tzinfo=None),
        error_code=None,
        error_message=None,
        workflow=WorkflowState(
            current_stage="solution_fill_check",
            workflow_phase="tank_filling",
            stage_deadline_at=None,
            stage_retry_count=0,
            stage_entered_at=NOW.replace(tzinfo=None),
            clean_fill_cycle=0,
            control_mode="auto",
            pending_manual_step=None,
        ),
        correction=None,
    )

    transitions = [
        {
            "from_stage": "solution_fill_start",
            "to_stage": "solution_fill_check",
            "workflow_phase": "tank_filling",
            "triggered_at": NOW.replace(tzinfo=None),
            "metadata": {},
        }
    ]

    async def fetch_fn(query, *args):
        if "FROM zone_events" in query:
            return [
                {
                    "type": "LEVEL_SWITCH_CHANGED",
                    "created_at": NOW.replace(tzinfo=None) + timedelta(seconds=2),
                    "payload": {
                        "channel": "level_solution_max",
                        "state": True,
                        "initial": False,
                    },
                }
            ]
        return []

    use_case = GetZoneAutomationStateUseCase(
        task_repository=_TaskRepo(active_task=task, transitions=transitions),
        workflow_repository=None,
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=1)

    assert len(result["timeline"]) == 2
    assert result["timeline"][0]["event"] == "SOLUTION_FILL_IN_PROGRESS"
    assert result["timeline"][1]["event"] == "LEVEL_SWITCH_CHANGED"
    assert "Верхний уровень раствора" in result["timeline"][1]["label"]
    assert result["timeline"][1]["active"] is True


async def test_state_prefers_solution_max_over_solution_min_for_full_tank() -> None:
    workflow = ZoneWorkflow(
        zone_id=1,
        workflow_phase="ready",
        version=3,
        scheduler_task_id="11",
        started_at=NOW.replace(tzinfo=None),
        updated_at=NOW.replace(tzinfo=None),
        payload={"ae3_cycle_start_stage": "complete_ready"},
    )

    async def fetch_fn(query, *args):
        if "FROM sensors s" in query:
            return [
                {"label": "level_solution_max", "type": "WATER_LEVEL", "last_value": 1.0, "last_ts": NOW, "last_quality": "GOOD"},
                {"label": "level_solution_min", "type": "WATER_LEVEL", "last_value": 1.0, "last_ts": NOW, "last_quality": "GOOD"},
            ]
        return []

    use_case = GetZoneAutomationStateUseCase(
        task_repository=_TaskRepo(),
        workflow_repository=_WorkflowRepo(workflow),
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=1)

    assert result["current_levels"]["nutrient_tank_level_percent"] == 100


async def test_workflow_state_timeline_includes_node_runtime_events_without_active_task() -> None:
    workflow = ZoneWorkflow(
        zone_id=7,
        workflow_phase="ready",
        version=5,
        scheduler_task_id="21",
        started_at=NOW.replace(tzinfo=None),
        updated_at=NOW.replace(tzinfo=None),
        payload={"ae3_cycle_start_stage": "complete_ready"},
    )

    async def fetch_fn(query, *args):
        if "FROM sensors s" in query:
            return []
        if "FROM zone_events" in query:
            return [
                {
                    "type": "LEVEL_SWITCH_CHANGED",
                    "created_at": NOW.replace(tzinfo=None) + timedelta(seconds=1),
                    "payload": {
                        "channel": "level_solution_min",
                        "state": False,
                        "initial": False,
                    },
                }
            ]
        return []

    use_case = GetZoneAutomationStateUseCase(
        task_repository=_TaskRepo(),
        workflow_repository=_WorkflowRepo(workflow),
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=7)

    assert len(result["timeline"]) == 1
    assert result["timeline"][0]["event"] == "LEVEL_SWITCH_CHANGED"
    assert "Нижний уровень раствора" in result["timeline"][0]["label"]
    assert result["timeline"][0]["active"] is True


async def test_state_reports_mid_level_when_solution_min_is_active_but_solution_max_is_not() -> None:
    workflow = ZoneWorkflow(
        zone_id=1,
        workflow_phase="ready",
        version=3,
        scheduler_task_id="11",
        started_at=NOW.replace(tzinfo=None),
        updated_at=NOW.replace(tzinfo=None),
        payload={"ae3_cycle_start_stage": "complete_ready"},
    )

    async def fetch_fn(query, *args):
        if "FROM sensors s" in query:
            return [
                {"label": "level_solution_max", "type": "WATER_LEVEL_SWITCH", "last_value": 0.0, "last_ts": NOW, "last_quality": "GOOD"},
                {"label": "level_solution_min", "type": "WATER_LEVEL_SWITCH", "last_value": 1.0, "last_ts": NOW, "last_quality": "GOOD"},
            ]
        return []

    use_case = GetZoneAutomationStateUseCase(
        task_repository=_TaskRepo(),
        workflow_repository=_WorkflowRepo(workflow),
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=1)

    assert result["current_levels"]["nutrient_tank_level_percent"] == 50


async def test_idle_state_timeline_includes_recent_node_runtime_events() -> None:
    async def fetch_fn(query, *args):
        if "FROM sensors s" in query:
            return []
        if "FROM zone_events" in query:
            return [
                {
                    "type": "SOLUTION_FILL_COMPLETED",
                    "created_at": NOW.replace(tzinfo=None) - timedelta(minutes=1),
                    "payload": {},
                }
            ]
        return []

    use_case = GetZoneAutomationStateUseCase(
        task_repository=_TaskRepo(),
        workflow_repository=None,
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=3)

    assert result["state"] == "IDLE"
    assert len(result["timeline"]) == 1
    assert result["timeline"][0]["event"] == "SOLUTION_FILL_COMPLETED"
    assert result["timeline"][0]["label"] == "Событие ноды: раствор заполнен"


async def test_idle_state_timeline_labels_emergency_stop_and_fail_safe_events() -> None:
    async def fetch_fn(query, *args):
        if "FROM sensors s" in query:
            return []
        if "FROM zone_events" in query:
            return [
                {
                    "type": "EMERGENCY_STOP_ACTIVATED",
                    "created_at": NOW.replace(tzinfo=None),
                    "payload": {"channel": "storage_state"},
                },
                {
                    "type": "RECIRCULATION_SOLUTION_LOW",
                    "created_at": (NOW + timedelta(seconds=5)).replace(tzinfo=None),
                    "payload": {"channel": "storage_state"},
                },
            ]
        return []

    use_case = GetZoneAutomationStateUseCase(
        task_repository=_TaskRepo(),
        workflow_repository=None,
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=7)

    assert [item["event"] for item in result["timeline"]] == [
        "EMERGENCY_STOP_ACTIVATED",
        "RECIRCULATION_SOLUTION_LOW",
    ]
    assert result["timeline"][0]["label"] == "Событие ноды: активирован аварийный стоп"
    assert result["timeline"][1]["label"] == "Событие ноды: рециркуляция остановлена по низкому уровню раствора"


async def test_state_prefers_terminal_last_task_over_stale_active_workflow_snapshot() -> None:
    workflow = ZoneWorkflow(
        zone_id=1,
        workflow_phase="tank_filling",
        version=9,
        scheduler_task_id="454",
        started_at=NOW.replace(tzinfo=None),
        updated_at=NOW.replace(tzinfo=None),
        payload={"ae3_cycle_start_stage": "solution_fill_start"},
    )
    task = SimpleNamespace(
        id=454,
        status="failed",
        error_code="command_timeout",
        error_message="TIMEOUT",
        updated_at=(NOW.replace(tzinfo=None)),
        workflow=WorkflowState(
            current_stage="solution_fill_start",
            workflow_phase="tank_filling",
            stage_deadline_at=None,
            stage_retry_count=0,
            stage_entered_at=NOW.replace(tzinfo=None),
            clean_fill_cycle=0,
            control_mode="auto",
            pending_manual_step=None,
        ),
        correction=None,
    )

    async def fetch_fn(query, *args):
        return []

    use_case = GetZoneAutomationStateUseCase(
        task_repository=_TaskRepo(last_task=task),
        workflow_repository=_WorkflowRepo(workflow),
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=1)

    assert result["state"] == "IDLE"
    assert result["state_details"]["failed"] is True
    assert result["state_details"]["error_code"] == "command_timeout"
    assert result["current_stage"] == "solution_fill_start"
