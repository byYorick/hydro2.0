"""E210: нет датчика света — ON в окне, OFF на границе при занятой мутации."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

from ae4.application import zone_tick as zone_tick_mod
from ae4.application.zone_tick import tick_one_zone
from ae4.domain.light_policy import LIGHT_NO_GUARANTEED_OFF, decide_light
from ae4.infrastructure.repositories.automation_task_repository import (
    PgAutomationTaskRepository,
)
from ae4.infrastructure.repositories.zone_lease_repository import PgZoneLeaseRepository
from common.db import fetch
from common.history_logger_gateway import GatewayPublishResult, HistoryLoggerGateway
from tests.unit.ae4.conftest_wave3 import make_phase, make_plan, make_planting, make_telemetry


class _RecordingGateway(HistoryLoggerGateway):
    def __init__(self) -> None:
        super().__init__(metrics_prefix="ae4_e210")
        self.calls: list[dict[str, Any]] = []

    async def publish_and_await_done(self, **kwargs: Any) -> GatewayPublishResult:
        self.calls.append(dict(kwargs))
        assert str(kwargs["cmd_id"]).startswith("ae4-")
        # Имя плана (lighting_on/off) в gateway не уходит.
        assert "plan" not in kwargs
        assert kwargs.get("name") is None
        return GatewayPublishResult(
            cmd_id=str(kwargs["cmd_id"]),
            legacy_command_id=f"legacy-{kwargs['cmd_id']}",
            status="DONE",
        )


def _light_plans() -> dict[str, Any]:
    base = make_plan().command_plans
    plans = dict(base.get("plans") or base)
    plans["lighting_on"] = [
        {
            "node_uid": "nd-light",
            "channel": "white_light",
            "cmd": "set_relay",
            "params": {"state": True},
        }
    ]
    plans["lighting_off"] = [
        {
            "node_uid": "nd-light",
            "channel": "white_light",
            "cmd": "set_relay",
            "params": {"state": False},
        }
    ]
    return {"plans": plans}


async def _zone() -> int:
    gh = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'Europe/Moscow', $3, NOW(), NOW())
        RETURNING id
        """,
        f"gh-{uuid4().hex[:18]}",
        "e210",
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
        "e210-zone",
        f"zn-{uuid4().hex[:18]}",
    )
    return int(zone[0]["id"])


