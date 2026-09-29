"""E221: feed_only не шлёт команд слива и возврата стока."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

from ae4.application.execute_claimed import execute_claimed_task
from ae4.application.water_procedures import build_irrigation_start_steps
from ae4.config.zone_plan import ZonePlan
from ae4.infrastructure.repositories.ae_command_repository import PgAeCommandRepository
from ae4.infrastructure.repositories.automation_task_repository import (
    PgAutomationTaskRepository,
)
from ae4.infrastructure.repositories.zone_lease_repository import PgZoneLeaseRepository
from ae4.runtime.worker import AE4_WORKER_OWNER
from common.db import execute, fetch
from common.history_logger_gateway import GatewayPublishResult, HistoryLoggerGateway
from tests.unit.ae4.conftest_wave3 import make_plan, make_planting


class _RecordingGateway(HistoryLoggerGateway):
    def __init__(self) -> None:
        super().__init__(metrics_prefix="ae4_e221")
        self.calls: list[dict[str, Any]] = []

    async def publish_and_await_done(self, **kwargs: Any) -> GatewayPublishResult:
        self.calls.append(dict(kwargs))
        assert kwargs["cmd"] != "irrigation_start"
        assert "solution_drain" not in str(kwargs).lower()
        assert "tank_filling" not in str(kwargs).lower()
        return GatewayPublishResult(
            cmd_id=str(kwargs["cmd_id"]),
            legacy_command_id=f"legacy-{kwargs['cmd_id']}",
            status="DONE",
        )


def test_e221_frame_payload_has_pump_duration_not_plan_name() -> None:
    plan = make_plan()
    steps = build_irrigation_start_steps(plan=plan, duration_sec=45)
    channels = [step["channel"] for step in steps]
    assert "valve_drain" not in channels
    assert "pump_drain" not in channels
    pump = next(step for step in steps if step["channel"] == "pump_main")
    assert pump["cmd"] == "run_pump"
    assert pump["params"]["duration_ms"] == 45000


@pytest.mark.asyncio
async def test_e221_feed_only_frame_publishes_no_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    gh_uid = f"gh-{uuid4().hex[:18]}"
    gh = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id, uid
        """,
        gh_uid,
        "e221",
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
        "e221-zone",
        f"zn-{uuid4().hex[:18]}",
    )
    zone_id = int(zone[0]["id"])
    plan = make_plan(zone_id=zone_id, greenhouse_uid=str(gh[0]["uid"]))
    planting = make_planting(zone_id=zone_id, duration_sec=30)

    repo = PgAutomationTaskRepository()
    task = await repo.create_pending_if_idle(
        zone_id=zone_id,
        idempotency_key=f"e221-{uuid4().hex}",
        task_type="irrigation_start",
        current_stage="feed_to_plants",
        workflow_phase="idle",
        scheduled_for=now,
        due_at=now,
        now=now,
        intent_meta={
            "kind": "feed_to_plants",
            "shot_kind": "extra",
            "duration_sec": 30,
            "reason_code": "soil_moisture_below_min",
            "grow_cycle_id": planting.grow_cycle_id,
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

    from ae4.application import execute_claimed as exec_mod

    async def fake_plan(*, zone_id: int) -> ZonePlan:
        return plan

    async def fake_planting(*, zone_id: int):
        return planting

    async def fake_record(**_kwargs) -> None:
        return None

    monkeypatch.setattr(exec_mod, "load_zone_plan", fake_plan)
    monkeypatch.setattr(exec_mod, "load_planting_state", fake_planting)
    monkeypatch.setattr(
        "ae4.application.water_procedures.record_successful_shot",
        fake_record,
    )

    gateway = _RecordingGateway()
    await execute_claimed_task(
        claimed_task_id=task.id,
        zone_id=zone_id,
        worker_owner=AE4_WORKER_OWNER,
        now=now,
        task_repository=repo,
        command_repository=PgAeCommandRepository(),
        lease_repository=PgZoneLeaseRepository(),
        gateway=gateway,
    )

    assert gateway.calls
    channels = [call["channel"] for call in gateway.calls]
    assert "valve_drain" not in channels
    assert "pump_drain" not in channels
    assert "valve_return" not in channels
    pump_calls = [call for call in gateway.calls if call["channel"] == "pump_main"]
    assert any(call["cmd"] == "run_pump" for call in pump_calls)
    assert any(
        int(call["params"].get("duration_ms") or 0) == 30000 for call in pump_calls
    )
    blob = str(gateway.calls).lower()
    assert "solution_drain" not in blob
    assert "tank_filling" not in blob
