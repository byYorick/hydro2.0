from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ae3lite.application.dto import StartupRecoveryResult, StartupRecoveryTerminalOutcome
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.application.use_cases import (
    ClaimNextTaskUseCase,
    ExecuteTaskUseCase,
    StartupRecoveryUseCase,
    WorkflowRouter,
)
from ae3lite.application.use_cases.execute_task import (
    TASK_EXECUTION_LEASE_LOST_CANCEL_MSG,
    TASK_EXECUTION_TIMEOUT_CANCEL_MSG,
)
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


class _MockIntentRepository:
    """Minimal intent repository stub for worker tests."""

    def __init__(self, *, mark_terminal_calls: list | None = None) -> None:
        self._mark_terminal_calls = mark_terminal_calls

    async def mark_running(self, *, intent_id: int, now: datetime) -> None:
        pass

    async def mark_terminal(
        self,
        *,
        intent_id: int,
        now: datetime,
        success: bool,
        error_code: object,
        error_message: object,
    ) -> None:
        if self._mark_terminal_calls is not None:
            self._mark_terminal_calls.append(
                {
                    "intent_id": intent_id,
                    "now": now,
                    "success": success,
                    "error_code": error_code,
                    "error_message": error_message,
                }
            )
from test_ae3lite_zone_snapshot_read_model_integration import (
    _cleanup,
    _insert_greenhouse,
    _insert_grow_cycle,
    _insert_irrig_node,
    _insert_phase,
    _insert_recipe_revision,
    _insert_sensor,
    _insert_zone,
    _upsert_zone_bundle,
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


async def _insert_pending_task(
    zone_id: int,
    *,
    prefix: str,
    now: datetime,
    due_at: datetime | None = None,
) -> int:
    normalized_now = now.replace(microsecond=0)
    normalized_due_at = (due_at or now).replace(microsecond=0)
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
        VALUES ($1, 'cycle_start', 'pending', $2, $3, $4, $3, $3, 'generic_cycle_start', 'startup', 'idle')
        RETURNING id
        """,
        zone_id,
        f"{prefix}-task",
        normalized_now,
        normalized_due_at,
    )
    return int(rows[0]["id"])


async def _reset_runtime_tables() -> None:
    """Deprecated global cleanup helper kept for backward compatibility."""
    return None


async def _insert_single_step_profile(zone_id: int) -> None:
    execution = {
        "workflow": "cycle_start",
        "topology": "generic_cycle_start",
        "required_node_types": ["irrig"],
    }
    await _upsert_zone_bundle(
        zone_id,
        {
            "logic_profile": {
                "active_mode": "working",
                "active_profile": {
                    "mode": "working",
                    "updated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                    "subsystems": {"diagnostics": {"execution": execution}},
                    "command_plans": {
                        "schema_version": 1,
                        "plan_version": 1,
                        "plans": {
                            "diagnostics": {
                                "steps": [
                                    {
                                        "name": "pump_start",
                                        "channel": "pump_main",
                                        "cmd": "set_relay",
                                        "params": {"state": True},
                                    }
                                ]
                            }
                        },
                    },
                },
            }
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
        VALUES ($1, $2, 'actuator', 'pump_main', NOW(), NOW())
        """,
        asset_id,
        node_channel_id,
    )
    return greenhouse_id, zone_id


class _DeleteTaskBeforeFirstAeInsertRepo(PgAeCommandRepository):
    """Simulates concurrent cleanup: ae_tasks removed immediately before first ae_commands INSERT."""

    def __init__(self) -> None:
        super().__init__()
        self._armed = True

    async def create_pending(  # type: ignore[override]
        self,
        *,
        task_id: int,
        step_no: int,
        node_uid: str,
        channel: str,
        payload,
        now: datetime,
        stage_name=None,
    ):
        if self._armed:
            self._armed = False
            await execute("DELETE FROM ae_tasks WHERE id = $1", task_id)
        return await super().create_pending(
            task_id=task_id,
            step_no=step_no,
            node_uid=node_uid,
            channel=channel,
            payload=payload,
            now=now,
            stage_name=stage_name,
        )


