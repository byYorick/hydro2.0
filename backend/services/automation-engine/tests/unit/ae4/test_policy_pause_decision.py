"""Вызов report_planting_decision из пути паузы воркера."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from ae4.application.execute_claimed import execute_claimed_task
from ae4.application.zone_state import enrich_zone_automation_state
from ae4.infrastructure.repositories.ae_command_repository import PgAeCommandRepository
from ae4.infrastructure.repositories.automation_task_repository import (
    PgAutomationTaskRepository,
)
from ae4.infrastructure.repositories.zone_lease_repository import PgZoneLeaseRepository
from ae4.runtime.worker import AE4_WORKER_OWNER
from common.db import execute, fetch
from common.history_logger_gateway import HistoryLoggerGateway


async def _fixture() -> int:
    gh = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        f"gh-{uuid4().hex[:18]}",
        "pause",
        f"pt_{uuid4().hex[:16]}",
    )
    zone = await fetch(
        """
        INSERT INTO zones (
            greenhouse_id, name, uid, status, automation_runtime, created_at, updated_at
        )
        VALUES ($1, $2, $3, 'online', 'ae4', NOW(), NOW())
        RETURNING id
        """,
        int(gh[0]["id"]),
        "pause-zone",
        f"zn-{uuid4().hex[:18]}",
    )
    return int(zone[0]["id"])


@pytest.mark.asyncio
async def test_policy_pause_calls_report_planting_decision() -> None:
    zone_id = await _fixture()
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    repo = PgAutomationTaskRepository()
    task = await repo.create_pending_if_idle(
        zone_id=zone_id,
        idempotency_key=f"pause-{uuid4().hex}",
        task_type="irrigation_start",
        current_stage="policy_pause",
        workflow_phase="idle",
        scheduled_for=now,
        due_at=now,
        now=now,
        intent_meta={
            "kind": "policy_pause",
            "reason_code": "night_skip",
            "human_message": "Ночь: полив пропущен",
        },
    )
    assert task is not None
    await execute(
        """
        UPDATE ae_tasks
        SET status = 'claimed', claimed_by = $2, claimed_at = $3, updated_at = $3
        WHERE id = $1
        """,
        task.id,
        AE4_WORKER_OWNER,
        now,
    )

    await execute_claimed_task(
        claimed_task_id=task.id,
        zone_id=zone_id,
        worker_owner=AE4_WORKER_OWNER,
        now=now,
        task_repository=repo,
        command_repository=PgAeCommandRepository(),
        lease_repository=PgZoneLeaseRepository(),
        gateway=HistoryLoggerGateway(metrics_prefix="ae4_pause_test"),
    )

    enriched = await enrich_zone_automation_state(
        zone_id=zone_id,
        payload={
            "zone_id": zone_id,
            "state": "IDLE",
            "state_details": {"failed": False},
        },
    )
    decision = enriched.get("planting_decision") or {}
    assert decision.get("failed") is False
    assert decision.get("reason_code") == "night_skip"
    assert decision.get("human_message") == "Ночь: полив пропущен"
    details = enriched.get("state_details") or {}
    assert details.get("failed") is not True
