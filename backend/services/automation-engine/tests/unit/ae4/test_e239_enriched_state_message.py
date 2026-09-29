"""E239: не-DONE даёт тот же русский текст на enrich-состоянии экрана."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from ae4.application.zone_state import enrich_zone_automation_state
from ae4.infrastructure import failure_report as failure_report_mod
from ae4.infrastructure.failure_report import report_failure
from common.db import fetch

# Одна фраза с PHPUnit ZoneAutomationStateServiceTest.
E239_HUMAN = "Команда ae4-t1-z1-s1 завершилась статусом ERROR, ожидался DONE"


async def _zone_id() -> int:
    rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        f"gh-{uuid4().hex[:18]}",
        "e239",
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
        "e239-zone",
        f"zn-{uuid4().hex[:18]}",
    )
    return int(zone_rows[0]["id"])


async def _async_true() -> bool:
    return True


@pytest.mark.asyncio
async def test_e239_non_done_message_on_enriched_zone_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zone_id = await _zone_id()
    monkeypatch.setattr(
        failure_report_mod,
        "send_biz_alert",
        lambda **_kwargs: _async_true(),
    )

    await report_failure(
        zone_id=zone_id,
        reason_code="ae4_command_not_done",
        human_message=E239_HUMAN,
        error_code="ae4_command_not_done",
        task_id=11,
    )

    base_payload: dict[str, Any] = {
        "zone_id": zone_id,
        "state": "IDLE",
        "state_label": "Ожидание",
        "state_details": {"failed": False, "human_error_message": None},
    }
    enriched = await enrich_zone_automation_state(
        zone_id=zone_id,
        payload=base_payload,
    )
    details = enriched.get("state_details") or {}
    assert details.get("failed") is True
    assert details.get("human_error_message") == E239_HUMAN
