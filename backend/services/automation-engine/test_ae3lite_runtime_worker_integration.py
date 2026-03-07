from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from ae3lite.application.dto import StartupRecoveryResult, StartupRecoveryTerminalOutcome
from ae3lite.application.use_cases import (
    ClaimNextTaskUseCase,
    ExecuteTaskUseCase,
    StartupRecoveryUseCase,
    WorkflowRouter,
)
from ae3lite.domain.services import CycleStartPlanner, TopologyRegistry
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
    _insert_irrig_node,
    _insert_phase,
    _insert_recipe_revision,
    _insert_sensor,
    _insert_zone,
)


class _HistoryLoggerClientStub:
    def __init__(self, *, terminal_status: str, error_message: str | None = None) -> None:
        self._terminal_status = terminal_status
        self._error_message = error_message

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
                failed_at,
                error_message,
                created_at,
                updated_at
            )
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, 'automation-engine', NOW(), NOW(), $7, NOW(), NOW())
            """,
            zone_id,
            channel,
            cmd,
            params,
            self._terminal_status,
            f"hl-{cmd_id}",
            self._error_message,
        )
        return f"hl-{cmd_id}"


async def _insert_pending_task(zone_id: int, *, prefix: str, now: datetime) -> int:
    normalized_now = now.replace(microsecond=0)
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
        VALUES ($1, 'cycle_start', 'pending', $2, $3, $3, $3, $3, 'generic_cycle_start', 'startup', 'idle')
        RETURNING id
        """,
        zone_id,
        f"{prefix}-task",
        normalized_now,
    )
    return int(rows[0]["id"])


async def _reset_runtime_tables() -> None:
    await execute("DELETE FROM ae_commands")
    await execute("DELETE FROM ae_zone_leases")
    await execute("DELETE FROM ae_tasks")
    await execute("DELETE FROM commands WHERE source = 'automation-engine'")


async def _insert_single_step_profile(zone_id: int) -> None:
    execution = {
        "workflow": "cycle_start",
        "topology": "generic_cycle_start",
        "required_node_types": ["irrig"],
    }
    await execute(
        """
        INSERT INTO zone_automation_logic_profiles (
            zone_id,
            mode,
            subsystems,
            command_plans,
            is_active,
            created_at,
            updated_at
        )
        VALUES (
            $1,
            'working',
            $2::jsonb,
            $3::jsonb,
            TRUE,
            NOW(),
            NOW()
        )
        """,
        zone_id,
        {"diagnostics": {"execution": execution}},
        {
            "schema_version": 1,
            "plan_version": 1,
            "plans": {
                "diagnostics": {
                    "steps": [
                        {
                            "name": "pump_start",
                            "channel": "irrigation_pump",
                            "cmd": "set_relay",
                            "params": {"state": True},
                        }
                    ]
                }
            },
        },
    )


