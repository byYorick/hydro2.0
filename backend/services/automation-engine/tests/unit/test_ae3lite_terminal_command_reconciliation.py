from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ae3lite.application.use_cases import startup_recovery as recovery_module
from ae3lite.application.use_cases.startup_recovery import StartupRecoveryUseCase
from ae3lite.infrastructure.gateways import SequentialCommandGateway
from ae3lite.infrastructure.repositories import (
    PgAeCommandRepository,
    PgAutomationTaskRepository,
    PgPidStateRepository,
)
from common.db import execute, fetch


NOW = datetime(2026, 10, 12, 12, 0, 0)


class _TaskRepository:
    def __init__(self, task):
        self.task = task

    async def get_by_id(self, *, task_id):
        assert task_id == self.task.id
        return self.task


class _CommandRepository:
    def __init__(self, rows):
        self.rows = rows
        self.marked: list[int] = []

    async def list_unreconciled_for_terminal_tasks(self, *, limit):
        assert limit == 100
        return list(self.rows)

    async def mark_dose_accounted(self, *, ae_command_id, now):
        self.marked.append(int(ae_command_id))
        return True


class _Gateway:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def reconcile_terminal_task_command(self, **kwargs):
        self.calls.append(kwargs)
        return dict(self.result)


class _PidRepository:
    def __init__(self):
        self.calls = []

    async def reconcile_completed_dose(self, **kwargs):
        self.calls.append(kwargs)
        return True


class _AlertRepository:
    def __init__(self):
        self.calls = []

    async def raise_active(self, **kwargs):
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_periodic_worker_repairs_late_done_without_rerunning_startup(monkeypatch):
    from unittest.mock import AsyncMock
    from ae3lite.runtime.worker import Ae3RuntimeWorker

    monkeypatch.setattr(recovery_module, "create_zone_event", AsyncMock())
    task = SimpleNamespace(id=32, zone_id=3, status="failed", current_stage="irrigation_check",
                           task_type="irrigation_start", topology="two_tank", correction=None)
    command = {"id": 901, "task_id": 32, "channel": "pump_b", "payload": {
        "cmd": "dose", "params": {"duration_ms": 2000},
        "_ae3_dose_context": {"pid_type": "ec", "last_correction_kind": "ec", "hold_sec": 90},
    }}
    gateway = _Gateway({"state": "waiting_command"})
    commands = _CommandRepository([command])
    pid = _PidRepository()
    recovery = StartupRecoveryUseCase(
        task_repository=_TaskRepository(task), lease_repository=SimpleNamespace(),
        command_gateway=gateway, command_repository=commands, pid_state_repository=pid,
        use_startup_recovery_lock=False,
    )
    recovery.run = AsyncMock(side_effect=AssertionError("active startup recovery must not repeat"))
    worker = Ae3RuntimeWorker(
        owner="test", claim_next_task_use_case=None, idle_poll_interval_sec=1,
        execute_task_use_case=None, startup_recovery_use_case=recovery,
        zone_lease_repository=None, zone_intent_repository=None,
        spawn_background_task_fn=None, now_fn=lambda: NOW, logger=None,
    )
    clock = [0.0]
    monkeypatch.setattr("ae3lite.runtime.worker.time.monotonic", lambda: clock[0])
    await worker._maybe_run_terminal_command_reconcile_once()
    assert not pid.calls
    gateway.result = {"state": "done", "terminal_at": NOW, "response_details": {"duration_ms": 1500}}
    clock[0] = 1
    await worker._maybe_run_terminal_command_reconcile_once()
    assert len(gateway.calls) == 1
    clock[0] = 61
    await worker._maybe_run_terminal_command_reconcile_once()
    assert len(gateway.calls) == 2
    assert pid.calls[0]["hold_until"] == NOW + timedelta(seconds=90)
    assert pid.calls[0]["last_output_ms"] == 1500
    assert commands.marked == [901]
    recovery.run.assert_not_awaited()