@pytest.mark.asyncio
async def test_e210_on_inside_window_without_light_sensor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Нет датчика света: внутри окна всё равно ON из шагов профиля."""
    zone_id = await _zone()
    # 10:00 UTC = 13:00 Europe/Moscow — внутри 06:00–22:00.
    now = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    plan = make_plan(zone_id=zone_id, command_plans=_light_plans())
    planting = make_planting(
        zone_id=zone_id,
        on_time="06:00:00",
        off_time="22:00:00",
        lighting_start_time="00:00:00",
        lighting_photoperiod_hours=1.0,
    )
    # Телеметрия без света: light_samples пустой.
    telemetry = make_telemetry(feed_min=1, clean_min=1, soil_value=50.0, now=now)

    async def fake_plan(*, zone_id: int):
        return plan

    async def fake_planting(*, zone_id: int):
        return planting

    async def fake_telemetry(**_kwargs):
        return telemetry

    async def fake_shots(**_kwargs):
        return None, now, False, 0

    async def fake_cursor(**_kwargs):
        from ae4.domain.planting import LightIntegralCursor

        return LightIntegralCursor(0.0, now, None, "ok")

    async def fake_save_cursor(**_kwargs):
        return None

    async def no_estop(*, zone_id: int) -> bool:
        return False

    async def no_work(**_kwargs) -> bool:
        return False

    async def fake_dose_states(**_kwargs):
        return None, None, None

    monkeypatch.setattr(zone_tick_mod, "load_zone_plan", fake_plan)
    monkeypatch.setattr(zone_tick_mod, "load_planting_state", fake_planting)
    monkeypatch.setattr(zone_tick_mod, "load_zone_telemetry", fake_telemetry)
    monkeypatch.setattr(zone_tick_mod, "load_shot_marks", fake_shots)
    monkeypatch.setattr(zone_tick_mod, "load_light_integral_cursor", fake_cursor)
    monkeypatch.setattr(zone_tick_mod, "save_light_integral_cursor", fake_save_cursor)
    monkeypatch.setattr(zone_tick_mod, "has_active_emergency_stop", no_estop)
    monkeypatch.setattr(zone_tick_mod, "zone_has_active_work", no_work)
    monkeypatch.setattr(zone_tick_mod, "_load_and_resolve_dose_states", fake_dose_states)

    gateway = _RecordingGateway()
    outcome = await tick_one_zone(
        zone_id=zone_id,
        now=now,
        task_repository=PgAutomationTaskRepository(),
        lease_repository=PgZoneLeaseRepository(),
        gateway=gateway,
    )
    light_calls = [c for c in gateway.calls if c.get("channel") == "white_light"]
    assert light_calls, "ожидался ON света без датчика"
    assert light_calls[0]["cmd"] == "set_relay"
    assert light_calls[0]["params"] == {"state": True}
    assert light_calls[0]["node_uid"] == "nd-light"
    assert outcome in {"paused", "created"}


@pytest.mark.asyncio
async def test_e210_off_at_boundary_while_mutation_busy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OFF на границе даже если проход уже занят доливом или дозой."""
    zone_id = await _zone()
    # 20:00 UTC = 23:00 Europe/Moscow — вне 06:00–22:00 (граница/ночь).
    now = datetime(2026, 6, 1, 20, 0, tzinfo=timezone.utc)
    plan = make_plan(zone_id=zone_id, command_plans=_light_plans())
    planting = make_planting(
        zone_id=zone_id,
        on_time="06:00:00",
        off_time="22:00:00",
    )

    async def fake_plan(*, zone_id: int):
        return plan

    async def fake_planting(*, zone_id: int):
        return planting

    async def no_estop(*, zone_id: int) -> bool:
        return False

    async def busy_work(**_kwargs) -> bool:
        return True

    monkeypatch.setattr(zone_tick_mod, "load_zone_plan", fake_plan)
    monkeypatch.setattr(zone_tick_mod, "load_planting_state", fake_planting)
    monkeypatch.setattr(zone_tick_mod, "has_active_emergency_stop", no_estop)
    monkeypatch.setattr(zone_tick_mod, "zone_has_active_work", busy_work)

    gateway = _RecordingGateway()
    outcome = await tick_one_zone(
        zone_id=zone_id,
        now=now,
        task_repository=PgAutomationTaskRepository(),
        lease_repository=PgZoneLeaseRepository(),
        gateway=gateway,
    )
    assert outcome == "skipped"
    light_calls = [c for c in gateway.calls if c.get("channel") == "white_light"]
    assert light_calls, "OFF света обязан уйти при занятой мутации"
    assert light_calls[0]["cmd"] == "set_relay"
    assert light_calls[0]["params"] == {"state": False}
    assert str(light_calls[0]["cmd_id"]).startswith("ae4-")


def test_e210_second_hour_pair_not_read() -> None:
    """Пара on_time/off_time задана — lighting_start+photoperiod (вторая пара) не читается."""
    # Если бы читали вторую пару 00:00 + 1ч, в 13:00 MSK окна бы не было.
    phase = make_phase(
        on_time="06:00:00",
        off_time="22:00:00",
        lighting_start_time="00:00:00",
        lighting_photoperiod_hours=1.0,
    )
    now = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    on_steps = [
        {
            "node_uid": "nd-light",
            "channel": "white_light",
            "cmd": "set_relay",
            "params": {"state": True},
        }
    ]
    off_steps = [
        {
            "node_uid": "nd-light",
            "channel": "white_light",
            "cmd": "set_relay",
            "params": {"state": False},
        }
    ]
    decision = decide_light(
        phase=phase,
        now=now,
        timezone_name="Europe/Moscow",
        mutation_busy=False,
        on_steps=on_steps,
        off_steps=off_steps,
        unattended_blocker_reason=LIGHT_NO_GUARANTEED_OFF,
    )
    assert decision.action == "on"
    assert decision.reason_code == "light_on_inside_window"
    assert decision.unattended_blocker_reason == LIGHT_NO_GUARANTEED_OFF
