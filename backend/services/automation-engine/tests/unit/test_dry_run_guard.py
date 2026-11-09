"""check_dry_run вызывается перед поливом и дозированием и блокирует пуск."""

from __future__ import annotations

import pytest

from ae3lite.application.services.dry_run_guard import command_needs_dry_run, guard_pump_start
from ae3lite.domain.errors import CommandPublishError


def test_dry_run_covers_dose_and_irrigation_only() -> None:
    assert command_needs_dry_run(cmd="dose", channel="pump_acid", params={"ml": 2}, stage="correction")
    assert command_needs_dry_run(
        cmd="run_pump",
        channel="pump_main",
        params={"duration_ms": 1000},
        stage="irrigation_start",
    )
    assert command_needs_dry_run(
        cmd="set_relay",
        channel="pump_main",
        params={"state": True},
        stage="task_type irrigation_start",
    )
    assert not command_needs_dry_run(
        cmd="set_relay",
        channel="pump_main",
        params={"state": False},
        stage="irrigation_stop",
    )
    assert not command_needs_dry_run(
        cmd="set_relay",
        channel="pump_main",
        params={"state": True},
        stage="solution_fill_start",
    )
    assert not command_needs_dry_run(
        cmd="set_relay",
        channel="valve_irrigation",
        params={"state": True},
        stage="irrigation_start",
    )


@pytest.mark.asyncio
async def test_unsafe_dry_run_blocks_and_check_error_alerts(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _unsafe(_zone_id: int):
        return False, "Water level too low"

    monkeypatch.setattr("common.pump_safety.check_dry_run", _unsafe)
    with pytest.raises(CommandPublishError, match="Water level too low"):
        await guard_pump_start(
            zone_id=3,
            cmd="dose",
            channel="pump_acid",
            params={"ml": 1},
            stage="correction",
        )


@pytest.mark.asyncio
async def test_dry_run_exception_blocks_and_raises_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    alerts: list[str] = []

    async def _boom(_zone_id: int):
        raise RuntimeError("db down")

    async def _alert(**kwargs):
        alerts.append(str(kwargs.get("code")))

    monkeypatch.setattr("common.pump_safety.check_dry_run", _boom)
    monkeypatch.setattr("common.alerts.create_alert", _alert)
    with pytest.raises(CommandPublishError, match="dry_run_check_failed"):
        await guard_pump_start(
            zone_id=3,
            cmd="run_pump",
            channel="pump_main",
            params={"duration_ms": 1000},
            stage="irrigation_start",
        )
    assert alerts == ["biz_dry_run"]