@pytest.mark.asyncio
async def test_terminal_done_dose_repairs_command_and_pid_state(monkeypatch: pytest.MonkeyPatch):
    events = []

    async def _create_zone_event(zone_id, event_type, payload):
        events.append((zone_id, event_type, payload))

    monkeypatch.setattr(recovery_module, "create_zone_event", _create_zone_event)
    task = SimpleNamespace(
        id=32,
        zone_id=3,
        status="completed",
        task_type="irrigation_start",
        topology="two_tank",
        current_stage="irrigation_check",
        workflow=SimpleNamespace(stage_retry_count=0),
        correction=None,
    )
    command = {
        "id": 901,
        "task_id": 32,
        "planner_step": "irrigation_check:corr_dose_ph:pump_acid",
        "stage_name": "irrigation_check",
        "channel": "pump_acid",
        "payload": {
            "cmd": "dose",
            "cmd_id": "ae3-t32-z3-s39",
            "params": {"ml": 2.0, "duration_ms": 2000},
        },
    }
    terminal_at = datetime(2026, 10, 12, 11, 59, 30)
    gateway = _Gateway(
        {
            "state": "done",
            "legacy_status": "DONE",
            "cmd_id": "ae3-t32-z3-s39",
            "response_details": {"duration_ms": 1750},
            "terminal_at": terminal_at,
        }
    )
    pid_repository = _PidRepository()
    alert_repository = _AlertRepository()
    command_repository = _CommandRepository([command])
    use_case = StartupRecoveryUseCase(
        task_repository=_TaskRepository(task),
        lease_repository=SimpleNamespace(),
        command_gateway=gateway,
        command_repository=command_repository,
        pid_state_repository=pid_repository,
        alert_repository=alert_repository,
        use_startup_recovery_lock=False,
    )

    reconciled, unresolved = await use_case._reconcile_terminal_task_commands(now=NOW)

    assert (reconciled, unresolved) == (1, 0)
    assert pid_repository.calls == [
        {
            "zone_id": 3,
            "pid_type": "ph",
            "last_output_ms": 1750,
            "last_dose_at": terminal_at,
            "hold_until": terminal_at,
            "last_correction_kind": "ph_down",
            "ae_command_id": 901,
            "now": NOW,
        }
    ]
    assert events[0][1] == "AE_TERMINAL_TASK_COMMAND_RECONCILED"
    assert alert_repository.calls[0]["code"] == "biz_ae3_terminal_task_command_reconciled"
    assert command_repository.marked == [901]


@pytest.mark.asyncio
async def test_terminal_non_terminal_command_stays_unresolved_and_alerts():
    task = SimpleNamespace(
        id=34,
        zone_id=3,
        status="completed",
        task_type="irrigation_start",
        topology="two_tank",
        current_stage="irrigation_check",
        workflow=SimpleNamespace(stage_retry_count=0),
        correction=None,
    )
    command = {
        "id": 902,
        "task_id": 34,
        "planner_step": "irrigation_check:corr_dose_ec:pump_npk",
        "stage_name": "irrigation_check",
        "channel": "pump_npk",
        "payload": {"cmd": "dose", "params": {"duration_ms": 2000}},
    }
    alerts = _AlertRepository()
    use_case = StartupRecoveryUseCase(
        task_repository=_TaskRepository(task),
        lease_repository=SimpleNamespace(),
        command_gateway=_Gateway(
            {
                "state": "waiting_command",
                "legacy_status": "RUNNING",
                "cmd_id": "ae3-t34-z3-s1",
                "response_details": {},
                "terminal_at": None,
            }
        ),
        command_repository=_CommandRepository([command]),
        pid_state_repository=_PidRepository(),
        alert_repository=alerts,
        use_startup_recovery_lock=False,
    )

    reconciled, unresolved = await use_case._reconcile_terminal_task_commands(now=NOW)

    assert (reconciled, unresolved) == (0, 1)
    assert alerts.calls[0]["code"] == "biz_ae3_terminal_task_command_unknown"


@pytest.mark.asyncio
async def test_terminal_command_error_is_reconciled_as_failed_alert() -> None:
    task = SimpleNamespace(
        id=35,
        zone_id=3,
        status="failed",
        task_type="irrigation_start",
        topology="two_tank",
        current_stage="irrigation_check",
        workflow=SimpleNamespace(stage_retry_count=0),
        correction=None,
    )
    command = {
        "id": 903,
        "task_id": 35,
        "planner_step": "irrigation_check:corr_dose_ec:pump_a",
        "stage_name": "irrigation_check",
        "channel": "pump_a",
        "payload": {"cmd": "dose", "params": {"duration_ms": 2000}},
    }
    alerts = _AlertRepository()
    use_case = StartupRecoveryUseCase(
        task_repository=_TaskRepository(task),
        lease_repository=SimpleNamespace(),
        command_gateway=_Gateway(
            {
                "state": "failed",
                "legacy_status": "ERROR",
                "cmd_id": "ae3-t35-z3-s1",
                "response_details": {"duration_ms": 0},
                "terminal_at": NOW,
            }
        ),
        command_repository=_CommandRepository([command]),
        pid_state_repository=_PidRepository(),
        alert_repository=alerts,
        use_startup_recovery_lock=False,
    )

    reconciled, unresolved = await use_case._reconcile_terminal_task_commands(now=NOW)

    assert (reconciled, unresolved) == (1, 0)
    assert alerts.calls[0]["code"] == "biz_ae3_terminal_task_command_failed"


