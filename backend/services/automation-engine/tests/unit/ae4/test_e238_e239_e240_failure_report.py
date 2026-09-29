"""E238/E239/E240: сбой через failure_report и устойчивость к падению алерта."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from ae4.infrastructure import failure_report as failure_report_mod
from ae4.infrastructure.failure_report import (
    load_latest_state_overlay,
    report_exception,
    report_failure,
)
from common.db import fetch


async def _zone_id() -> int:
    rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        f"gh-{uuid4().hex[:18]}",
        "e238",
        f"pt_{uuid4().hex[:20]}",
    )
    zone_rows = await fetch(
        """
        INSERT INTO zones (
            greenhouse_id, name, uid, status, automation_runtime, created_at, updated_at
        )
        VALUES ($1, $2, $3, 'online', 'ae4', NOW(), NOW())
        RETURNING id
        """,
        int(rows[0]["id"]),
        "e238-zone",
        f"zn-{uuid4().hex[:18]}",
    )
    return int(zone_rows[0]["id"])


@pytest.mark.asyncio
async def test_e238_exception_sets_failed_and_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    zone_id = await _zone_id()
    alerts: list[dict[str, Any]] = []

    async def fake_alert(**kwargs: Any) -> bool:
        alerts.append(kwargs)
        return True

    monkeypatch.setattr(failure_report_mod, "send_biz_alert", fake_alert)

    await report_exception(
        zone_id=zone_id,
        reason_code="ae4_task_exception",
        human_message="Исключение тестового тика",
        exc=RuntimeError("boom"),
        grow_cycle_id=42,
        task_id=7,
    )

    overlay = await load_latest_state_overlay(zone_id=zone_id)
    assert overlay.get("failed") is True
    assert overlay.get("error_code") == "ae4_task_exception"
    assert "Исключение тестового тика" in str(overlay.get("human_error_message"))
    assert alerts
    assert alerts[0]["dedupe_key"]


@pytest.mark.asyncio
async def test_e240_alert_failure_keeps_zone_text(monkeypatch: pytest.MonkeyPatch) -> None:
    zone_id = await _zone_id()

    async def broken_alert(**_kwargs: Any) -> bool:
        raise RuntimeError("telegram down")

    monkeypatch.setattr(failure_report_mod, "send_biz_alert", broken_alert)

    await report_failure(
        zone_id=zone_id,
        reason_code="ae4_task_exception",
        human_message="Текст сбоя должен остаться",
        error_code="ae4_task_exception",
    )
    overlay = await load_latest_state_overlay(zone_id=zone_id)
    assert overlay.get("failed") is True
    assert overlay.get("human_error_message") == "Текст сбоя должен остаться"