async def _prepare_runtime_zone(prefix: str, now: datetime) -> tuple[int, int]:
    greenhouse_id = await _insert_greenhouse(prefix)
    zone_id = await _insert_zone(f"{prefix}-zone", greenhouse_id=greenhouse_id)
    _, recipe_revision_id = await _insert_recipe_revision(prefix)
    grow_cycle_id = await _insert_grow_cycle(zone_id, greenhouse_id=greenhouse_id, recipe_revision_id=recipe_revision_id)
    phase_id = await _insert_phase(grow_cycle_id, ph_target=5.8)
    await execute(
        """
        UPDATE grow_cycles
        SET current_phase_id = $2,
            started_at = $3,
            recipe_started_at = $3,
            updated_at = $3
        WHERE id = $1
        """,
        grow_cycle_id,
        phase_id,
        now,
    )
    await _insert_single_step_profile(zone_id)
    node_id, _node_uid = await _insert_irrig_node(zone_id, prefix=prefix)
    sensor_id = await _insert_sensor(
        greenhouse_id=greenhouse_id,
        zone_id=zone_id,
        node_id=node_id,
        sensor_type="WATER_LEVEL",
        label="level_clean_min",
    )
    await execute(
        """
        INSERT INTO telemetry_last (sensor_id, last_value, last_ts, last_quality, updated_at)
        VALUES ($1, 81.5, NOW(), 'GOOD', NOW())
        """,
        sensor_id,
    )
    rows = await fetch(
        """
        INSERT INTO node_channels (node_id, channel, type, config, created_at, updated_at)
        VALUES ($1, 'pump_main', 'ACTUATOR', '{}'::jsonb, NOW(), NOW())
        RETURNING id
        """,
        node_id,
    )
    node_channel_id = int(rows[0]["id"])
    rows = await fetch(
        """
        INSERT INTO infrastructure_instances (
            owner_type,
            owner_id,
            asset_type,
            label,
            required,
            created_at,
            updated_at
        )
        VALUES ('zone', $1, 'PUMP', 'Main Pump', TRUE, NOW(), NOW())
        RETURNING id
        """,
        zone_id,
    )
    asset_id = int(rows[0]["id"])
    await execute(
        """
        INSERT INTO channel_bindings (
            infrastructure_instance_id,
            node_channel_id,
            direction,
            role,
            created_at,
            updated_at
        )
        VALUES ($1, $2, 'actuator', 'irrigation_pump', NOW(), NOW())
        """,
        asset_id,
        node_channel_id,
    )
    return greenhouse_id, zone_id


def _build_worker(*, terminal_status: str, error_message: str | None = None) -> Ae3RuntimeWorker:
    task_repository = PgAutomationTaskRepository()
    lease_repository = PgZoneLeaseRepository()
    command_repository = PgAeCommandRepository()
    workflow_repository = PgZoneWorkflowRepository()
    command_gateway = SequentialCommandGateway(
        task_repository=task_repository,
        command_repository=command_repository,
        history_logger_client=_HistoryLoggerClientStub(terminal_status=terminal_status, error_message=error_message),
        poll_interval_sec=0.05,
    )
    execute_use_case = ExecuteTaskUseCase(
        task_repository=task_repository,
        zone_snapshot_read_model=PgZoneSnapshotReadModel(),
        planner=CycleStartPlanner(),
        command_gateway=command_gateway,
        workflow_router=WorkflowRouter(
            task_repository=task_repository,
            workflow_repository=workflow_repository,
            topology_registry=TopologyRegistry(),
            runtime_monitor=PgZoneRuntimeMonitor(),
            command_gateway=command_gateway,
        ),
    )
    async def _noop(**kwargs):
        return None

    return Ae3RuntimeWorker(
        owner="worker-ae3-test",
        claim_next_task_use_case=ClaimNextTaskUseCase(
            task_repository=task_repository,
            zone_lease_repository=lease_repository,
            lease_ttl_sec=120,
        ),
        execute_task_use_case=execute_use_case,
        startup_recovery_use_case=StartupRecoveryUseCase(
            task_repository=task_repository,
            lease_repository=lease_repository,
            reconcile_command_use_case=type("ReconcileNoop", (), {"run": staticmethod(_noop)})(),
            command_gateway=command_gateway,
            workflow_repository=workflow_repository,
            topology_registry=TopologyRegistry(),
        ),
        zone_lease_repository=lease_repository,
        spawn_background_task_fn=lambda coro, **kwargs: asyncio.create_task(coro, name=str(kwargs.get("task_name") or "ae3-test")),
        mark_intent_running_fn=_noop,
        mark_intent_terminal_fn=_noop,
        now_fn=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        logger=type("Logger", (), {"warning": staticmethod(lambda *args, **kwargs: None)})(),
    )


