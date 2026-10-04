"""Интеграционные тесты идемпотентности команд AE3 (PR5)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ae3lite.domain.entities import PlannedCommand
from ae3lite.domain.errors import CommandPublishError
from ae3lite.infrastructure.gateways.command_publish_pipeline import build_planner_step
from ae3lite.infrastructure.gateways.sequential_command_gateway import SequentialCommandGateway
from ae3lite.infrastructure.repositories import PgAeCommandRepository, PgAutomationTaskRepository
from common.db import execute, fetch

from test_ae3lite_startup_recovery_integration import (
    _cleanup,
    _insert_greenhouse,
    _insert_task,
    _insert_zone,
)


class _RecordingHistoryLogger:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

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
        self.calls.append(
            {
                "greenhouse_uid": greenhouse_uid,
                "zone_id": zone_id,
                "node_uid": node_uid,
                "channel": channel,
                "cmd": cmd,
                "params": params,
                "cmd_id": cmd_id,
            }
        )
        existing = await fetch(
            "SELECT id FROM commands WHERE cmd_id = $1 LIMIT 1",
            cmd_id,
        )
        if not existing:
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
                    created_at,
                    updated_at
                )
                VALUES ($1, $2, $3, $4::jsonb, 'SENT', $5, 'automation-engine', NOW(), NOW())
                """,
                zone_id,
                channel,
                cmd,
                params,
                cmd_id,
            )
        return str(cmd_id)


class _FailOnceHistoryLogger(_RecordingHistoryLogger):
    def __init__(self) -> None:
        super().__init__()
        self.attempt = 0

    async def publish(self, **kwargs) -> str:
        self.attempt += 1
        if self.attempt == 1:
            raise CommandPublishError("ReadTimeout: request to history-logger timed out")
        return await super().publish(**kwargs)


class _CircuitOpenThenOkHistoryLogger(_RecordingHistoryLogger):
    def __init__(self) -> None:
        super().__init__()
        self.attempt = 0

    async def publish(self, **kwargs) -> str:
        self.attempt += 1
        if self.attempt == 1:
            raise CommandPublishError("hl_circuit_open")
        return await super().publish(**kwargs)


class _FailMarkAcceptedRepo(PgAeCommandRepository):
    async def mark_publish_accepted(self, *, ae_command_id: int, external_id: str, now: datetime) -> bool:
        return False


def _mock_task(task_id: int, zone_id: int):
    from unittest.mock import MagicMock

    workflow = MagicMock()
    workflow.stage_deadline_at = None
    workflow.workflow_phase = "tank_filling"
    workflow.corr_step = ""
    task = MagicMock()
    task.id = task_id
    task.zone_id = zone_id
    task.claimed_by = "worker-a"
    task.claim_generation = 0
    task.current_stage = "solution_fill_check"
    task.topology = "two_tank_drip_substrate_trays"
    task.status = "running"
    task.workflow = workflow
    task.correction = None
    return task


