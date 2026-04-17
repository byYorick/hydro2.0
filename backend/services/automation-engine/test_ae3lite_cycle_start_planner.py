from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ae3lite.application.dto import ZoneActuatorRef, ZoneSnapshot
from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services.cycle_start_planner import CycleStartPlanner


def _minimal_zone_correction_config() -> dict:
    return {
        "base": {
            "runtime": {
                "required_node_type": "irrig",
                "clean_fill_timeout_sec": 1200,
                "solution_fill_timeout_sec": 1800,
                "clean_fill_retry_cycles": 1,
                "level_switch_on_threshold": 0.5,
                "clean_max_sensor_label": "level_clean_max",
                "clean_min_sensor_label": "level_clean_min",
                "solution_max_sensor_label": "level_solution_max",
                "solution_min_sensor_label": "level_solution_min",
            },
            "timing": {
                "sensor_mode_stabilization_time_sec": 60,
                "stabilization_sec": 60,
                "telemetry_max_age_sec": 60,
                "irr_state_max_age_sec": 30,
                "level_poll_interval_sec": 10,
            },
            "retry": {
                "max_ec_correction_attempts": 5,
                "max_ph_correction_attempts": 5,
                "prepare_recirculation_timeout_sec": 1200,
                "prepare_recirculation_correction_slack_sec": 0,
                "prepare_recirculation_max_attempts": 3,
                "prepare_recirculation_max_correction_attempts": 20,
                "telemetry_stale_retry_sec": 15,
                "decision_window_retry_sec": 20,
                "low_water_retry_sec": 30,
            },
            "dosing": {
                "solution_volume_l": 100.0,
                "dose_ec_channel": "pump_a",
                "dose_ph_up_channel": "pump_base",
                "dose_ph_down_channel": "pump_acid",
                "max_ec_dose_ml": 50.0,
                "max_ph_dose_ml": 20.0,
                "ec_dosing_mode": "single",
            },
            "tolerance": {
                "prepare_tolerance": {"ph_pct": 15.0, "ec_pct": 25.0},
            },
            "controllers": {
                "ph": {
                    "mode": "cross_coupled_pi_d",
                    "kp": 5.0,
                    "ki": 0.05,
                    "kd": 0.0,
                    "derivative_filter_alpha": 0.35,
                    "deadband": 0.05,
                    "max_dose_ml": 20.0,
                    "min_interval_sec": 90,
                    "max_integral": 20.0,
                    "anti_windup": {"enabled": True},
                    "overshoot_guard": {"enabled": True, "hard_min": 4.0, "hard_max": 9.0},
                    "no_effect": {"enabled": True, "max_count": 3},
                    "observe": {
                        "telemetry_period_sec": 2,
                        "window_min_samples": 3,
                        "decision_window_sec": 6,
                        "observe_poll_sec": 2,
                        "min_effect_fraction": 0.25,
                        "stability_max_slope": 0.02,
                        "no_effect_consecutive_limit": 3,
                    },
                },
                "ec": {
                    "mode": "supervisory_allocator",
                    "kp": 30.0,
                    "ki": 0.3,
                    "kd": 0.0,
                    "derivative_filter_alpha": 0.35,
                    "deadband": 0.1,
                    "max_dose_ml": 50.0,
                    "min_interval_sec": 120,
                    "max_integral": 100.0,
                    "anti_windup": {"enabled": True},
                    "overshoot_guard": {"enabled": True, "hard_min": 0.0, "hard_max": 10.0},
                    "no_effect": {"enabled": True, "max_count": 3},
                    "observe": {
                        "telemetry_period_sec": 2,
                        "window_min_samples": 3,
                        "decision_window_sec": 6,
                        "observe_poll_sec": 2,
                        "min_effect_fraction": 0.25,
                        "stability_max_slope": 0.05,
                        "no_effect_consecutive_limit": 3,
                    },
                },
            },
            "safety": {
                "safe_mode_on_no_effect": True,
                "block_on_active_no_effect_alert": True,
            },
        },
        "phases": {
            "solution_fill": {},
            "tank_recirc": {},
            "irrigation": {},
        },
        "meta": {},
    }


