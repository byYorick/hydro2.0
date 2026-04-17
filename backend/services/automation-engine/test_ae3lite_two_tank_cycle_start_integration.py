from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.application.use_cases import ClaimNextTaskUseCase, ExecuteTaskUseCase, StartupRecoveryUseCase, WorkflowRouter
from ae3lite.domain.services.cycle_start_planner import CycleStartPlanner
from ae3lite.infrastructure.gateways import SequentialCommandGateway
from ae3lite.infrastructure.read_models import PgZoneRuntimeMonitor, PgZoneSnapshotReadModel
from ae3lite.infrastructure.repositories import (
    PgAeCommandRepository,
    PgAutomationTaskRepository,
    PgZoneLeaseRepository,
    PgZoneWorkflowRepository,
)
from ae3lite.runtime import Ae3RuntimeWorker
from common.db import execute, fetch
from test_ae3lite_zone_snapshot_read_model_integration import (
    _cleanup,
    _insert_greenhouse,
    _insert_grow_cycle,
    _insert_process_calibrations,
    _insert_irrig_node,
    _insert_phase,
    _insert_profile,
    _insert_recipe_revision,
    _insert_sensor,
    _insert_zone,
    _upsert_zone_bundle,
)


class _TwoTankHistoryLoggerStub:
    def __init__(self, *, zone_id: int, initial_state: dict[str, bool]) -> None:
        self._zone_id = zone_id
        self._state = dict(initial_state)

    async def publish(
        self,
        *,
        greenhouse_uid: str,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
        params: dict[str, object],
        cmd_id: str | None = None,
    ) -> str:
        if cmd == "set_relay":
            self._state[str(channel)] = bool(params.get("state"))
        await execute(
            """
            INSERT INTO commands (
                zone_id,
                channel,
                cmd,
                params,
                status,
                cmd_id,
                source,
                ack_at,
                created_at,
                updated_at
            )
            VALUES ($1, $2, $3, $4::jsonb, 'DONE', $5, 'automation-engine', NOW(), NOW(), NOW())
            """,
            zone_id,
            channel,
            cmd,
            params,
            f"hl-{cmd_id}",
        )
        if cmd == "state":
            snapshot_payload = {"snapshot": dict(self._state), "cmd_id": f"hl-{cmd_id}"}
            await execute(
                """
                INSERT INTO zone_events (zone_id, type, payload_json, created_at)
                VALUES ($1, 'IRR_STATE_SNAPSHOT', $2::jsonb, NOW())
                """,
                self._zone_id,
                snapshot_payload,
            )
        return f"hl-{cmd_id}"


async def _insert_ph_ec_support_nodes(*, zone_id: int, greenhouse_id: int) -> None:
    pid_patch: dict[str, dict[str, dict[str, float]]] = {}
    for node_type, sensor_type, sensor_label in (("ph", "PH", "ph_sensor"), ("ec", "EC", "ec_sensor")):
        rows = await fetch(
            """
            INSERT INTO nodes (zone_id, uid, type, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'online', NOW(), NOW())
            RETURNING id
            """,
            zone_id,
            f"nd-{node_type}-{uuid4().hex[:12]}",
            node_type,
        )
        node_id = int(rows[0]["id"])
        await execute(
            """
            INSERT INTO node_channels (node_id, channel, type, config, created_at, updated_at)
            VALUES ($1, 'system', 'SERVICE', '{}'::jsonb, NOW(), NOW())
            """,
            node_id,
        )
        sensor_id = await _insert_sensor(
            greenhouse_id=greenhouse_id,
            zone_id=zone_id,
            node_id=node_id,
            sensor_type=sensor_type,
            label=sensor_label,
        )
        await execute(
            """
            INSERT INTO telemetry_last (sensor_id, last_value, last_ts, last_quality, updated_at)
            VALUES ($1, $2, NOW(), 'GOOD', NOW())
            """,
            sensor_id,
            5.8 if sensor_type == "PH" else 1.4,
        )
        await execute(
            """
            INSERT INTO telemetry_samples (sensor_id, zone_id, ts, value, quality, created_at)
            VALUES
                ($1, $2, NOW() - INTERVAL '4 seconds', $3, 'GOOD', NOW()),
                ($1, $2, NOW() - INTERVAL '2 seconds', $3, 'GOOD', NOW()),
                ($1, $2, NOW(), $3, 'GOOD', NOW())
            """,
            sensor_id,
            zone_id,
            5.8 if sensor_type == "PH" else 1.4,
        )
        pid_patch[node_type] = {
            "config": {
                "kp": 1.2 if node_type == "ph" else 1.5,
                "ki": 0.4 if node_type == "ph" else 0.3,
                "kd": 0.1 if node_type == "ph" else 0.0,
            }
        }
    await _upsert_zone_bundle(zone_id, {"pid": pid_patch})


