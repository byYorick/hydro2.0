from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ae3lite.application.dto import ZoneActuatorRef, ZoneSnapshot
from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services import CycleStartPlanner


def _task(now: datetime) -> AutomationTask:
    return AutomationTask.from_row({
        "id": 71, "zone_id": 9, "task_type": "cycle_start", "status": "claimed",
        "idempotency_key": "planner-test", "scheduled_for": now, "due_at": now,
        "claimed_by": "worker-a", "claimed_at": now, "error_code": None, "error_message": None,
        "created_at": now, "updated_at": now, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "startup", "workflow_phase": "idle",
        "stage_deadline_at": None, "stage_retry_count": 0, "stage_entered_at": None,
        "clean_fill_cycle": 0, "corr_step": None,
    })


def _snapshot() -> ZoneSnapshot:
    return ZoneSnapshot(
        zone_id=9,
        greenhouse_id=3,
        automation_runtime="ae3",
        grow_cycle_id=101,
        current_phase_id=301,
        phase_name="VEG",
        workflow_phase="idle",
        workflow_version=4,
        targets={"ph": {"target": 5.9}},
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "generic_cycle_start",
            "required_node_types": ["irrig"],
        },
        command_plans={
            "schema_version": 1,
            "plan_version": 1,
            "plans": {
                "diagnostics": {
                    "steps": [
                        {
                            "channel": "irrigation_pump",
                            "cmd": "set_relay",
                            "params": {"state": True},
                        }
                    ]
                }
            },
        },
        telemetry_last={},
        pid_state={},
        pid_configs={},
        actuators=(
            ZoneActuatorRef(
                node_uid="nd-irrig-1",
                node_type="irrig",
                channel="pump_main",
                node_channel_id=41,
                role="irrigation_pump",
            ),
        ),
    )


def test_cycle_start_planner_builds_resolved_sequential_plan() -> None:
    now = datetime.now(timezone.utc)
    planner = CycleStartPlanner()

    plan = planner.build(task=_task(now), snapshot=_snapshot())

    assert plan.workflow == "cycle_start"
    assert plan.topology == "generic_cycle_start"
    assert len(plan.steps) == 1
    assert plan.steps[0].step_no == 1
    assert plan.steps[0].node_uid == "nd-irrig-1"
    assert plan.steps[0].channel == "pump_main"
    assert plan.steps[0].payload["requested_channel"] == "irrigation_pump"


def test_cycle_start_planner_builds_native_two_tank_named_plans() -> None:
    now = datetime.now(timezone.utc)
    planner = CycleStartPlanner()
    snapshot = ZoneSnapshot(
        **{
            **_snapshot().__dict__,
            "targets": {"ph": {"target": 5.9}, "ec": {"target": 1.4}},
            "diagnostics_execution": {
                "workflow": "cycle_start",
                "topology": "two_tank_drip_substrate_trays",
                "required_node_types": ["irrig"],
                "startup": {
                    "clean_fill_timeout_sec": 30,
                    "solution_fill_timeout_sec": 45,
                    "prepare_recirculation_timeout_sec": 60,
                },
                "two_tank_commands": {
                    "clean_fill_start": [{"channel": "valve_clean_fill", "cmd": "set_relay", "params": {"state": True}}],
                },
            },
            "actuators": (
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_clean_fill", node_channel_id=41, role="valve_clean_fill"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_clean_supply", node_channel_id=42, role="valve_clean_supply"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_solution_fill", node_channel_id=43, role="valve_solution_fill"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_solution_supply", node_channel_id=44, role="valve_solution_supply"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="pump_main", node_channel_id=45, role="pump_main"),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="system", node_channel_id=46, role="system", channel_type="SERVICE"),
                ZoneActuatorRef(node_uid="nd-ec-1", node_type="ec", channel="system", node_channel_id=47, role="system", channel_type="SERVICE"),
            ),
        }
    )

    plan = planner.build(task=_task(now), snapshot=snapshot)

    assert plan.topology == "two_tank_drip_substrate_trays"
    assert plan.steps == ()
    assert plan.named_plans["clean_fill_start"][0].channel == "valve_clean_fill"
    assert plan.named_plans["sensor_mode_activate"][0].channel == "system"
    assert plan.named_plans["irr_state_probe"][0].channel == "storage_state"


def test_cycle_start_planner_rejects_unsupported_schema_version() -> None:
    now = datetime.now(timezone.utc)
    planner = CycleStartPlanner()
    snapshot = _snapshot()
    broken_snapshot = ZoneSnapshot(
        **{
            **snapshot.__dict__,
            "command_plans": {
                "schema_version": 2,
                "plan_version": 1,
                "plans": {"diagnostics": {"steps": []}},
            },
        }
    )

    with pytest.raises(PlannerConfigurationError):
        planner.build(task=_task(now), snapshot=broken_snapshot)


def test_cycle_start_planner_fails_when_channel_cannot_be_resolved() -> None:
    now = datetime.now(timezone.utc)
    planner = CycleStartPlanner()
    snapshot = _snapshot()
    unresolved_snapshot = ZoneSnapshot(
        **{
            **snapshot.__dict__,
            "actuators": (
                ZoneActuatorRef(
                    node_uid="nd-irrig-1",
                    node_type="irrig",
                    channel="valve_clean_fill",
                    node_channel_id=41,
                    role="clean_fill_valve",
                ),
            ),
        }
    )

    with pytest.raises(PlannerConfigurationError):
        planner.build(task=_task(now), snapshot=unresolved_snapshot)


def test_cycle_start_planner_fails_closed_on_ambiguous_actuator_resolution() -> None:
    now = datetime.now(timezone.utc)
    planner = CycleStartPlanner()
    snapshot = _snapshot()
    ambiguous_snapshot = ZoneSnapshot(
        **{
            **snapshot.__dict__,
            "actuators": (
                ZoneActuatorRef(
                    node_uid="nd-irrig-1",
                    node_type="irrig",
                    channel="pump_main",
                    node_channel_id=41,
                    role="irrigation_pump",
                ),
                ZoneActuatorRef(
                    node_uid="nd-irrig-2",
                    node_type="irrig",
                    channel="pump_backup",
                    node_channel_id=42,
                    role="irrigation_pump",
                ),
            ),
        }
    )

    with pytest.raises(PlannerConfigurationError):
        planner.build(task=_task(now), snapshot=ambiguous_snapshot)