def _minimal_pid_configs() -> dict:
    return {
        "ph": {"config": {"kp": 1.0, "ki": 0.1, "kd": 0.0}},
        "ec": {"config": {"kp": 1.0, "ki": 0.1, "kd": 0.0}},
    }


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
        phase_targets={
            "ph": {"target": 5.9, "min": 5.7, "max": 6.1},
            "ec": {"target": 1.4, "min": 1.2, "max": 1.6},
        },
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
                            "channel": "pump_main",
                            "cmd": "set_relay",
                            "params": {"state": True},
                        }
                    ]
                }
            },
        },
        telemetry_last={},
        pid_state={},
        pid_configs=_minimal_pid_configs(),
        process_calibrations={
            "solution_fill": {
                "transport_delay_sec": 6,
                "settle_sec": 4,
                "ec_gain_per_ml": 0.1,
                "ph_up_gain_per_ml": 0.05,
                "ph_down_gain_per_ml": -0.05,
            },
            "tank_recirc": {
                "transport_delay_sec": 6,
                "settle_sec": 4,
                "ec_gain_per_ml": 0.1,
                "ph_up_gain_per_ml": 0.05,
                "ph_down_gain_per_ml": -0.05,
            },
            "irrigation": {
                "transport_delay_sec": 6,
                "settle_sec": 4,
                "ec_gain_per_ml": 0.1,
                "ph_up_gain_per_ml": 0.05,
                "ph_down_gain_per_ml": -0.05,
            },
        },
        actuators=(
            ZoneActuatorRef(
                node_uid="nd-irrig-1",
                node_type="irrig",
                channel="pump_main",
                node_channel_id=41,
                role="pump_main",
            ),
        ),
        correction_config=_minimal_zone_correction_config(),
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
    assert plan.steps[0].payload["requested_channel"] == "pump_main"


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
                    "irr_state_wait_timeout_sec": 5.0,
                    "clean_fill_timeout_sec": 30,
                    "solution_fill_timeout_sec": 45,
                    "prepare_recirculation_timeout_sec": 240,
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
                    ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_irrigation", node_channel_id=445, role="valve_irrigation"),
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


