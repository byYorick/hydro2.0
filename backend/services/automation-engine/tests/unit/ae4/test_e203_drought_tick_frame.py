"""E203: тик воркера — сушь даёт кадр без intent Laravel, interval ещё не вышел."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

from ae4.application import zone_tick as zone_tick_mod
from ae4.application.zone_tick import tick_one_zone
from ae4.domain.planting import LightIntegralCursor
from ae4.infrastructure.repositories.automation_task_repository import (
    PgAutomationTaskRepository,
)
from ae4.infrastructure.repositories.zone_lease_repository import PgZoneLeaseRepository
from common.db import fetch
from common.history_logger_gateway import GatewayPublishResult, HistoryLoggerGateway
from tests.unit.ae4.conftest_wave3 import make_phase, make_plan, make_planting, make_telemetry


class _SilentGateway(HistoryLoggerGateway):
    def __init__(self) -> None:
        super().__init__(metrics_prefix="ae4_e203")
        self.calls: list[dict[str, Any]] = []

    async def publish_and_await_done(self, **kwargs: Any) -> GatewayPublishResult:
        self.calls.append(dict(kwargs))
        return GatewayPublishResult(
            cmd_id=str(kwargs["cmd_id"]),
            legacy_command_id=f"legacy-{kwargs['cmd_id']}",
            status="DONE",
        )


async def _zone() -> int:
    gh = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'Europe/Moscow', $3, NOW(), NOW())
        RETURNING id
        """,
        f"gh-{uuid4().hex[:18]}",
        "e203",
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
        "e203-zone",
        f"zn-{uuid4().hex[:18]}",
    )
    return int(zone[0]["id"])


@pytest.mark.asyncio
async def test_e203_drought_tick_creates_frame_without_laravel_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zone_id = await _zone()
    now = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    started = datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc)
    plan = make_plan(zone_id=zone_id)
    planting = make_planting(
        zone_id=zone_id,
        started_at=started,
        interval_sec=3600,
        duration_sec=60,
        soil_moisture_min=40.0,
        soil_moisture_max=60.0,
        on_time="06:00:00",
        off_time="22:00:00",
    )
    telemetry = make_telemetry(
        feed_min=1,
        clean_min=1,
        soil_value=20.0,
        now=now,
    )

    async def fake_plan(*, zone_id: int):
        return plan

    async def fake_planting(*, zone_id: int):
        return planting

    async def fake_telemetry(**_kwargs):
        return telemetry

    async def fake_shots(**_kwargs):
        return None, started, False, 0

    async def fake_cursor(**_kwargs):
        from ae4.domain.planting import LightIntegralCursor

        return LightIntegralCursor(0.0, started, None, "ok")

    async def fake_save_cursor(**_kwargs):
        return None

    async def no_estop(*, zone_id: int) -> bool:
        return False

    async def no_work(**_kwargs) -> bool:
        return False

    async def no_light(**_kwargs):
        from ae4.domain.light_policy import LightPolicyDecision, LightPolicyResult

        return LightPolicyResult(
            decision=LightPolicyDecision(
                action="noop",
                reason_code="test_skip",
                steps=(),
            ),
            published_cmd_ids=(),
        )

    monkeypatch.setattr(zone_tick_mod, "load_zone_plan", fake_plan)
    monkeypatch.setattr(zone_tick_mod, "load_planting_state", fake_planting)
    monkeypatch.setattr(zone_tick_mod, "load_zone_telemetry", fake_telemetry)
    monkeypatch.setattr(zone_tick_mod, "load_shot_marks", fake_shots)
    monkeypatch.setattr(zone_tick_mod, "load_light_integral_cursor", fake_cursor)
    monkeypatch.setattr(zone_tick_mod, "save_light_integral_cursor", fake_save_cursor)
    monkeypatch.setattr(zone_tick_mod, "has_active_emergency_stop", no_estop)
    monkeypatch.setattr(zone_tick_mod, "zone_has_active_work", no_work)
    monkeypatch.setattr(zone_tick_mod, "apply_light_policy", no_light)

    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    gateway = _SilentGateway()

    outcome = await tick_one_zone(
        zone_id=zone_id,
        now=now,
        task_repository=task_repo,
        lease_repository=lease_repo,
        gateway=gateway,
    )
    assert outcome == "created"

    active = await task_repo.get_active_for_zone(zone_id=zone_id)
    assert active is not None
    assert active.status == "pending"
    assert active.due_at is not None
    meta = dict(active.intent_meta or {})
    assert meta.get("kind") == "feed_to_plants"
    assert meta.get("reason_code") == "soil_moisture_below_min"
    assert meta.get("shot_kind") == "extra"
    # Intent Laravel не участвует: idempotency_key свой ae4-*, не scheduler.
    assert str(active.idempotency_key).startswith("ae4-feed_to_plants-")
