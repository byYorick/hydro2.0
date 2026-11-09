"""check_dry_run вызывается перед поливом и дозированием и блокирует пуск."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from ae3lite.application.services.dry_run_guard import command_needs_dry_run, guard_pump_start
from ae3lite.domain.errors import CommandPublishError
from common.pump_safety import check_dry_run
from common.utils.time import utcnow


def _level_row(label: str, value: float, *, age_sec: float = 0, quality: str = "GOOD"):
    return {
        "label": label,
        "value": value,
        "ts": utcnow().replace(tzinfo=None) - timedelta(seconds=age_sec),
        "quality": quality,
    }


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
    async def _unsafe(_zone_id: int, **_kwargs):
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

    async def _boom(_zone_id: int, **_kwargs):
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


@pytest.mark.asyncio
async def test_dry_run_fail_closed_branches() -> None:
    fresh_solution = _level_row("level_solution_min", 1.0)
    low_solution = _level_row("level_solution", 0.05)
    stale_solution = _level_row("level_solution_min", 1.0, age_sec=300)
    bad_solution = _level_row("level_solution_min", 1.0, quality="BAD")
    clean_only = _level_row("level_clean_min", 1.0)
    dose_stock = _level_row("pump_acid_level", 0.8)
    empty_dose_stock = _level_row("pump_acid_level", 0.0)

    cases = [
        ("missing", [], "solution", None, False, "unavailable"),
        ("stale", [stale_solution], "solution", None, False, "stale"),
        ("bad_quality", [bad_solution], "solution", None, False, "stale"),
        ("clean_tank_ignored", [clean_only], "solution", None, False, "unavailable"),
        ("solution_low", [low_solution, clean_only], "solution", None, False, "too low"),
        ("solution_ok_despite_clean", [fresh_solution, _level_row("level_clean_min", 0.0)], "solution", None, True, None),
        ("dose_uses_channel_stock", [fresh_solution, dose_stock, _level_row("level_solution", 0.0)], "dose", "pump_acid", True, None),
        ("dose_empty_stock", [fresh_solution, empty_dose_stock], "dose", "pump_acid", False, "too low"),
        ("dose_without_stock_uses_solution", [fresh_solution, clean_only], "dose", "pump_acid", True, None),
    ]

    for name, rows, source, channel, expect_safe, snippet in cases:
        with patch("common.pump_safety.fetch", new_callable=AsyncMock) as mock_fetch, \
             patch("common.pump_safety.create_alert", new_callable=AsyncMock) as mock_alert:
            mock_fetch.return_value = rows
            safe, error = await check_dry_run(9, source=source, channel=channel)
        assert safe is expect_safe, name
        if expect_safe:
            assert error is None
            mock_alert.assert_not_called()
        else:
            assert snippet in (error or "")
            mock_alert.assert_awaited()


@pytest.mark.asyncio
async def test_dry_run_query_error_is_fail_closed() -> None:
    with patch("common.pump_safety.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("common.pump_safety.create_alert", new_callable=AsyncMock) as mock_alert:
        mock_fetch.side_effect = RuntimeError("db down")
        safe, error = await check_dry_run(4, source="solution")
    assert safe is False
    assert error == "dry_run_check_failed"
    mock_alert.assert_awaited()