def test_cycle_start_planner_builds_native_two_tank_with_short_alias() -> None:
    """topology='two_tank' (short alias) must route to two-tank planner, not generic."""
    now = datetime.now(timezone.utc)
    planner = CycleStartPlanner()
    snapshot = ZoneSnapshot(
        **{
            **_snapshot().__dict__,
            "targets": {"ph": {"target": 5.9}, "ec": {"target": 1.4}},
            "diagnostics_execution": {
                "workflow": "cycle_start",
                "topology": "two_tank",
                "required_node_types": ["irrig"],
                "startup": {
                    "irr_state_wait_timeout_sec": 5.0,
                    "clean_fill_timeout_sec": 30,
                    "solution_fill_timeout_sec": 45,
                    "prepare_recirculation_timeout_sec": 240,
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
                    ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_irrigation", node_channel_id=445, role="valve_irrigation"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="pump_main", node_channel_id=45, role="pump_main"),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="system", node_channel_id=46, role="system", channel_type="SERVICE"),
                ZoneActuatorRef(node_uid="nd-ec-1", node_type="ec", channel="system", node_channel_id=47, role="system", channel_type="SERVICE"),
            ),
        }
    )

    plan = planner.build(task=_task(now), snapshot=snapshot)

    # Must use two-tank specific planner: named_plans populated, steps empty
    assert plan.topology == "two_tank"
    assert plan.steps == ()
    assert "clean_fill_start" in plan.named_plans
    assert "sensor_mode_activate" in plan.named_plans
    assert "irr_state_probe" in plan.named_plans
    assert plan.named_plans["irr_state_probe"][0].channel == "storage_state"


def test_two_tank_plan_runtime_zone_workflow_phase_matches_snapshot_workflow_phase() -> None:
    """Block A: plan.runtime.zone_workflow_phase is the bridge await_ready uses (see ae3lite.md §2.1)."""
    now = datetime.now(timezone.utc)
    planner = CycleStartPlanner()
    snapshot = ZoneSnapshot(
        **{
            **_snapshot().__dict__,
            "workflow_phase": "ready",
            "targets": {"ph": {"target": 5.9}, "ec": {"target": 1.4}},
            "diagnostics_execution": {
                "workflow": "cycle_start",
                "topology": "two_tank",
                "required_node_types": ["irrig"],
                "startup": {
                    "irr_state_wait_timeout_sec": 5.0,
                    "clean_fill_timeout_sec": 30,
                    "solution_fill_timeout_sec": 45,
                    "prepare_recirculation_timeout_sec": 240,
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
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_irrigation", node_channel_id=445, role="valve_irrigation"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="pump_main", node_channel_id=45, role="pump_main"),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="system", node_channel_id=46, role="system", channel_type="SERVICE"),
                ZoneActuatorRef(node_uid="nd-ec-1", node_type="ec", channel="system", node_channel_id=47, role="system", channel_type="SERVICE"),
            ),
        }
    )
    plan = planner.build(task=_task(now), snapshot=snapshot)
    assert plan.runtime.zone_workflow_phase == "ready"


def test_cycle_start_planner_uses_locked_irrigation_decision_snapshot_for_active_task() -> None:
    now = datetime.now(timezone.utc)
    planner = CycleStartPlanner()
    task = AutomationTask.from_row({
        "id": 72, "zone_id": 9, "task_type": "irrigation_start", "status": "running",
        "idempotency_key": "planner-irrigation-lock", "scheduled_for": now, "due_at": now,
        "claimed_by": "worker-a", "claimed_at": now, "error_code": None, "error_message": None,
        "created_at": now, "updated_at": now, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "await_ready", "workflow_phase": "idle",
        "stage_deadline_at": None, "stage_retry_count": 0, "stage_entered_at": None,
        "clean_fill_cycle": 0,
        "irrigation_decision_strategy": "task",
        "irrigation_decision_config": {
            "lookback_sec": 900,
            "min_samples": 2,
        },
        "irrigation_bundle_revision": "bundle-locked-1234567890",
        "corr_step": None,
    })
    snapshot = ZoneSnapshot(
        **{
            **_snapshot().__dict__,
            "diagnostics_execution": {
                "workflow": "cycle_start",
                "topology": "two_tank_drip_substrate_trays",
                "required_node_types": ["irrig"],
                "startup": {
                    "irr_state_wait_timeout_sec": 5.0,
                    "clean_fill_timeout_sec": 30,
                    "solution_fill_timeout_sec": 45,
                    "prepare_recirculation_timeout_sec": 240,
                },
                "two_tank_commands": {
                    "clean_fill_start": [{"channel": "valve_clean_fill", "cmd": "set_relay", "params": {"state": True}}],
                },
            },
            "bundle_revision": "bundle-live-9999999999",
            "actuators": (
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_clean_fill", node_channel_id=41, role="valve_clean_fill"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_clean_supply", node_channel_id=42, role="valve_clean_supply"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_solution_fill", node_channel_id=43, role="valve_solution_fill"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_solution_supply", node_channel_id=44, role="valve_solution_supply"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_irrigation", node_channel_id=445, role="valve_irrigation"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="pump_main", node_channel_id=45, role="pump_main"),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="system", node_channel_id=46, role="system", channel_type="SERVICE"),
                ZoneActuatorRef(node_uid="nd-ec-1", node_type="ec", channel="system", node_channel_id=47, role="system", channel_type="SERVICE"),
            ),
        }
    )

    plan = planner.build(task=task, snapshot=snapshot)

    assert plan.runtime.irrigation_decision.strategy == "task"
    assert plan.runtime.irrigation_decision.config.lookback_sec == 900
    assert plan.runtime.irrigation_decision.config.min_samples == 2
    assert plan.runtime.bundle_revision == "bundle-locked-1234567890"


def test_cycle_start_planner_rejects_incomplete_solution_fill_start_contract() -> None:
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
                    "irr_state_wait_timeout_sec": 5.0,
                    "clean_fill_timeout_sec": 30,
                    "solution_fill_timeout_sec": 45,
                    "prepare_recirculation_timeout_sec": 240,
                },
                "two_tank_commands": {
                    "solution_fill_start": [{"channel": "valve_clean_supply", "cmd": "set_relay", "params": {"state": True}}],
                },
            },
            "actuators": (
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_clean_fill", node_channel_id=41, role="valve_clean_fill"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_clean_supply", node_channel_id=42, role="valve_clean_supply"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_solution_fill", node_channel_id=43, role="valve_solution_fill"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_solution_supply", node_channel_id=44, role="valve_solution_supply"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_irrigation", node_channel_id=445, role="valve_irrigation"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="pump_main", node_channel_id=45, role="pump_main"),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="system", node_channel_id=46, role="system", channel_type="SERVICE"),
                ZoneActuatorRef(node_uid="nd-ec-1", node_type="ec", channel="system", node_channel_id=47, role="system", channel_type="SERVICE"),
            ),
        }
    )

    with pytest.raises(PlannerConfigurationError) as exc:
        planner.build(task=_task(now), snapshot=snapshot)

    assert "solution_fill_start" in str(exc.value)
    assert "valve_solution_fill" in str(exc.value)
    assert "pump_main" in str(exc.value)


