"""Подъём после рестарта: не берёт ae3; закрывает кадр через irrigation_stop."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

from ae4.application import frame_recovery as frame_recovery_mod
from ae4.application.frame_recovery import recover_inflight_tasks
from ae4.config.zone_plan import ZonePlan
from ae4.infrastructure.repositories.ae_command_repository import PgAeCommandRepository
from ae4.infrastructure.repositories.automation_task_repository import (
    PgAutomationTaskRepository,
)
from ae4.runtime.worker import AE4_WORKER_OWNER
from common.db import execute, fetch
from common.history_logger_gateway import GatewayPublishResult, HistoryLoggerGateway


class _RecordingGateway(HistoryLoggerGateway):
    def __init__(self) -> None:
        super().__init__(metrics_prefix="ae4_restart_test")
        self.calls: list[dict[str, Any]] = []

    async def publish_and_await_done(self, **kwargs: Any) -> GatewayPublishResult:
        self.calls.append(dict(kwargs))
        return GatewayPublishResult(
            cmd_id=str(kwargs["cmd_id"]),
            legacy_command_id=f"legacy-{kwargs['cmd_id']}",
            status="DONE",
        )


async def _insert_zone(*, runtime: str) -> int:
    gh = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        f"gh-{uuid4().hex[:18]}",
        f"rst-{runtime}",
        f"pt_{uuid4().hex[:16]}",
    )
    zone = await fetch(
        """
        INSERT INTO zones (
            greenhouse_id, name, uid, status, automation_runtime, created_at, updated_at
        )
        VALUES ($1, $2, $3, 'online', $4, NOW(), NOW())
        RETURNING id
        """,
        int(gh[0]["id"]),
        f"z-{runtime}",
        f"zn-{uuid4().hex[:18]}",
        runtime,
    )
    return int(zone[0]["id"])


async def _insert_inflight_task(*, zone_id: int, owner: str) -> int:
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    rows = await fetch(
        """
        INSERT INTO ae_tasks (
            zone_id, task_type, status, idempotency_key,
            topology, current_stage, workflow_phase,
            claimed_by, claimed_at, scheduled_for, due_at,
            created_at, updated_at
        )
        VALUES (
            $1, 'irrigation_start', 'waiting_command', $2,
            'planting', 'irrigation_check', 'irrigating',
            $3, $4, $4, $4, $4, $4
        )
        RETURNING id
        """,
        zone_id,
        f"rst-{uuid4().hex}",
        owner,
        now,
    )
    return int(rows[0]["id"])


@pytest.mark.asyncio
async def test_restart_skips_ae3_and_closes_open_frame_with_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    zone_ae3 = await _insert_zone(runtime="ae3")
    zone_ae4 = await _insert_zone(runtime="ae4")
    task_ae3 = await _insert_inflight_task(zone_id=zone_ae3, owner="ae3-owner")
    task_ae4 = await _insert_inflight_task(
        zone_id=zone_ae4,
        owner=AE4_WORKER_OWNER,
    )

    cmd_repo = PgAeCommandRepository()
    await cmd_repo.create_pending(
        task_id=task_ae4,
        step_no=1,
        node_uid="nd-pump",
        channel="pump_main",
        payload={
            "cmd": "run_pump",
            "params": {"duration_ms": 5000},
            "role": "irrigation_start",
            "cmd_id": f"ae4-t{task_ae4}-z{zone_ae4}-s1",
        },
        now=now,
        stage_name="irrigation_start",
    )
    await execute(
        """
        UPDATE ae_commands
        SET terminal_status = 'DONE',
            publish_status = 'accepted',
            updated_at = $2
        WHERE task_id = $1 AND step_no = 1
        """,
        task_ae4,
        now,
    )

    plan = ZonePlan(
        zone_id=zone_ae4,
        grow_cycle_id=1,
        greenhouse_id=1,
        greenhouse_uid="gh-rst",
        timezone="UTC",
        control_mode="auto",
        telemetry_max_age_sec=30,
        clean_fill_timeout_sec=120,
        solution_topup_timeout_sec=120,
        nutrient_solution_volume_l=50.0,
        command_plans={
            "plans": {
                "irrigation_stop": [
                    {
                        "node_uid": "nd-pump",
                        "channel": "valve_irrigation",
                        "cmd": "set_relay",
                        "params": {"state": False},
                    }
                ]
            }
        },
    )

    async def fake_load_zone_plan(*, zone_id: int) -> ZonePlan:
        assert zone_id == zone_ae4
        return plan

    monkeypatch.setattr(frame_recovery_mod, "load_zone_plan", fake_load_zone_plan)
    monkeypatch.setattr(
        frame_recovery_mod,
        "report_failure",
        lambda **_kwargs: _async_none(),
    )

    gateway = _RecordingGateway()
    task_repo = PgAutomationTaskRepository()

    inflight = await task_repo.list_inflight_for_ae4(worker_owner=AE4_WORKER_OWNER)
    inflight_ids = {task.id for task in inflight}
    assert task_ae4 in inflight_ids
    assert task_ae3 not in inflight_ids

    recovered = await recover_inflight_tasks(
        task_repository=task_repo,
        command_repository=cmd_repo,
        gateway=gateway,
        worker_owner=AE4_WORKER_OWNER,
        now=now,
    )
    assert recovered == 1
    assert gateway.calls
    assert all(call["cmd"] == "set_relay" for call in gateway.calls)
    assert all(call["cmd"] != "run_pump" for call in gateway.calls)
    assert all(
        not str(call.get("cmd_id", "")).endswith("-open2") for call in gateway.calls
    )
    # Второй кадр (irrigation_start) не публиковался.
    assert not any(
        str(call.get("params", {}).get("role", "")) == "irrigation_start"
        for call in gateway.calls
    )


async def _async_none() -> None:
    return None