def _build_worker(
    *,
    terminal_status: str,
    error_message: str | None = None,
    command_repository: PgAeCommandRepository | None = None,
) -> Ae3RuntimeWorker:
    task_repository = PgAutomationTaskRepository()
    lease_repository = PgZoneLeaseRepository()
    command_repository = command_repository or PgAeCommandRepository()
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

    return Ae3RuntimeWorker(
        owner="worker-ae3-test",
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
            command_gateway=command_gateway,
            workflow_repository=workflow_repository,
            topology_registry=TopologyRegistry(),
        ),
        zone_lease_repository=lease_repository,
        zone_intent_repository=_MockIntentRepository(),
        spawn_background_task_fn=lambda coro, **kwargs: asyncio.create_task(coro, name=str(kwargs.get("task_name") or "ae3-test")),
        now_fn=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        logger=type("Logger", (), {"warning": staticmethod(lambda *args, **kwargs: None)})(),
    )


def _build_noop_worker(*, spawn_background_task_fn) -> Ae3RuntimeWorker:
    async def _noop_run(**kwargs):
        return None

    return Ae3RuntimeWorker(
        owner="worker-ae3-noop",
        claim_next_task_use_case=type("ClaimNextTaskUseCaseStub", (), {"run": staticmethod(_noop_run)})(),
        idle_poll_interval_sec=0.05,
        execute_task_use_case=type("ExecuteTaskUseCaseStub", (), {"run": staticmethod(_noop_run)})(),
        startup_recovery_use_case=type("StartupRecoveryUseCaseStub", (), {"run": staticmethod(_noop_run)})(),
        zone_lease_repository=type("ZoneLeaseRepositoryStub", (), {"release": staticmethod(_noop_run)})(),
        zone_intent_repository=_MockIntentRepository(),
        spawn_background_task_fn=spawn_background_task_fn,
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
        idle_poll_interval_sec=0.1,
        execute_task_use_case=type("ExecuteTaskUseCaseStub", (), {"run": staticmethod(_noop_run)})(),
        startup_recovery_use_case=type("StartupRecoveryUseCaseStub", (), {"run": staticmethod(_recovery_run)})(),
        zone_lease_repository=type("ZoneLeaseRepositoryStub", (), {"release": staticmethod(_noop_run)})(),
        zone_intent_repository=_MockIntentRepository(mark_terminal_calls=terminal_calls),
        spawn_background_task_fn=lambda coro, **kwargs: asyncio.create_task(coro, name=str(kwargs.get("task_name") or "ae3-test")),
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
async def test_runtime_worker_wakes_itself_for_delayed_pending_task() -> None:
    prefix = f"ae3-worker-delayed-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    worker: Ae3RuntimeWorker | None = None

    try:
        _greenhouse_id, zone_id = await _prepare_runtime_zone(prefix, now)
        task_id = await _insert_pending_task(
            zone_id,
            prefix=prefix,
            now=now,
            due_at=now + timedelta(seconds=1),
        )
        worker = _build_worker(terminal_status="DONE")

        worker.kick()

        for _ in range(80):
            rows = await fetch(
                "SELECT status, completed_at FROM ae_tasks WHERE id = $1",
                task_id,
            )
            if rows and str(rows[0]["status"]).lower() == "completed":
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("Delayed pending task did not complete without an extra kick")

        lease_rows = await fetch(
            "SELECT zone_id FROM ae_zone_leases WHERE zone_id = $1",
            zone_id,
        )
        assert lease_rows == []
    finally:
        wake_task = getattr(worker, "_wake_task", None)
        if wake_task is not None and not wake_task.done():
            wake_task.cancel()
            with suppress(asyncio.CancelledError):
                await wake_task
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_runtime_worker_survives_task_delete_before_ae_command_insert() -> None:
    """Regression: FK failure on ae_commands insert must not crash the worker loop."""
    prefix = f"ae3-worker-preinsert-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        _greenhouse_id, zone_id = await _prepare_runtime_zone(prefix, now)
        task_id = await _insert_pending_task(zone_id, prefix=prefix, now=now)
        worker = _build_worker(
            terminal_status="DONE",
            command_repository=_DeleteTaskBeforeFirstAeInsertRepo(),
        )

        drain_task = asyncio.create_task(worker._drain_pending_tasks())

        await asyncio.wait_for(drain_task, timeout=10.0)

        lease_rows = await fetch("SELECT zone_id FROM ae_zone_leases WHERE zone_id = $1", zone_id)
        assert lease_rows == []
        assert drain_task.exception() is None

        gone = await fetch("SELECT id FROM ae_tasks WHERE id = $1", task_id)
        assert gone == []
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_runtime_worker_survives_cleanup_race_after_publish() -> None:
    prefix = f"ae3-worker-cleanup-race-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cleaned_up = False

    try:
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


@pytest.mark.asyncio
async def test_runtime_worker_timeout_cancels_execution_with_timeout_reason_and_marks_intent_failed() -> None:
    cancel_args: list[tuple[object, ...]] = []
    terminal_calls: list[dict[str, object]] = []
    released: list[tuple[int, str]] = []

    task = SimpleNamespace(
        id=701,
        zone_id=81,
        topology="generic_cycle_start",
        intent_id=991,
        status="claimed",
        error_code=None,
        error_message=None,
        is_active=True,
    )

    class _ClaimOnce:
        def __init__(self) -> None:
            self._used = False

        async def run(self, **kwargs):
            if self._used:
                return None
            self._used = True
            return task, None

    class _ExecuteTimeoutAware:
        async def run(self, *, task, now):
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError as exc:
                cancel_args.append(exc.args)
                return SimpleNamespace(
                    id=task.id,
                    zone_id=task.zone_id,
                    topology=task.topology,
                    intent_id=task.intent_id,
                    status="failed",
                    error_code=TASK_EXECUTION_TIMEOUT_CANCEL_MSG,
                    error_message="Task execution exceeded runtime timeout",
                    is_active=False,
                )

    async def _release(*, zone_id, owner):
        released.append((zone_id, owner))
        return True

    async def _noop(**kwargs):
        return None

    async def _mark_terminal(**kwargs):
        terminal_calls.append(dict(kwargs))

    worker = Ae3RuntimeWorker(
        owner="worker-timeout-test",
        claim_next_task_use_case=_ClaimOnce(),
        idle_poll_interval_sec=0.05,
        execute_task_use_case=_ExecuteTimeoutAware(),
        startup_recovery_use_case=type("StartupRecoveryUseCaseStub", (), {"run": staticmethod(_noop)})(),
        zone_lease_repository=type("ZoneLeaseRepositoryStub", (), {"release": staticmethod(_release)})(),
        zone_intent_repository=_MockIntentRepository(mark_terminal_calls=terminal_calls),
        spawn_background_task_fn=lambda coro, **kwargs: asyncio.create_task(coro, name=str(kwargs.get("task_name") or "ae3-test")),
        now_fn=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        logger=type(
            "Logger",
            (),
            {
                "debug": staticmethod(lambda *args, **kwargs: None),
                "warning": staticmethod(lambda *args, **kwargs: None),
                "error": staticmethod(lambda *args, **kwargs: None),
            },
        )(),
        max_task_execution_sec=0.01,
    )

    await worker._drain_pending_tasks()

    assert cancel_args == [(TASK_EXECUTION_TIMEOUT_CANCEL_MSG,)]
    assert released == [(81, "worker-timeout-test")]
    assert len(terminal_calls) == 1
    assert terminal_calls[0]["intent_id"] == 991
    assert terminal_calls[0]["success"] is False
    assert terminal_calls[0]["error_code"] == TASK_EXECUTION_TIMEOUT_CANCEL_MSG
    assert terminal_calls[0]["error_message"] == "Task execution exceeded runtime timeout"


@pytest.mark.asyncio
async def test_runtime_worker_continues_draining_after_timeout_without_extra_kick() -> None:
    terminal_calls: list[dict[str, object]] = []
    released: list[tuple[int, str]] = []
    executed_task_ids: list[int] = []

    timed_out_task = SimpleNamespace(
        id=801,
        zone_id=91,
        topology="generic_cycle_start",
        intent_id=1991,
        status="claimed",
        error_code=None,
        error_message=None,
        is_active=True,
    )
    completed_task = SimpleNamespace(
        id=802,
        zone_id=92,
        topology="generic_cycle_start",
        intent_id=0,
        status="claimed",
        error_code=None,
        error_message=None,
        is_active=True,
    )

    class _ClaimSequence:
        def __init__(self) -> None:
            self._items = [timed_out_task, completed_task]

        async def run(self, **kwargs):
            if not self._items:
                return None
            return self._items.pop(0), None

    class _ExecuteSequence:
        async def run(self, *, task, now):
            executed_task_ids.append(int(task.id))
            if int(task.id) == timed_out_task.id:
                try:
                    await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    return SimpleNamespace(
                        id=task.id,
                        zone_id=task.zone_id,
                        topology=task.topology,
                        intent_id=task.intent_id,
                        status="failed",
                        error_code=TASK_EXECUTION_TIMEOUT_CANCEL_MSG,
                        error_message="Task execution exceeded runtime timeout",
                        is_active=False,
                    )
            return SimpleNamespace(
                id=task.id,
                zone_id=task.zone_id,
                topology=task.topology,
                intent_id=task.intent_id,
                status="completed",
                error_code=None,
                error_message=None,
                is_active=False,
            )

    async def _release(*, zone_id, owner):
        released.append((zone_id, owner))
        return True

    async def _noop(**kwargs):
        return None

    async def _mark_terminal(**kwargs):
        terminal_calls.append(dict(kwargs))

    worker = Ae3RuntimeWorker(
        owner="worker-timeout-continue-test",
        claim_next_task_use_case=_ClaimSequence(),
        idle_poll_interval_sec=0.05,
        execute_task_use_case=_ExecuteSequence(),
        startup_recovery_use_case=type("StartupRecoveryUseCaseStub", (), {"run": staticmethod(_noop)})(),
        zone_lease_repository=type("ZoneLeaseRepositoryStub", (), {"release": staticmethod(_release)})(),
        zone_intent_repository=_MockIntentRepository(mark_terminal_calls=terminal_calls),
        spawn_background_task_fn=lambda coro, **kwargs: asyncio.create_task(coro, name=str(kwargs.get("task_name") or "ae3-test")),
        now_fn=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        logger=type(
            "Logger",
            (),
            {
                "debug": staticmethod(lambda *args, **kwargs: None),
                "warning": staticmethod(lambda *args, **kwargs: None),
                "error": staticmethod(lambda *args, **kwargs: None),
            },
        )(),
        max_task_execution_sec=0.01,
    )

    await worker._drain_pending_tasks()

    assert executed_task_ids == [801, 802]
    assert released == [
        (91, "worker-timeout-continue-test"),
        (92, "worker-timeout-continue-test"),
    ]
    assert len(terminal_calls) == 1
    assert terminal_calls[0]["intent_id"] == 1991
    assert worker.drain_health() == (True, "idle")


@pytest.mark.asyncio
async def test_runtime_worker_cancels_execution_when_lease_is_lost() -> None:
    cancel_args: list[tuple[object, ...]] = []
    terminal_calls: list[dict[str, object]] = []
    released: list[tuple[int, str]] = []

    task = SimpleNamespace(
        id=851,
        zone_id=95,
        topology="generic_cycle_start",
        intent_id=2991,
        status="claimed",
        error_code=None,
        error_message=None,
        is_active=True,
    )

    class _ClaimOnce:
        def __init__(self) -> None:
            self._used = False

        async def run(self, **kwargs):
            if self._used:
                return None
            self._used = True
            return task, None

    class _ExecuteLeaseAware:
        async def run(self, *, task, now):
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError as exc:
                cancel_args.append(exc.args)
                return SimpleNamespace(
                    id=task.id,
                    zone_id=task.zone_id,
                    topology=task.topology,
                    intent_id=task.intent_id,
                    status="failed",
                    error_code=TASK_EXECUTION_LEASE_LOST_CANCEL_MSG,
                    error_message="Zone lease was lost during task execution",
                    is_active=False,
                )

    async def _release(*, zone_id, owner):
        released.append((zone_id, owner))
        return True

    async def _noop(**kwargs):
        return None

    worker = Ae3RuntimeWorker(
        owner="worker-lease-lost-test",
        claim_next_task_use_case=_ClaimOnce(),
        idle_poll_interval_sec=0.05,
        execute_task_use_case=_ExecuteLeaseAware(),
        startup_recovery_use_case=type("StartupRecoveryUseCaseStub", (), {"run": staticmethod(_noop)})(),
        zone_lease_repository=type("ZoneLeaseRepositoryStub", (), {"release": staticmethod(_release)})(),
        zone_intent_repository=_MockIntentRepository(mark_terminal_calls=terminal_calls),
        spawn_background_task_fn=lambda coro, **kwargs: asyncio.create_task(coro, name=str(kwargs.get("task_name") or "ae3-test")),
        now_fn=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        logger=type(
            "Logger",
            (),
            {
                "debug": staticmethod(lambda *args, **kwargs: None),
                "warning": staticmethod(lambda *args, **kwargs: None),
                "error": staticmethod(lambda *args, **kwargs: None),
            },
        )(),
        max_task_execution_sec=5.0,
    )

    async def _force_lease_loss(*, zone_id, lease_lost_event):
        lease_lost_event.set()

    worker._lease_heartbeat = _force_lease_loss  # type: ignore[method-assign]

    await worker._drain_pending_tasks()

    assert cancel_args == [(TASK_EXECUTION_LEASE_LOST_CANCEL_MSG,)]
    assert released == [(95, "worker-lease-lost-test")]
    assert len(terminal_calls) == 1
    assert terminal_calls[0]["intent_id"] == 2991
    assert terminal_calls[0]["error_code"] == TASK_EXECUTION_LEASE_LOST_CANCEL_MSG


@pytest.mark.asyncio
async def test_runtime_worker_does_not_warn_when_lease_was_already_removed_during_cleanup() -> None:
    warnings: list[tuple] = []
    debug_messages: list[tuple] = []
    resolved_calls: list[dict[str, object]] = []

    task = SimpleNamespace(
        id=901,
        zone_id=191,
        topology="generic_cycle_start",
        intent_id=0,
        status="claimed",
        error_code=None,
        error_message=None,
        is_active=True,
    )

    class _ClaimOnce:
        def __init__(self) -> None:
            self._used = False

        async def run(self, **kwargs):
            if self._used:
                return None
            self._used = True
            return task, None

    class _ExecuteImmediateDone:
        async def run(self, *, task, now):
            return SimpleNamespace(
                id=task.id,
                zone_id=task.zone_id,
                topology=task.topology,
                intent_id=task.intent_id,
                status="completed",
                error_code=None,
                error_message=None,
                is_active=False,
            )

    class _ZoneLeaseRepoMissingAfterRelease:
        async def release(self, *, zone_id, owner):
            return False

        async def get(self, *, zone_id):
            return None

    async def _noop(**kwargs):
        return None

    async def _record_resolved_alert(**kwargs):
        resolved_calls.append(kwargs)
        return True

    import ae3lite.runtime.worker as worker_module

    original_resolved = worker_module.send_infra_resolved_alert
    worker_module.send_infra_resolved_alert = _record_resolved_alert
    try:
        worker = Ae3RuntimeWorker(
            owner="worker-lease-cleanup-test",
            claim_next_task_use_case=_ClaimOnce(),
            idle_poll_interval_sec=0.05,
            execute_task_use_case=_ExecuteImmediateDone(),
            startup_recovery_use_case=type("StartupRecoveryUseCaseStub", (), {"run": staticmethod(_noop)})(),
            zone_lease_repository=_ZoneLeaseRepoMissingAfterRelease(),
            zone_intent_repository=_MockIntentRepository(mark_terminal_calls=[]),
            spawn_background_task_fn=lambda coro, **kwargs: asyncio.create_task(coro, name=str(kwargs.get("task_name") or "ae3-test")),
            now_fn=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
            logger=type(
                "Logger",
                (),
                {
                    "debug": staticmethod(lambda *args, **kwargs: debug_messages.append(args)),
                    "warning": staticmethod(lambda *args, **kwargs: warnings.append(args)),
                    "error": staticmethod(lambda *args, **kwargs: None),
                },
            )(),
            max_task_execution_sec=0.5,
        )

        await worker._drain_pending_tasks()
    finally:
        worker_module.send_infra_resolved_alert = original_resolved

    assert warnings == []
    assert any("lease already absent during release" in str(args[0]) for args in debug_messages)
    assert len(resolved_calls) == 1
    assert resolved_calls[0]["code"] == "ae3_zone_lease_release_failed"
    assert resolved_calls[0]["zone_id"] == 191


@pytest.mark.asyncio
async def test_runtime_worker_health_reports_unexpected_clean_exit() -> None:
    worker = _build_noop_worker(
        spawn_background_task_fn=lambda coro, **kwargs: asyncio.create_task(coro, name=str(kwargs.get("task_name") or "ae3-test")),
    )
    done_task = asyncio.create_task(asyncio.sleep(0), name="ae3-done-drain")

    await done_task

    worker._drain_task = done_task
    worker._last_drain_exit_ok = False
    worker._last_drain_exit_reason = "worker_unexpected_exit"

    assert worker.drain_health() == (False, "worker_unexpected_exit")