def test_cycle_start_planner_injects_stage_timeout_guard_into_pump_main_start() -> None:
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
                    "irr_state_wait_timeout_sec": 5.0,
                },
            },
            "command_plans": {
                "schema_version": 1,
                "plan_version": 1,
                "plans": {"diagnostics": {"steps": []}},
            },
            "actuators": (
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_clean_fill", node_channel_id=41, role="valve_clean_fill"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_clean_supply", node_channel_id=42, role="valve_clean_supply"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_solution_fill", node_channel_id=43, role="valve_solution_fill"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_solution_supply", node_channel_id=44, role="valve_solution_supply"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_irrigation", node_channel_id=445, role="valve_irrigation"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="pump_main", node_channel_id=45, role="pump_main"),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="system", node_channel_id=46, role="system", channel_type="SERVICE"),
                ZoneActuatorRef(node_uid="nd-ec-1", node_type="ec", channel="system", node_channel_id=47, role="system", channel_type="SERVICE"),
            ),
        }
    )

    plan = planner.build(task=_task(now), snapshot=snapshot)

    solution_fill = plan.named_plans["solution_fill_start"]
    guarded = next(cmd for cmd in solution_fill if cmd.channel == "pump_main")
    assert guarded.payload["params"]["timeout_ms"] == 1800 * 1000
    assert guarded.payload["params"]["stage"] == "solution_fill"
    assert guarded.payload["complete_on_ack"] is True

    recirc = plan.named_plans["prepare_recirculation_start"]
    guarded_recirc = next(cmd for cmd in recirc if cmd.channel == "pump_main")
    assert guarded_recirc.payload["params"]["timeout_ms"] == 1200 * 1000
    assert guarded_recirc.payload["params"]["stage"] == "prepare_recirculation"
    assert guarded_recirc.payload["complete_on_ack"] is True


def test_cycle_start_planner_ignores_empty_generic_steps_for_native_two_tank_topology() -> None:
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
                    "irr_state_wait_timeout_sec": 5.0,
                },
                "two_tank_commands": {
                    "clean_fill_start": [{"channel": "valve_clean_fill", "cmd": "set_relay", "params": {"state": True}}],
                },
            },
            "command_plans": {
                "schema_version": 1,
                "plan_version": 1,
                "plans": {
                    "diagnostics": {
                        "steps": [],
                    }
                },
            },
            "actuators": (
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_clean_fill", node_channel_id=41, role="valve_clean_fill"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_clean_supply", node_channel_id=42, role="valve_clean_supply"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_solution_fill", node_channel_id=43, role="valve_solution_fill"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_solution_supply", node_channel_id=44, role="valve_solution_supply"),
                    ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_irrigation", node_channel_id=445, role="valve_irrigation"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="pump_main", node_channel_id=45, role="pump_main"),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="system", node_channel_id=46, role="system", channel_type="SERVICE"),
                ZoneActuatorRef(node_uid="nd-ec-1", node_type="ec", channel="system", node_channel_id=47, role="system", channel_type="SERVICE"),
            ),
        }
    )

    plan = planner.build(task=_task(now), snapshot=snapshot)

    assert plan.topology == "two_tank_drip_substrate_trays"
    assert plan.steps == ()
    assert "clean_fill_start" in plan.named_plans


def test_cycle_start_planner_resolves_legacy_dosing_aliases_from_bound_pumps() -> None:
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
                    "irr_state_wait_timeout_sec": 5.0,
                    "clean_fill_timeout_sec": 30,
                    "solution_fill_timeout_sec": 45,
                    "prepare_recirculation_timeout_sec": 240,
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
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_irrigation", node_channel_id=445, role="valve_irrigation"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="pump_main", node_channel_id=45, role="pump_main"),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="pump_acid", node_channel_id=46, role="pump_acid", pump_calibration={"ml_per_sec": 1.0}),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="pump_base", node_channel_id=47, role="pump_base", pump_calibration={"ml_per_sec": 1.0}),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="system", node_channel_id=48, role="system", channel_type="SERVICE"),
                ZoneActuatorRef(
                    node_uid="nd-ec-1",
                    node_type="ec",
                    channel="pump_a",
                    node_channel_id=49,
                    role="pump_a",
                    pump_calibration={"component": "npk", "ml_per_sec": 1.0},
                ),
                ZoneActuatorRef(node_uid="nd-ec-1", node_type="ec", channel="system", node_channel_id=50, role="system", channel_type="SERVICE"),
            ),
        }
    )

    plan = planner.build(task=_task(now), snapshot=snapshot)

    correction_actuators = plan.runtime.correction.actuators
    assert correction_actuators["ec"]["channel"] == "pump_a"
    assert correction_actuators["ph_up"]["channel"] == "pump_base"
    assert correction_actuators["ph_down"]["channel"] == "pump_acid"


