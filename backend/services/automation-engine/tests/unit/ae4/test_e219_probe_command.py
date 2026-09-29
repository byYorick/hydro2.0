"""E219: тестовая команда через шлюз; не-DONE роняет шаг."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

from ae4.application.execute_claimed import execute_claimed_task
from ae4.infrastructure.repositories.ae_command_repository import PgAeCommandRepository
from ae4.infrastructure.repositories.automation_task_repository import (
    PgAutomationTaskRepository,
)
from ae4.infrastructure.repositories.zone_lease_repository import PgZoneLeaseRepository
from ae4.runtime.worker import AE4_WORKER_OWNER
from common.db import fetch
from common.history_logger_gateway import (
    CommandNotDoneError,
    GatewayPublishResult,
    HistoryLoggerGateway,
    build_ae4_cmd_id,
)


class _MockGateway(HistoryLoggerGateway):
    def __init__(self, *, terminal_status: str) -> None:
        super().__init__(metrics_prefix="ae4_test", status_reader=lambda _cmd: terminal_status)
        self.published: list[dict[str, Any]] = []
        self._terminal_status = terminal_status

    async def publish(self, **kwargs: Any) -> str:
        self.published.append(dict(kwargs))
        assert str(kwargs["cmd_id"]).startswith("ae4-")
        assert kwargs["cmd"] != "irrigation_start"
        return f"legacy-{kwargs['cmd_id']}"

    async def publish_and_await_done(self, **kwargs: Any) -> GatewayPublishResult:
        await self.publish(**kwargs)
        if self._terminal_status != "DONE":
            raise CommandNotDoneError(
                cmd_id=str(kwargs["cmd_id"]),
                status=self._terminal_status,
                message=f"статус {self._terminal_status}",
            )
        return GatewayPublishResult(
            cmd_id=str(kwargs["cmd_id"]),
            legacy_command_id=f"legacy-{kwargs['cmd_id']}",
            status="DONE",
        )


async def _fixture_zone() -> tuple[int, str]:
    gh_uid = f"gh-{uuid4().hex[:18]}"
    rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        gh_uid,
        "e219",
        f"pt_{uuid4().hex[:20]}",
    )
    greenhouse_id = int(rows[0]["id"])
    zone_rows = await fetch(
        """
        INSERT INTO zones (
            greenhouse_id, name, uid, status, automation_runtime, created_at, updated_at
        )
        VALUES ($1, $2, $3, 'online', 'ae4', NOW(), NOW())
        RETURNING id
        """,
        greenhouse_id,
        "e219-zone",
        f"zn-{uuid4().hex[:18]}",
    )
    return int(zone_rows[0]["id"]), gh_uid


async def _create_probe_task(*, zone_id: int, greenhouse_uid: str) -> int:
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    repo = PgAutomationTaskRepository()
    task = await repo.create_pending_if_idle(
        zone_id=zone_id,
        idempotency_key=f"e219-{uuid4().hex}",
        task_type="irrigation_start",
        current_stage="probe_command",
        workflow_phase="idle",
        scheduled_for=now,
        due_at=now,
        now=now,
        intent_meta={
            "kind": "probe_command",
            "greenhouse_uid": greenhouse_uid,
            "node_uid": "nd-probe",
            "channel": "pump_main",
            "cmd": "state",
            "params": {},
        },
    )
    assert task is not None
    from common.db import execute

    await execute(
        """
        UPDATE ae_tasks
        SET status = 'claimed',
            claimed_by = $2,
            claimed_at = $3,
            updated_at = $3
        WHERE id = $1
        """,
        task.id,
        AE4_WORKER_OWNER,
        now,
    )
    return task.id


@pytest.mark.asyncio
async def test_e219_probe_reaches_gateway_and_non_done_fails() -> None:
    zone_id, greenhouse_uid = await _fixture_zone()
    task_id = await _create_probe_task(zone_id=zone_id, greenhouse_uid=greenhouse_uid)
    gateway = _MockGateway(terminal_status="ERROR")
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)

    await execute_claimed_task(
        claimed_task_id=task_id,
        zone_id=zone_id,
        worker_owner=AE4_WORKER_OWNER,
        now=now,
        task_repository=PgAutomationTaskRepository(),
        command_repository=PgAeCommandRepository(),
        lease_repository=PgZoneLeaseRepository(),
        gateway=gateway,
    )

    assert len(gateway.published) == 1
    assert gateway.published[0]["cmd"] == "state"
    rows = await fetch("SELECT status, error_code FROM ae_tasks WHERE id = $1", task_id)
    assert rows[0]["status"] == "failed"
    assert rows[0]["error_code"] == "ae4_command_not_done"
    events = await fetch(
        """
        SELECT type, payload_json
        FROM zone_events
        WHERE zone_id = $1 AND type = 'AE4_STATE_DETAILS'
        ORDER BY id DESC
        LIMIT 1
        """,
        zone_id,
    )
    assert events
    assert events[0]["payload_json"]["failed"] is True


def test_ae4_cmd_id_prefix() -> None:
    assert build_ae4_cmd_id(task_id=1, zone_id=2, step_no=3).startswith("ae4-")
