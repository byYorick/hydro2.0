"""E218: E-STOP из zone_events обрывает полив; нового MQTT-топика нет."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

from ae4.application import zone_tick as zone_tick_mod
from ae4.application.zone_tick import tick_one_zone
from ae4.infrastructure import failure_report as failure_report_mod
from ae4.infrastructure.repositories.automation_task_repository import (
    PgAutomationTaskRepository,
)
from ae4.infrastructure.repositories.zone_lease_repository import PgZoneLeaseRepository
from common.db import create_zone_event, fetch
from common.history_logger_gateway import GatewayPublishResult, HistoryLoggerGateway
from tests.unit.ae4.conftest_wave3 import make_plan, make_planting


class _RecordingGateway(HistoryLoggerGateway):
    def __init__(self) -> None:
        super().__init__(metrics_prefix="ae4_e218")
        self.calls: list[dict[str, Any]] = []

    async def publish_and_await_done(self, **kwargs: Any) -> GatewayPublishResult:
        self.calls.append(dict(kwargs))
        # Новый MQTT-топик не заводится: cmd только device-level.
        assert kwargs["cmd"] in {"set_relay", "set_pwm", "run_pump", "dose", "state"}
        return GatewayPublishResult(
            cmd_id=str(kwargs["cmd_id"]),
            legacy_command_id=f"legacy-{kwargs['cmd_id']}",
            status="DONE",
        )


async def _zone() -> int:
    gh = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        f"gh-{uuid4().hex[:18]}",
        "e218",
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
        "e218-zone",
        f"zn-{uuid4().hex[:18]}",
    )
    return int(zone[0]["id"])


@pytest.mark.asyncio
async def test_e218_estop_from_zone_events_aborts_irrigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zone_id = await _zone()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    await create_zone_event(
        zone_id,
        "EMERGENCY_STOP_ACTIVATED",
        {"source": "pytest", "channel": "e_stop"},
    )
    plan = make_plan(zone_id=zone_id)
    planting = make_planting(zone_id=zone_id)

    async def fake_plan(*, zone_id: int):
        return plan

    async def fake_planting(*, zone_id: int):
        return planting

    async def no_work(**_kwargs) -> bool:
        return False

    async def fake_estop_off(**_kwargs):
        return ["ae4-estop-1"]

    alerts: list[dict[str, Any]] = []

    async def fake_alert(**kwargs: Any) -> bool:
        alerts.append(kwargs)
        return True

    monkeypatch.setattr(zone_tick_mod, "load_zone_plan", fake_plan)
    monkeypatch.setattr(zone_tick_mod, "load_planting_state", fake_planting)
    monkeypatch.setattr(zone_tick_mod, "zone_has_active_work", no_work)
    monkeypatch.setattr(zone_tick_mod, "emergency_off_dosing_and_tract", fake_estop_off)
    monkeypatch.setattr(failure_report_mod, "send_biz_alert", fake_alert)

    gateway = _RecordingGateway()
    outcome = await tick_one_zone(
        zone_id=zone_id,
        now=now,
        task_repository=PgAutomationTaskRepository(),
        lease_repository=PgZoneLeaseRepository(),
        gateway=gateway,
    )
    assert outcome == "failed"
    assert alerts
    assert alerts[0]["code"] == "emergency_stop_activated"
    tasks = await fetch(
        "SELECT COUNT(*)::int AS cnt FROM ae_tasks WHERE zone_id = $1",
        zone_id,
    )
    assert int(tasks[0]["cnt"]) == 0