@pytest.mark.asyncio
async def test_retry_after_ambiguous_publish_error_reuses_same_cmd_id() -> None:
    prefix = f"ae3-cmd-idem-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    command_repo = PgAeCommandRepository()
    task_repo = PgAutomationTaskRepository()
    hl = _FailOnceHistoryLogger()
    planner_step = "solution_fill_check:0"

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="running",
            now=now,
            topology="two_tank_drip_substrate_trays",
            current_stage="solution_fill_check",
            workflow_phase="tank_filling",
        )
        task = _mock_task(task_id, zone_id)
        command = PlannedCommand(
            step_no=1,
            node_uid="nd-pump-1",
            channel="pump_main",
            payload={"cmd": "dose", "params": {"ml": 1.0, "duration_ms": 1000}},
            planner_step=planner_step,
        )
        gateway = SequentialCommandGateway(
            task_repository=task_repo,
            command_repository=command_repo,
            history_logger_client=hl,
            poll_interval_sec=0.01,
            command_poll_default_sec=5.0,
            command_poll_margin_sec=0.0,
        )

        with pytest.raises(CommandPublishError, match="ReadTimeout"):
            await gateway._publish_pipeline.publish(task=task, command=command, now=now, planner_step=planner_step)

        failed_row = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
        assert failed_row is not None
        assert failed_row["publish_status"] == "published_unconfirmed"

        second = await gateway._publish_pipeline.publish(task=task, command=command, now=now, planner_step=planner_step)

        assert second.cmd_id_reused is True
        assert len(hl.calls) == 1
        assert hl.calls[0]["cmd_id"] == second.cmd_id

        rows = await fetch(
            "SELECT id, cmd_id FROM commands WHERE cmd_id = $1",
            second.cmd_id,
        )
        assert len(rows) <= 1

        ae_rows = await fetch(
            "SELECT id, step_no, planner_step, publish_status FROM ae_commands WHERE task_id = $1 ORDER BY step_no",
            task_id,
        )
        assert len(ae_rows) == 1
        assert int(ae_rows[0]["step_no"]) == int(second.step_no)
        assert ae_rows[0]["planner_step"] == planner_step
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_retry_after_definite_publish_error_keeps_pending_cmd_id() -> None:
    prefix = f"ae3-cmd-definite-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    command_repo = PgAeCommandRepository()
    task_repo = PgAutomationTaskRepository()
    hl = _CircuitOpenThenOkHistoryLogger()
    planner_step = "solution_fill_check:definite"

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="running",
            now=now,
            topology="two_tank_drip_substrate_trays",
            current_stage="solution_fill_check",
            workflow_phase="tank_filling",
        )
        task = _mock_task(task_id, zone_id)
        command = PlannedCommand(
            step_no=1,
            node_uid="nd-pump-1",
            channel="pump_main",
            payload={"cmd": "dose", "params": {"ml": 1.0, "duration_ms": 1000}},
            planner_step=planner_step,
        )
        gateway = SequentialCommandGateway(
            task_repository=task_repo,
            command_repository=command_repo,
            history_logger_client=hl,
            poll_interval_sec=0.01,
            command_poll_default_sec=5.0,
            command_poll_margin_sec=0.0,
        )

        with pytest.raises(CommandPublishError, match="hl_circuit_open"):
            await gateway._publish_pipeline.publish(task=task, command=command, now=now, planner_step=planner_step)

        pending_row = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
        assert pending_row is not None
        assert pending_row["publish_status"] == "pending"

        second = await gateway._publish_pipeline.publish(task=task, command=command, now=now, planner_step=planner_step)
        assert second.cmd_id_reused is True
        assert second.cmd_id.endswith("-s1")
        assert len(hl.calls) == 1
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_publish_redrive_after_mark_accept_failure_reaches_terminal() -> None:
    prefix = f"ae3-cmd-redrive-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    command_repo = _FailMarkAcceptedRepo()
    task_repo = PgAutomationTaskRepository()
    hl = _RecordingHistoryLogger()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="running",
            now=now,
            topology="two_tank_drip_substrate_trays",
            current_stage="startup",
            workflow_phase="idle",
        )
        task = _mock_task(task_id, zone_id)
        command = PlannedCommand(
            step_no=1,
            node_uid="nd-pump-1",
            channel="pump_main",
            payload={"cmd": "set_relay", "params": {"state": True}},
            planner_step=build_planner_step(stage="startup", seq_index=0),
        )
        gateway = SequentialCommandGateway(
            task_repository=task_repo,
            command_repository=command_repo,
            history_logger_client=hl,
            poll_interval_sec=0.01,
            command_poll_default_sec=30.0,
        )

        import ae3lite.infrastructure.gateways.sequential_command_gateway as gw_module

        poll_calls = {"n": 0}
        bound_recover = gateway.recover_waiting_command

        async def _recover_done(*, task, now):
            poll_calls["n"] += 1
            if poll_calls["n"] == 1:
                return {
                    "state": "waiting_command",
                    "task": task,
                    "legacy_status": "SENT",
                    "external_id": None,
                    "cmd_id": hl.calls[0]["cmd_id"],
                }
            legacy = await command_repo.get_legacy_command_by_cmd_id(
                zone_id=zone_id,
                cmd_id=str(hl.calls[0]["cmd_id"]),
            )
            assert legacy is not None
            await execute(
                "UPDATE commands SET status = 'DONE', updated_at = NOW() WHERE id = $1",
                int(legacy["id"]),
            )
            return await bound_recover(task=task, now=now)

        gateway.recover_waiting_command = AsyncMock(side_effect=_recover_done)  # type: ignore[method-assign]

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(gw_module.asyncio, "sleep", AsyncMock(return_value=None))
            result = await gateway.run_batch(task=task, commands=[command], now=now)

        assert result["success"] is True
        row = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
        assert row is not None
        assert row["publish_status"] in {"accepted", "published_unconfirmed"}
        updated = await task_repo.get_by_id(task_id=task_id)
        assert updated is not None
        assert updated.status == "running"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_allocate_reuses_planner_step_row() -> None:
    prefix = f"ae3-planner-step-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    command_repo = PgAeCommandRepository()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="running",
            now=now,
            topology="two_tank_drip_substrate_trays",
            current_stage="startup",
            workflow_phase="idle",
        )
        planner_step = "startup:1"
        first = await command_repo.allocate_and_create_pending(
            task_id=task_id,
            zone_id=zone_id,
            node_uid="nd-a",
            channel="pump_main",
            payload={"cmd": "dose", "params": {"ml": 1.0}},
            now=now,
            planner_step=planner_step,
        )
        second = await command_repo.allocate_and_create_pending(
            task_id=task_id,
            zone_id=zone_id,
            node_uid="nd-a",
            channel="pump_main",
            payload={"cmd": "dose", "params": {"ml": 1.0}},
            now=now,
            planner_step=planner_step,
        )
        assert first is not None and second is not None
        assert first[0] == second[0]
        assert first[1] == second[1]
        assert second[2] is True
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
@pytest.mark.parametrize("publish_status", ["pending", "published_unconfirmed"])
@pytest.mark.parametrize("changed", ["node", "channel", "cmd", "params"])
async def test_retry_rejects_changed_effect_without_mutating_intent(publish_status, changed):
    prefix = f"ae3-immutable-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    repo = PgAeCommandRepository()
    hl = _RecordingHistoryLogger()
    try:
        gh = await _insert_greenhouse(prefix)
        zone = await _insert_zone(prefix, greenhouse_id=gh)
        task_id = await _insert_task(zone, prefix=prefix, task_status="running", now=now)
        task = _mock_task(task_id, zone)
        args = dict(task_id=task_id, zone_id=zone, node_uid="nd-a", channel="pump_main",
                    payload={"cmd": "dose", "params": {"ml": 1.0}}, now=now, planner_step="dose:1")
        first = await repo.allocate_and_create_pending(**args)
        if publish_status == "published_unconfirmed":
            await repo.mark_publish_published_unconfirmed(ae_command_id=first[0], now=now)
        before = await repo.get_by_task_step(task_id=task_id, step_no=first[1])
        if changed == "node":
            args["node_uid"] = "nd-b"
        elif changed == "channel":
            args["channel"] = "pump_other"
        elif changed == "cmd":
            args["payload"] = {"cmd": "stop", "params": {"ml": 1.0}}
        else:
            args["payload"] = {"cmd": "dose", "params": {"ml": 2.0}}
        with pytest.raises(CommandPublishError, match="command_identity_conflict"):
            await repo.allocate_and_create_pending(**args)
        after = await repo.get_by_task_step(task_id=task_id, step_no=first[1])
        assert dict(before) == dict(after)
        from ae3lite.infrastructure.gateways.command_publish_pipeline import CommandPublishPipeline
        pipeline = CommandPublishPipeline(command_repository=repo, history_logger_client=hl)
        command = PlannedCommand(step_no=1, node_uid=args["node_uid"], channel=args["channel"], payload=args["payload"])
        with pytest.raises(CommandPublishError, match="command_identity_conflict"):
            await pipeline.redrive_existing(task=task, ae_command=after, command=command, now=now)
        assert hl.calls == []
        # A deliberate next pulse has a different identity, even in the same stage.
        args["planner_step"] = "dose:2"
        second = await repo.allocate_and_create_pending(**args)
        assert second[0] != first[0] and second[1] == first[1] + 1
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_claim_loss_between_allocation_and_http_prevents_publish():
    prefix = f"ae3-prehttp-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    hl = _RecordingHistoryLogger()

    class TransferBeforePublish(PgAeCommandRepository):
        async def resolve_greenhouse_uid(self, *, zone_id):
            uid = await super().resolve_greenhouse_uid(zone_id=zone_id)
            await execute("UPDATE ae_tasks SET claim_generation = claim_generation + 1 WHERE zone_id = $1", zone_id)
            return uid

    try:
        gh = await _insert_greenhouse(prefix)
        zone = await _insert_zone(prefix, greenhouse_id=gh)
        task_id = await _insert_task(zone, prefix=prefix, task_status="running", now=now)
        from ae3lite.infrastructure.gateways.command_publish_pipeline import CommandPublishPipeline
        pipeline = CommandPublishPipeline(command_repository=TransferBeforePublish(), history_logger_client=hl)
        command = PlannedCommand(step_no=1, node_uid="nd-a", channel="pump_main", payload={"cmd": "dose", "params": {"ml": 1}})
        with pytest.raises(CommandPublishError, match="claim_ownership_lost"):
            await pipeline.publish(task=_mock_task(task_id, zone), command=command, now=now)
        assert hl.calls == []
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_terminal_safety_off_is_allowed_but_cannot_stop_next_task():
    prefix = f"ae3-stop-authority-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    repo = PgAeCommandRepository()
    try:
        gh = await _insert_greenhouse(prefix)
        zone = await _insert_zone(prefix, greenhouse_id=gh)
        task_id = await _insert_task(zone, prefix=prefix, task_status="failed", now=now)
        safe = {"cmd": "set_relay", "params": {"state": False}, "_ae3_fail_safe": True}
        args = dict(task_id=task_id, owner="old-worker", claim_generation=0)
        await repo.assert_publish_authority(**args, payload=safe)
        with pytest.raises(CommandPublishError, match="claim_ownership_lost"):
            await repo.assert_publish_authority(**args, payload={**safe, "params": {"state": True}})
        await _insert_task(zone, prefix=prefix + '-next', task_status="pending", now=now)
        with pytest.raises(CommandPublishError, match="claim_ownership_lost"):
            await repo.assert_publish_authority(**args, payload=safe)
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
@pytest.mark.parametrize("safety_stop", [False, True])
async def test_deadline_checked_at_dispatch_not_batch_start(safety_stop):
    from datetime import timedelta
    from types import SimpleNamespace
    from ae3lite.domain.errors import TaskExecutionError
    from ae3lite.infrastructure.gateways.command_publish_pipeline import CommandPublishPipeline

    batch_start = datetime(2026, 10, 4)
    task = SimpleNamespace(id=1, zone_id=2, claimed_by="worker", claim_generation=3,
                           current_stage="irrigation", overall_deadline_at=batch_start + timedelta(seconds=30))
    repo = AsyncMock()
    repo.allocate_and_create_pending.return_value = (9, 1, False, "pending")
    repo.resolve_greenhouse_uid.return_value = "gh-test"
    repo.resolve_legacy_command_id.return_value = 10
    repo.assert_publish_authority = AsyncMock()
    transport = AsyncMock()
    transport.publish.return_value = "ae3-t1-z2-s1"
    pipeline = CommandPublishPipeline(command_repository=repo, history_logger_client=transport,
                                      now_fn=lambda: batch_start + timedelta(seconds=31))
    command = PlannedCommand(step_no=1, node_uid="nd-a", channel="pump_main",
                             payload={"cmd": "stop", "params": {}, "_ae3_fail_safe": safety_stop})
    if safety_stop:
        await pipeline.publish(task=task, command=command, now=batch_start)
        transport.publish.assert_awaited_once()
    else:
        with pytest.raises(TaskExecutionError) as caught:
            await pipeline.publish(task=task, command=command, now=batch_start)
        assert caught.value.code == "ae3_task_overall_deadline_exceeded"
        transport.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_replayed_done_does_not_adopt_newer_running_claim():
    from types import SimpleNamespace
    from ae3lite.domain.errors import TaskExecutionError
    task = SimpleNamespace(id=1, zone_id=2, claimed_by="worker", claim_generation=4, status="waiting_command")
    newer = SimpleNamespace(id=1, zone_id=2, claimed_by="worker", claim_generation=5, status="running")
    tasks = AsyncMock()
    tasks.resume_after_waiting_command.return_value = None
    tasks.get_by_id.return_value = newer
    gateway = SequentialCommandGateway(task_repository=tasks, command_repository=AsyncMock(),
                                       history_logger_client=AsyncMock(), poll_interval_sec=0.05)
    with pytest.raises(TaskExecutionError):
        await gateway._apply_legacy_outcome(task=task, ae_command={"id": 9},
            legacy_row={"id": 10, "status": "DONE"}, now=datetime(2026, 10, 4))