def _build_noop_worker(*, spawn_background_task_fn) -> Ae3RuntimeWorker:
    async def _noop_run(**kwargs):
        return None

    return Ae3RuntimeWorker(
        owner="worker-ae3-noop",
        claim_next_task_use_case=type("ClaimNextTaskUseCaseStub", (), {"run": staticmethod(_noop_run)})(),
        execute_task_use_case=type("ExecuteTaskUseCaseStub", (), {"run": staticmethod(_noop_run)})(),
        startup_recovery_use_case=type("StartupRecoveryUseCaseStub", (), {"run": staticmethod(_noop_run)})(),
        zone_lease_repository=type("ZoneLeaseRepositoryStub", (), {"release": staticmethod(_noop_run)})(),
        spawn_background_task_fn=spawn_background_task_fn,
        mark_intent_running_fn=_noop_run,
        mark_intent_terminal_fn=_noop_run,
        now_fn=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        logger=type("Logger", (), {"warning": staticmethod(lambda *args, **kwargs: None)})(),
    )


class _PendingTaskOnOtherLoop:
    def __init__(self) -> None:
        self._loop = object()

    def done(self) -> bool:
        return False

    def get_loop(self):
        return self._loop


@pytest.mark.asyncio
async def test_runtime_worker_claims_executes_and_completes_pending_task_on_done() -> None:
    prefix = f"ae3-worker-done-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        await _reset_runtime_tables()
        _greenhouse_id, zone_id = await _prepare_runtime_zone(prefix, now)
        task_id = await _insert_pending_task(zone_id, prefix=prefix, now=now)
        worker = _build_worker(terminal_status="DONE")

        await worker._drain_pending_tasks()

        rows = await fetch("SELECT status, completed_at FROM ae_tasks WHERE id = $1", task_id)
        assert str(rows[0]["status"]).lower() == "completed"
        assert rows[0]["completed_at"] is not None

        command_rows = await fetch("SELECT publish_status, terminal_status FROM ae_commands WHERE task_id = $1", task_id)
        assert len(command_rows) == 1
        assert command_rows[0]["publish_status"] == "accepted"
        assert command_rows[0]["terminal_status"] == "DONE"

        lease_rows = await fetch("SELECT zone_id FROM ae_zone_leases WHERE zone_id = $1", zone_id)
        assert lease_rows == []
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_runtime_worker_respawns_when_existing_drain_task_is_on_other_loop() -> None:
    spawned: list[asyncio.Task] = []

    def _spawn(coro, **kwargs):
        task = asyncio.create_task(coro, name=str(kwargs.get("task_name") or "ae3-test"))
        spawned.append(task)
        return task

    worker = _build_noop_worker(spawn_background_task_fn=_spawn)
    worker._drain_task = _PendingTaskOnOtherLoop()

    task = worker.kick()

    assert spawned == [task]
    await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_runtime_worker_respawns_when_kick_arrives_while_existing_drain_task_is_finishing() -> None:
    spawned: list[asyncio.Task] = []
    closing_gate = asyncio.Event()

    async def _closing_drain() -> None:
        await closing_gate.wait()

    def _spawn(coro, **kwargs):
        task = asyncio.create_task(coro, name=str(kwargs.get("task_name") or "ae3-test"))
        spawned.append(task)
        return task

    worker = _build_noop_worker(spawn_background_task_fn=_spawn)
    existing_task = asyncio.create_task(_closing_drain(), name="ae3-existing-drain")
    worker._drain_task = existing_task

    returned = worker.kick()

    assert returned is existing_task
    assert spawned == []

    closing_gate.set()
    await asyncio.wait_for(existing_task, timeout=1.0)

    for _ in range(20):
        if spawned:
            break
        await asyncio.sleep(0)

    assert len(spawned) == 1
    await asyncio.wait_for(spawned[0], timeout=1.0)


