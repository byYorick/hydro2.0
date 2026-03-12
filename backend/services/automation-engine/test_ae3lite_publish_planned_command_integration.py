from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from ae3lite.application.use_cases import PublishPlannedCommandUseCase
from ae3lite.domain.entities import AutomationTask, PlannedCommand
from ae3lite.domain.errors import CommandPublishError
from ae3lite.infrastructure.repositories import PgAeCommandRepository, PgAutomationTaskRepository
from common.db import execute, fetch


class FakeHistoryLoggerClient:
    def __init__(self, *, cmd_id: str, insert_legacy_command: bool) -> None:
        self._cmd_id = cmd_id
        self._insert_legacy_command = insert_legacy_command
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
        if self._insert_legacy_command:
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
                self._cmd_id,
            )
        return self._cmd_id


async def _insert_greenhouse(prefix: str) -> tuple[int, str]:
    greenhouse_uid = f"gh-{uuid4().hex[:20]}"
    rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        greenhouse_uid,
        f"{prefix}-gh",
        f"pt-{uuid4().hex[:20]}",
    )
    return int(rows[0]["id"]), greenhouse_uid


async def _insert_zone(prefix: str, *, greenhouse_id: int) -> int:
    rows = await fetch(
        """
        INSERT INTO zones (greenhouse_id, name, uid, status, automation_runtime, created_at, updated_at)
        VALUES ($1, $2, $3, 'online', 'ae3', NOW(), NOW())
        RETURNING id
        """,
        greenhouse_id,
        f"{prefix}-zone",
        f"zn-{uuid4().hex[:20]}",
    )
    return int(rows[0]["id"])


async def _insert_task(zone_id: int, *, prefix: str, now: datetime) -> AutomationTask:
    rows = await fetch(
        """
        INSERT INTO ae_tasks (
            zone_id,
            task_type,
            status,
            idempotency_key,
            scheduled_for,
            due_at,
            claimed_by,
            claimed_at,
            created_at,
            updated_at,
            topology,
            current_stage,
            workflow_phase
        )
        VALUES ($1, 'cycle_start', 'running', $2, $3, $3, 'worker-a', $3, $3, $3, 'two_tank', 'startup', 'idle')
        RETURNING *
        """,
        zone_id,
        f"{prefix}-task",
        now,
    )
    row = rows[0]
    return AutomationTask.from_row(row)


async def _cleanup(prefix: str) -> None:
    await execute("DELETE FROM greenhouses WHERE name LIKE $1", f"{prefix}%")


@pytest.mark.asyncio
async def test_publish_planned_command_persists_external_id_from_legacy_commands_table() -> None:
    prefix = f"ae3-publish-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task_repository = PgAutomationTaskRepository()
    repository = PgAeCommandRepository()
    history_client = FakeHistoryLoggerClient(cmd_id="cmd-ae3-success-1", insert_legacy_command=True)
    use_case = PublishPlannedCommandUseCase(
        task_repository=task_repository,
        command_repository=repository,
        history_logger_client=history_client,
    )

    try:
        greenhouse_id, greenhouse_uid = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task = await _insert_task(zone_id, prefix=prefix, now=now)

        published = await use_case.run(
            task=task,
            command=PlannedCommand(
                step_no=1,
                node_uid="nd-irrig-1",
                channel="pump_main",
                payload={"cmd": "set_relay", "params": {"state": True}},
            ),
            now=now,
        )

        row = await repository.get_by_task_step(task_id=task.id, step_no=1)

        assert history_client.calls[0]["greenhouse_uid"] == greenhouse_uid
        assert history_client.calls[0]["cmd_id"] == f"ae3-t{task.id}-z{task.zone_id}-s1"
        assert published.external_id is not None
        assert published.payload["cmd_id"] == f"ae3-t{task.id}-z{task.zone_id}-s1"
        assert row is not None
        assert row["publish_status"] == "accepted"
        assert row["external_id"] == published.external_id
        assert row["payload"]["cmd_id"] == f"ae3-t{task.id}-z{task.zone_id}-s1"

        updated_task = await task_repository.get_by_id(task_id=task.id)
        assert updated_task is not None
        assert updated_task.status == "waiting_command"

        command_rows = await fetch("SELECT id, cmd_id FROM commands WHERE id = $1", int(published.external_id))
        assert len(command_rows) == 1
        assert command_rows[0]["cmd_id"] == "cmd-ae3-success-1"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_publish_planned_command_marks_ae_command_failed_when_legacy_link_missing() -> None:
    prefix = f"ae3-publish-fail-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task_repository = PgAutomationTaskRepository()
    repository = PgAeCommandRepository()
    history_client = FakeHistoryLoggerClient(cmd_id="cmd-ae3-missing-link-1", insert_legacy_command=False)
    use_case = PublishPlannedCommandUseCase(
        task_repository=task_repository,
        command_repository=repository,
        history_logger_client=history_client,
    )

    try:
        greenhouse_id, _ = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task = await _insert_task(zone_id, prefix=prefix, now=now)

        with pytest.raises(CommandPublishError, match="Legacy commands.id not found"):
            await use_case.run(
                task=task,
                command=PlannedCommand(
                    step_no=1,
                    node_uid="nd-irrig-1",
                    channel="pump_main",
                    payload={"cmd": "set_relay", "params": {"state": True}},
                ),
                now=now,
            )

        row = await repository.get_by_task_step(task_id=task.id, step_no=1)

        assert row is not None
        assert row["publish_status"] == "failed"
        assert row["external_id"] is None
        assert "Legacy commands.id not found" in str(row["last_error"])

        updated_task = await task_repository.get_by_id(task_id=task.id)
        assert updated_task is not None
        assert updated_task.status == "failed"
        assert updated_task.error_code == "command_send_failed"
    finally:
        await _cleanup(prefix)