async def _insert_two_tank_runtime_zone(prefix: str, *, clean_full: bool, solution_full: bool) -> tuple[int, int]:
    greenhouse_id = await _insert_greenhouse(prefix)
    zone_id = await _insert_zone(f"{prefix}-zone", greenhouse_id=greenhouse_id)
    _, recipe_revision_id = await _insert_recipe_revision(prefix)
    grow_cycle_id = await _insert_grow_cycle(zone_id, greenhouse_id=greenhouse_id, recipe_revision_id=recipe_revision_id)
    phase_id = await _insert_phase(grow_cycle_id, ph_target=5.8)
    await execute(
        """
        UPDATE grow_cycles
        SET current_phase_id = $2,
            started_at = NOW(),
            recipe_started_at = NOW(),
            updated_at = NOW()
        WHERE id = $1
        """,
        grow_cycle_id,
        phase_id,
    )
    await _insert_profile(zone_id)
    node_id, _node_uid = await _insert_irrig_node(zone_id, prefix=prefix)
    sensor_rows = (
        ("level_clean_min", 1.0 if clean_full else 0.0),
        ("level_clean_max", 1.0 if clean_full else 0.0),
        ("level_solution_min", 1.0 if solution_full else 0.0),
        ("level_solution_max", 1.0 if solution_full else 0.0),
    )
    for label, value in sensor_rows:
        sensor_id = await _insert_sensor(
            greenhouse_id=greenhouse_id,
            zone_id=zone_id,
            node_id=node_id,
            sensor_type="WATER_LEVEL",
            label=label,
        )
        await execute(
            """
            INSERT INTO telemetry_last (sensor_id, last_value, last_ts, last_quality, updated_at)
            VALUES ($1, $2, NOW(), 'GOOD', NOW())
            """,
            sensor_id,
            value,
        )
    for channel in (
        "valve_clean_fill",
        "valve_clean_supply",
        "valve_solution_fill",
        "valve_solution_supply",
        "pump_main",
        "valve_irrigation",
    ):
        rows = await fetch(
            """
            INSERT INTO node_channels (node_id, channel, type, config, created_at, updated_at)
            VALUES ($1, $2, 'ACTUATOR', '{}'::jsonb, NOW(), NOW())
            RETURNING id
            """,
            node_id,
            channel,
        )
        if channel == "pump_main":
            rows2 = await fetch(
                """
                INSERT INTO infrastructure_instances (owner_type, owner_id, asset_type, label, required, created_at, updated_at)
                VALUES ('zone', $1, 'PUMP', 'Main Pump', TRUE, NOW(), NOW())
                RETURNING id
                """,
                zone_id,
            )
            await execute(
                """
                INSERT INTO channel_bindings (infrastructure_instance_id, node_channel_id, direction, role, created_at, updated_at)
                VALUES ($1, $2, 'actuator', 'pump_main', NOW(), NOW())
                """,
                int(rows2[0]["id"]),
                int(rows[0]["id"]),
            )
    await _insert_ph_ec_support_nodes(zone_id=zone_id, greenhouse_id=greenhouse_id)
    await _insert_correction_config(zone_id)
    await _insert_process_calibrations(zone_id)
    return greenhouse_id, zone_id