@pytest.mark.asyncio
async def test_runtime_worker_marks_terminal_intents_discovered_during_startup_recovery() -> None:
    terminal_calls: list[dict[str, object]] = []
    fixed_now = datetime(2026, 3, 6, 12, 0, 0)

    async def _noop_run(**kwargs):
        return None

    async def _recovery_run(**kwargs):
        return StartupRecoveryResult(
            released_expired_leases=0,
            scanned_tasks=2,
            completed_tasks=1,
            failed_tasks=1,
            waiting_command_tasks=0,
            recovered_waiting_command_tasks=0,
            terminal_outcomes=(
                StartupRecoveryTerminalOutcome(
                    task_id=101,
                    intent_id=901,
                    success=True,
                    error_code=None,
                    error_message=None,
                ),
                StartupRecoveryTerminalOutcome(
                    task_id=102,
                    intent_id=902,
                    success=False,
                    error_code="command_timeout",
                    error_message="restart_timeout",
                ),
            ),
        )

    async def _mark_terminal(**kwargs):
        terminal_calls.append(dict(kwargs))

    worker = Ae3RuntimeWorker(
        owner="worker-ae3-recovery",
        claim_next_task_use_case=type("ClaimNextTaskUseCaseStub", (), {"run": staticmethod(_noop_run)})(),
        execute_task_use_case=type("ExecuteTaskUseCaseStub", (), {"run": staticmethod(_noop_run)})(),
        startup_recovery_use_case=type("StartupRecoveryUseCaseStub", (), {"run": staticmethod(_recovery_run)})(),
        zone_lease_repository=type("ZoneLeaseRepositoryStub", (), {"release": staticmethod(_noop_run)})(),
        spawn_background_task_fn=lambda coro, **kwargs: asyncio.create_task(coro, name=str(kwargs.get("task_name") or "ae3-test")),
        mark_intent_running_fn=_noop_run,
        mark_intent_terminal_fn=_mark_terminal,
        now_fn=lambda: fixed_now,
        logger=type("Logger", (), {"warning": staticmethod(lambda *args, **kwargs: None)})(),
    )

    result = await worker.recover_on_startup()

    assert result.scanned_tasks == 2
    assert terminal_calls == [
        {
            "intent_id": 901,
            "now": fixed_now,
            "success": True,
            "error_code": None,
            "error_message": None,
        },
        {
            "intent_id": 902,
            "now": fixed_now,
            "success": False,
            "error_code": "command_timeout",
            "error_message": "restart_timeout",
        },
    ]


@pytest.mark.asyncio
async def test_runtime_worker_fails_pending_task_on_timeout_terminal() -> None:
    prefix = f"ae3-worker-timeout-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        await _reset_runtime_tables()
        _greenhouse_id, zone_id = await _prepare_runtime_zone(prefix, now)
        task_id = await _insert_pending_task(zone_id, prefix=prefix, now=now)
        worker = _build_worker(terminal_status="TIMEOUT", error_message="closed_loop_timeout")

        await worker._drain_pending_tasks()

        rows = await fetch("SELECT status, error_code, error_message FROM ae_tasks WHERE id = $1", task_id)
        assert str(rows[0]["status"]).lower() == "failed"
        assert rows[0]["error_code"] == "command_timeout"
        assert "closed_loop_timeout" in str(rows[0]["error_message"])
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_runtime_worker_survives_cleanup_race_after_publish() -> None:
    prefix = f"ae3-worker-cleanup-race-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cleaned_up = False

    try:
        await _reset_runtime_tables()
        _greenhouse_id, zone_id = await _prepare_runtime_zone(prefix, now)
        task_id = await _insert_pending_task(zone_id, prefix=prefix, now=now)
        worker = _build_worker(terminal_status="ACK")

        drain_task = asyncio.create_task(worker._drain_pending_tasks())

        for _ in range(100):
            rows = await fetch("SELECT status FROM ae_tasks WHERE id = $1", task_id)
            if rows and str(rows[0]["status"]).lower() == "waiting_command":
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("Task did not reach waiting_command before cleanup")

        await _cleanup(prefix)
        cleaned_up = True

        await asyncio.wait_for(drain_task, timeout=5.0)

        lease_rows = await fetch("SELECT zone_id FROM ae_zone_leases WHERE zone_id = $1", zone_id)
        assert lease_rows == []
        assert drain_task.exception() is None
    finally:
        if not cleaned_up:
            await _cleanup(prefix)