def test_cycle_start_planner_resolves_modern_dosing_names_to_legacy_roles() -> None:
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
                    "irr_state_wait_timeout_sec": 5.0,
                    "clean_fill_timeout_sec": 30,
                    "solution_fill_timeout_sec": 45,
                    "prepare_recirculation_timeout_sec": 240,
                },
                "correction": {
                    "dose_ec_channel": "pump_a",
                    "dose_ph_up_channel": "pump_base",
                    "dose_ph_down_channel": "pump_acid",
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
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_irrigation", node_channel_id=445, role="valve_irrigation"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="pump_main", node_channel_id=45, role="pump_main"),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="pump_acid", node_channel_id=46, role="pump_acid", pump_calibration={"ml_per_sec": 1.0}),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="pump_base", node_channel_id=47, role="pump_base", pump_calibration={"ml_per_sec": 1.0}),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="system", node_channel_id=48, role="system", channel_type="SERVICE"),
                ZoneActuatorRef(node_uid="nd-ec-1", node_type="ec", channel="pump_a", node_channel_id=49, role="pump_a", pump_calibration={"component": "npk", "ml_per_sec": 1.0}),
                ZoneActuatorRef(node_uid="nd-ec-1", node_type="ec", channel="system", node_channel_id=50, role="system", channel_type="SERVICE"),
            ),
        }
    )

    plan = planner.build(task=_task(now), snapshot=snapshot)

    correction_actuators = plan.runtime.correction.actuators
    assert correction_actuators["ec"]["channel"] == "pump_a"
    assert correction_actuators["ph_up"]["channel"] == "pump_base"
    assert correction_actuators["ph_down"]["channel"] == "pump_acid"


def test_cycle_start_planner_fails_closed_when_dosing_calibration_missing_preflight() -> None:
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
                    "irr_state_wait_timeout_sec": 5.0,
                    "clean_fill_timeout_sec": 30,
                    "solution_fill_timeout_sec": 45,
                    "prepare_recirculation_timeout_sec": 240,
                },
                "correction": {
                    "dose_ec_channel": "pump_a",
                    "dose_ph_up_channel": "pump_base",
                    "dose_ph_down_channel": "pump_acid",
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
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_irrigation", node_channel_id=445, role="valve_irrigation"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="pump_main", node_channel_id=45, role="pump_main"),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="pump_acid", node_channel_id=46, role="pump_acid", pump_calibration={"ml_per_sec": 1.0}),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="pump_base", node_channel_id=47, role="pump_base", pump_calibration={"ml_per_sec": 1.0}),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="system", node_channel_id=48, role="system", channel_type="SERVICE"),
                ZoneActuatorRef(node_uid="nd-ec-1", node_type="ec", channel="pump_a", node_channel_id=49, role="pump_a"),
                ZoneActuatorRef(node_uid="nd-ec-1", node_type="ec", channel="system", node_channel_id=50, role="system", channel_type="SERVICE"),
            ),
        }
    )

    with pytest.raises(PlannerConfigurationError) as exc:
        planner.build(task=_task(now), snapshot=snapshot)

    assert getattr(exc.value, "code", None) == "zone_dosing_calibration_missing_critical"
    assert "channel=pump_a" in str(exc.value)


def test_cycle_start_planner_allows_uncalibrated_unused_ec_backup_channels() -> None:
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
                    "irr_state_wait_timeout_sec": 5.0,
                    "clean_fill_timeout_sec": 30,
                    "solution_fill_timeout_sec": 45,
                    "prepare_recirculation_timeout_sec": 240,
                },
                "correction": {
                    "dose_ec_channel": "pump_a",
                    "dose_ph_up_channel": "pump_base",
                    "dose_ph_down_channel": "pump_acid",
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
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_irrigation", node_channel_id=445, role="valve_irrigation"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="pump_main", node_channel_id=45, role="pump_main"),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="pump_acid", node_channel_id=46, role="pump_acid", pump_calibration={"ml_per_sec": 1.0}),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="pump_base", node_channel_id=47, role="pump_base", pump_calibration={"ml_per_sec": 1.0}),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="system", node_channel_id=48, role="system", channel_type="SERVICE"),
                ZoneActuatorRef(node_uid="nd-ec-1", node_type="ec", channel="pump_a", node_channel_id=49, role="pump_a", pump_calibration={"component": "npk", "ml_per_sec": 1.0}),
                ZoneActuatorRef(node_uid="nd-ec-1", node_type="ec", channel="pump_b", node_channel_id=50, role="pump_b"),
                ZoneActuatorRef(node_uid="nd-ec-1", node_type="ec", channel="system", node_channel_id=51, role="system", channel_type="SERVICE"),
            ),
        }
    )

    plan = planner.build(task=_task(now), snapshot=snapshot)

    correction_actuators = plan.runtime.correction.actuators
    assert correction_actuators["ec"]["channel"] == "pump_a"
    assert correction_actuators["ec_actuators"]["pump_b"]["channel"] == "pump_b"