@pytest.mark.asyncio
async def test_terminal_dose_pid_failure_does_not_mark_accounted() -> None:
    task = SimpleNamespace(
        id=36,
        zone_id=3,
        status="completed",
        task_type="irrigation_start",
        topology="two_tank",
        current_stage="irrigation_check",
        workflow=SimpleNamespace(stage_retry_count=0),
        correction=None,
    )
    command = {
        "id": 904,
        "task_id": 36,
        "planner_step": "irrigation_check:corr_dose_ec:pump_b",
        "stage_name": "irrigation_check",
        "channel": "pump_b",
        "payload": {"cmd": "dose", "params": {"duration_ms": 2000}},
    }
    command_repository = _CommandRepository([command])

    class _FailingPid(_PidRepository):
        async def reconcile_completed_dose(self, **kwargs):
            self.calls.append(kwargs)
            raise RuntimeError("pid persist failed")

    pid_repository = _FailingPid()
    use_case = StartupRecoveryUseCase(
        task_repository=_TaskRepository(task),
        lease_repository=SimpleNamespace(),
        command_gateway=_Gateway(
            {
                "state": "done",
                "legacy_status": "DONE",
                "cmd_id": "ae3-t36-z3-s1",
                "response_details": {"duration_ms": 2000},
                "terminal_at": NOW,
            }
        ),
        command_repository=command_repository,
        pid_state_repository=pid_repository,
        alert_repository=_AlertRepository(),
        use_startup_recovery_lock=False,
    )

    reconciled, unresolved = await use_case._reconcile_terminal_task_commands(now=NOW)

    assert (reconciled, unresolved) == (0, 1)
    assert len(pid_repository.calls) == 1
    assert command_repository.marked == []


def _payload_dict(raw: object) -> dict:
    if isinstance(raw, str):
        loaded = json.loads(raw)
        return loaded if isinstance(loaded, dict) else {}
    if isinstance(raw, dict):
        return raw
    return {}


class _NoPublishHistory:
    def __init__(self) -> None:
        self.publishes = 0

    async def publish(self, **_kwargs):
        self.publishes += 1
        raise AssertionError("учёт DONE dose не публикует команду на узел")


class _TaskScopedCommands(PgAeCommandRepository):
    def __init__(self, task_id: int) -> None:
        self._only_task_id = task_id

    async def list_unreconciled_for_terminal_tasks(self, *, limit: int = 100):
        rows = await super().list_unreconciled_for_terminal_tasks(limit=limit)
        return [row for row in rows if int(row["task_id"]) == self._only_task_id]