async def _insert_correction_config(zone_id: int) -> None:
    """Insert a complete authority correction bundle fixture for fail-closed runtime validation."""
    minimal_cfg = {
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
                "prepare_recirculation_max_attempts": 3,
                "prepare_recirculation_max_correction_attempts": 20,
                "prepare_recirculation_correction_slack_sec": 0,
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
    await _upsert_zone_bundle(
        zone_id,
        {
            "correction": {
                "phase_overrides": {},
                "resolved_config": minimal_cfg,
            }
        },
    )


async def _insert_pending_task(zone_id: int, *, prefix: str) -> int:
    rows = await fetch(
        """
        INSERT INTO ae_tasks (
            zone_id,
            task_type,
            status,
            idempotency_key,
            scheduled_for,
            due_at,
            created_at,
            updated_at,
            topology,
            current_stage,
            workflow_phase
        )
        VALUES (
            $1,
            'cycle_start',
            'pending',
            $2,
            NOW() - INTERVAL '1 second',
            NOW() - INTERVAL '1 second',
            NOW(),
            NOW(),
            'two_tank',
            'startup',
            'idle'
        )
        RETURNING id
        """,
        zone_id,
        f"{prefix}-task",
    )
    return int(rows[0]["id"])


def _build_worker(*, zone_id: int, clean_full: bool, solution_full: bool) -> Ae3RuntimeWorker:
    task_repository = PgAutomationTaskRepository()
    lease_repository = PgZoneLeaseRepository()
    command_repository = PgAeCommandRepository()
    workflow_repository = PgZoneWorkflowRepository()
    gateway = SequentialCommandGateway(
        task_repository=task_repository,
        command_repository=command_repository,
        history_logger_client=_TwoTankHistoryLoggerStub(
            zone_id=zone_id,
            initial_state={
                "pump_main": False,
                "valve_clean_fill": False,
                "valve_clean_supply": False,
                "valve_solution_fill": False,
                "valve_solution_supply": False,
                "valve_irrigation": True,
                "clean_level_min": clean_full,
                "clean_level_max": clean_full,
                "solution_level_min": solution_full,
                "solution_level_max": solution_full,
            },
        ),
        poll_interval_sec=0.01,
    )
    execute_use_case = ExecuteTaskUseCase(
        task_repository=task_repository,
        zone_snapshot_read_model=PgZoneSnapshotReadModel(),
        planner=CycleStartPlanner(),
        command_gateway=gateway,
        workflow_router=WorkflowRouter(
            task_repository=task_repository,
            workflow_repository=workflow_repository,
            topology_registry=TopologyRegistry(),
            runtime_monitor=PgZoneRuntimeMonitor(),
            command_gateway=gateway,
        ),
    )

    async def _noop(**kwargs):
        return None

    return Ae3RuntimeWorker(
        owner="ae3-two-tank-test",
        claim_next_task_use_case=ClaimNextTaskUseCase(
            task_repository=task_repository,
            zone_lease_repository=lease_repository,
            lease_ttl_sec=120,
        ),
        idle_poll_interval_sec=0.05,
        execute_task_use_case=execute_use_case,
        startup_recovery_use_case=StartupRecoveryUseCase(
            task_repository=task_repository,
            lease_repository=lease_repository,
            command_gateway=gateway,
            workflow_repository=workflow_repository,
            topology_registry=TopologyRegistry(),
        ),
        zone_lease_repository=lease_repository,
        zone_intent_repository=type("IntentRepoStub", (), {
            "mark_running": staticmethod(_noop),
            "mark_terminal": staticmethod(_noop),
        })(),
        spawn_background_task_fn=lambda coro, **kwargs: asyncio.create_task(coro, name=str(kwargs.get("task_name") or "ae3-two-tank")),
        now_fn=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        logger=type("Logger", (), {"warning": staticmethod(lambda *args, **kwargs: None), "debug": staticmethod(lambda *args, **kwargs: None)})(),
    )


@pytest.mark.asyncio
async def test_two_tank_cycle_start_completes_when_clean_and_solution_tanks_ready() -> None:
    prefix = f"ae3-two-tank-ready-{uuid4().hex}"
    worker: Ae3RuntimeWorker | None = None
    try:
        _greenhouse_id, zone_id = await _insert_two_tank_runtime_zone(prefix, clean_full=True, solution_full=True)
        task_id = await _insert_pending_task(zone_id, prefix=prefix)
        worker = _build_worker(zone_id=zone_id, clean_full=True, solution_full=True)

        await worker._drain_pending_tasks()

        task_rows = await fetch("SELECT status FROM ae_tasks WHERE id = $1", task_id)
        workflow_rows = await fetch("SELECT workflow_phase FROM zone_workflow_state WHERE zone_id = $1", zone_id)
        command_rows = await fetch("SELECT COUNT(*) AS cnt FROM ae_commands WHERE task_id = $1", task_id)

        assert str(task_rows[0]["status"]).lower() == "completed"
        assert str(workflow_rows[0]["workflow_phase"]).lower() == "ready"
        assert int(command_rows[0]["cnt"]) >= 8
    finally:
        wake_task = getattr(worker, "_wake_task", None)
        if wake_task is not None and not wake_task.done():
            wake_task.cancel()
            with suppress(asyncio.CancelledError):
                await wake_task
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_two_tank_cycle_start_requeues_clean_fill_check_when_clean_tank_not_full() -> None:
    prefix = f"ae3-two-tank-refill-{uuid4().hex}"
    worker: Ae3RuntimeWorker | None = None
    try:
        _greenhouse_id, zone_id = await _insert_two_tank_runtime_zone(prefix, clean_full=False, solution_full=False)
        task_id = await _insert_pending_task(zone_id, prefix=prefix)
        worker = _build_worker(zone_id=zone_id, clean_full=False, solution_full=False)

        await worker._drain_pending_tasks()

        rows = await fetch("SELECT status, current_stage FROM ae_tasks WHERE id = $1", task_id)
        workflow_rows = await fetch("SELECT workflow_phase FROM zone_workflow_state WHERE zone_id = $1", zone_id)
        command_rows = await fetch("SELECT COUNT(*) AS cnt FROM ae_commands WHERE task_id = $1", task_id)

        assert str(rows[0]["status"]).lower() == "pending"
        assert rows[0]["current_stage"] == "clean_fill_check"
        assert str(workflow_rows[0]["workflow_phase"]).lower() == "tank_filling"
        assert int(command_rows[0]["cnt"]) >= 2
    finally:
        wake_task = getattr(worker, "_wake_task", None)
        if wake_task is not None and not wake_task.done():
            wake_task.cancel()
            with suppress(asyncio.CancelledError):
                await wake_task
        await _cleanup(prefix)