def test_cycle_start_planner_fails_closed_when_pid_configs_missing_preflight() -> None:
    now = datetime.now(timezone.utc)
    planner = CycleStartPlanner()
    snapshot = ZoneSnapshot(
        **{
            **_snapshot().__dict__,
            "targets": {"ph": {"target": 5.9}, "ec": {"target": 1.4}},
            "pid_configs": {},
            "diagnostics_execution": {
                "workflow": "cycle_start",
                "topology": "two_tank_drip_substrate_trays",
                "required_node_types": ["irrig"],
                "startup": {
                    "irr_state_wait_timeout_sec": 5.0,
                    "clean_fill_timeout_sec": 30,
                    "solution_fill_timeout_sec": 45,
                    "prepare_recirculation_timeout_sec": 240,
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
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="valve_irrigation", node_channel_id=445, role="valve_irrigation"),
                ZoneActuatorRef(node_uid="nd-irrig-1", node_type="irrig", channel="pump_main", node_channel_id=45, role="pump_main"),
                ZoneActuatorRef(node_uid="nd-ph-1", node_type="ph", channel="system", node_channel_id=46, role="system", channel_type="SERVICE"),
                ZoneActuatorRef(node_uid="nd-ec-1", node_type="ec", channel="system", node_channel_id=47, role="system", channel_type="SERVICE"),
            ),
        }
    )

    with pytest.raises(PlannerConfigurationError) as exc:
        planner.build(task=_task(now), snapshot=snapshot)

    assert getattr(exc.value, "code", None) == "zone_pid_config_missing_critical"


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
                    role="pump_main",
                ),
                ZoneActuatorRef(
                    node_uid="nd-irrig-2",
                    node_type="irrig",
                    channel="pump_main",
                    node_channel_id=42,
                    role="pump_main",
                ),
            ),
        }
    )

    with pytest.raises(PlannerConfigurationError):
        planner.build(task=_task(now), snapshot=ambiguous_snapshot)


def test_planner_builds_lighting_tick_single_pwm_command() -> None:
    now = datetime.now(timezone.utc)
    planner = CycleStartPlanner()
    task = AutomationTask.from_row({
        "id": 81,
        "zone_id": 9,
        "task_type": "lighting_tick",
        "status": "claimed",
        "idempotency_key": "lt-test",
        "scheduled_for": now,
        "due_at": now,
        "claimed_by": "w",
        "claimed_at": now,
        "error_code": None,
        "error_message": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "topology": "lighting_tick",
        "intent_source": "laravel_scheduler",
        "intent_trigger": "lighting_tick",
        "intent_id": 1,
        "intent_meta": {},
        "current_stage": "apply",
        "workflow_phase": "ready",
        "stage_deadline_at": None,
        "stage_retry_count": 0,
        "stage_entered_at": None,
        "clean_fill_cycle": 0,
        "corr_step": None,
    })
    base = _snapshot()
    snapshot = ZoneSnapshot(
        **{
            **base.__dict__,
            "targets": {"lighting": {"pwm_duty": 73}},
            "actuators": (
                ZoneActuatorRef(
                    node_uid="nd-light-1",
                    node_type="light",
                    channel="light_main",
                    node_channel_id=501,
                    role="main",
                ),
            ),
        }
    )
    plan = planner.build(task=task, snapshot=snapshot)
    assert plan.workflow == "lighting_tick"
    assert plan.topology == "lighting_tick"
    assert len(plan.steps) == 1
    assert plan.steps[0].channel == "light_main"
    assert plan.steps[0].payload["cmd"] == "set_pwm"
    assert plan.steps[0].payload["params"]["duty"] == 73