class _FlakyPidRepository(PgPidStateRepository):
    def __init__(self) -> None:
        self.calls = 0
        self.fail = True

    async def reconcile_completed_dose(self, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("pid persist failed")
        return await super().reconcile_completed_dose(**kwargs)


async def _selected_command_ids() -> set[int]:
    rows = await PgAeCommandRepository().list_unreconciled_for_terminal_tasks(limit=1000)
    return {int(row["id"]) for row in rows}


@pytest.mark.asyncio
async def test_done_dose_without_account_marker_is_repaired_once_on_real_repository() -> None:
    """A4: DONE без маркера виден repository; падение PID оставляет строку; повтор не дозирует."""
    prefix = f"ae3-a4-dose-{uuid4().hex[:12]}"
    # ae_commands сортируются по created_at: старая метка держит строки в голове выборки.
    # commands партиционированы по времени, поэтому legacy-строка живёт в текущем окне.
    queued_at = datetime(1970, 1, 2, 0, 0, 0)
    legacy_at = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    history = _NoPublishHistory()
    pid_repository = _FlakyPidRepository()
    command_ids: dict[str, int] = {}
    zone_id = 0
    try:
        greenhouse_rows = await fetch(
            """
            INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
            VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
            RETURNING id
            """,
            f"gh-{uuid4().hex[:20]}",
            f"{prefix}-gh",
            f"pt-{uuid4().hex[:20]}",
        )
        greenhouse_id = int(greenhouse_rows[0]["id"])
        zone_rows = await fetch(
            """
            INSERT INTO zones (greenhouse_id, name, uid, status, automation_runtime, created_at, updated_at)
            VALUES ($1, $2, $3, 'online', 'ae3', NOW(), NOW())
            RETURNING id
            """,
            greenhouse_id,
            f"{prefix}-zone",
            f"zn-{uuid4().hex[:20]}",
        )
        zone_id = int(zone_rows[0]["id"])
        task_rows = await fetch(
            """
            INSERT INTO ae_tasks (
                zone_id, task_type, status, idempotency_key, scheduled_for, due_at,
                claimed_by, claimed_at, created_at, updated_at, topology, current_stage, workflow_phase
            )
            VALUES ($1, 'irrigation_start', 'completed', $2, $3, $3, 'worker-a', $3, $3, $3,
                    'two_tank', 'irrigation_check', 'irrigating')
            RETURNING id
            """,
            zone_id,
            f"{prefix}-task",
            legacy_at,
        )
        task_id = int(task_rows[0]["id"])
        legacy_rows = await fetch(
            """
            INSERT INTO commands (
                zone_id, channel, cmd, params, status, cmd_id, source,
                ack_at, duration_ms, created_at, updated_at
            )
            VALUES (
                $1, 'pump_b', 'dose', '{"ml": 5, "duration_ms": 5000}'::jsonb,
                'DONE', $2, 'automation-engine', $3, 2500, $3, $3
            )
            RETURNING id
            """,
            zone_id,
            f"{prefix}-cmd",
            legacy_at,
        )
        legacy_id = int(legacy_rows[0]["id"])

        async def _insert_ae(
            *,
            step_no: int,
            payload: dict,
            publish_status: str,
            terminal_status: str | None,
            external_id: str | None,
            queued_at: datetime,
            terminal_at: datetime | None,
            planner_step: str,
            channel: str,
        ) -> int:
            rows = await fetch(
                """
                INSERT INTO ae_commands (
                    task_id, step_no, planner_step, node_uid, channel, payload,
                    external_id, publish_status, terminal_status, terminal_at,
                    created_at, updated_at
                )
                VALUES (
                    $1, $2, $3, 'nd-ec-1', $4, $5::jsonb,
                    $6, $7, $8, $9, $10, $10
                )
                RETURNING id
                """,
                task_id,
                step_no,
                planner_step,
                channel,
                payload,
                external_id,
                publish_status,
                terminal_status,
                terminal_at,
                queued_at,
            )
            return int(rows[0]["id"])

        command_ids["done"] = await _insert_ae(
            step_no=1,
            payload={
                "cmd": "dose", "params": {"ml": 5, "duration_ms": 5000},
                "_ae3_dose_context": {"pid_type": "ec", "last_correction_kind": "ec", "hold_sec": 120},
            },
            publish_status="accepted",
            terminal_status="DONE",
            external_id=str(legacy_id),
            queued_at=queued_at,
            terminal_at=legacy_at,
            planner_step="irrigation_check:corr_dose_ec:pump_b",
            channel="pump_b",
        )
        command_ids["accepted_null"] = await _insert_ae(
            step_no=2,
            payload={"cmd": "set_relay", "params": {"state": False}, "cmd_id": f"{prefix}-relay"},
            publish_status="accepted",
            terminal_status=None,
            external_id=None,
            queued_at=queued_at + timedelta(seconds=1),
            terminal_at=None,
            planner_step="irrigation_check:0:pump_main",
            channel="pump_main",
        )
        command_ids["unconfirmed"] = await _insert_ae(
            step_no=3,
            payload={"cmd": "dose", "params": {"duration_ms": 1000}, "cmd_id": f"{prefix}-unconfirmed"},
            publish_status="published_unconfirmed",
            terminal_status=None,
            external_id=None,
            queued_at=queued_at + timedelta(seconds=2),
            terminal_at=None,
            planner_step="irrigation_check:corr_dose_ph:pump_acid",
            channel="pump_acid",
        )
        command_ids["fail_safe"] = await _insert_ae(
            step_no=4,
            payload={"cmd": "dose", "_ae3_fail_safe": True, "params": {"duration_ms": 1000}},
            publish_status="accepted",
            terminal_status="DONE",
            external_id=None,
            queued_at=queued_at + timedelta(seconds=3),
            terminal_at=legacy_at,
            planner_step="irrigation_check:corr_dose_ec:pump_b",
            channel="pump_b",
        )

        selected = await _selected_command_ids()
        assert command_ids["done"] in selected
        assert command_ids["accepted_null"] in selected
        assert command_ids["unconfirmed"] in selected
        assert command_ids["fail_safe"] not in selected

        command_repository = _TaskScopedCommands(task_id)
        task_repository = PgAutomationTaskRepository()
        gateway = SequentialCommandGateway(
            task_repository=task_repository,
            command_repository=command_repository,
            history_logger_client=history,
            poll_interval_sec=0.05,
        )
        use_case = StartupRecoveryUseCase(
            task_repository=task_repository,
            lease_repository=SimpleNamespace(),
            command_gateway=gateway,
            command_repository=command_repository,
            pid_state_repository=pid_repository,
            use_startup_recovery_lock=False,
        )

        await use_case._reconcile_terminal_task_commands(now=legacy_at + timedelta(minutes=5))
        selected_after_failure = await _selected_command_ids()
        done_row = await command_repository.get_by_task_step(task_id=task_id, step_no=1)
        assert command_ids["done"] in selected_after_failure
        assert _payload_dict(done_row["payload"]).get("_ae3_dose_accounted") is not True
        assert pid_repository.calls == 1
        pid_rows = await fetch(
            "SELECT last_output_ms FROM pid_state WHERE zone_id = $1 AND pid_type = 'ec'",
            zone_id,
        )
        assert pid_rows == []

        marked_fail_safe = await command_repository.mark_dose_accounted(
            ae_command_id=command_ids["fail_safe"],
            now=legacy_at,
        )
        fail_safe_row = await command_repository.get_by_task_step(task_id=task_id, step_no=4)
        assert marked_fail_safe is False
        assert _payload_dict(fail_safe_row["payload"]).get("_ae3_dose_accounted") is not True

        pid_repository.fail = False
        await use_case._reconcile_terminal_task_commands(now=legacy_at + timedelta(minutes=6))
        selected_after_repair = await _selected_command_ids()
        done_row = await command_repository.get_by_task_step(task_id=task_id, step_no=1)
        unconfirmed_row = await command_repository.get_by_task_step(task_id=task_id, step_no=3)
        assert command_ids["done"] not in selected_after_repair
        assert _payload_dict(done_row["payload"]).get("_ae3_dose_accounted") is True
        assert unconfirmed_row["terminal_status"] is None
        assert command_ids["unconfirmed"] in selected_after_repair
        assert command_ids["accepted_null"] in selected_after_repair
        pid_rows = await fetch(
            """
            SELECT last_output_ms, last_dose_at
            FROM pid_state
            WHERE zone_id = $1 AND pid_type = 'ec'
            """,
            zone_id,
        )
        assert len(pid_rows) == 1
        assert int(pid_rows[0]["last_output_ms"]) == 2500
        holds = await fetch("SELECT pid_type, hold_until FROM pid_state WHERE zone_id = $1", zone_id)
        assert {row["pid_type"] for row in holds} == {"ec", "ph"}
        assert all(row["hold_until"].replace(tzinfo=None) == legacy_at + timedelta(seconds=120) for row in holds)

        # Replaying an older dose cannot move the latest dose backwards or
        # shorten either contour's hold, even with a changed timing policy.
        await PgPidStateRepository().reconcile_completed_dose(
            zone_id=zone_id, pid_type="ec", last_output_ms=100,
            last_dose_at=legacy_at - timedelta(seconds=30),
            hold_until=legacy_at + timedelta(seconds=10),
            last_correction_kind="ec", ae_command_id=command_ids["done"], now=legacy_at,
        )
        holds_again = await fetch("SELECT pid_type, hold_until FROM pid_state WHERE zone_id = $1", zone_id)
        assert [dict(row) for row in holds_again] == [dict(row) for row in holds]
        assert pid_repository.calls == 2

        await use_case._reconcile_terminal_task_commands(now=legacy_at + timedelta(minutes=7))
        pid_rows_again = await fetch(
            """
            SELECT last_output_ms
            FROM pid_state
            WHERE zone_id = $1 AND pid_type = 'ec'
            """,
            zone_id,
        )
        assert pid_repository.calls == 2
        assert len(pid_rows_again) == 1
        assert int(pid_rows_again[0]["last_output_ms"]) == 2500
        assert history.publishes == 0
    finally:
        if zone_id:
            await execute("DELETE FROM pid_state WHERE zone_id = $1", zone_id)
        await execute("DELETE FROM greenhouses WHERE name LIKE $1", f"{prefix}%")
