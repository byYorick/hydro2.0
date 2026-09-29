"""E249: три no-effect — импульс стоп, critical один раз, failed не true."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

from ae4.application import zone_tick as zone_tick_mod
from ae4.application.mutation_decision import MutationDecision
from ae4.domain.dose_policy import DoseDecision
from ae4.infrastructure import failure_report as failure_report_mod
from ae4.infrastructure.failure_report import load_latest_state_overlay
from common.db import fetch


async def _zone_id() -> int:
    rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        f"gh-{uuid4().hex[:18]}",
        "e249",
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
        "e249-zone",
        f"zn-{uuid4().hex[:18]}",
    )
    return int(zone_rows[0]["id"])


@pytest.mark.asyncio
async def test_e249_three_no_effect_critical_once_failed_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zone_id = await _zone_id()
    alerts: list[dict[str, Any]] = []

    async def fake_alert(**kwargs: Any) -> bool:
        alerts.append(kwargs)
        return True

    monkeypatch.setattr(failure_report_mod, "send_biz_alert", fake_alert)

    decision = MutationDecision(
        kind=None,
        reason_code="reagent_no_effect_stopped",
        human_message="Три раза без эффекта — реагент остановлен",
        failed=False,
        create_task=False,
        create_alert=True,
        dose_decision=DoseDecision(
            allow_pulse=False,
            reagent="nutrition",
            dose_ml=None,
            reason_code="reagent_no_effect_stopped",
            human_message="Три раза без эффекта — реагент остановлен",
            blocks_shot=False,
            critical_alert=True,
        ),
    )

    class FakeRepo:
        async def create_pending_if_idle(self, **_kwargs: Any) -> None:
            return None

    now = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    for _ in range(3):
        await zone_tick_mod._apply_decision(
            zone_id=zone_id,
            grow_cycle_id=1,
            now=now,
            decision=decision,
            task_repository=FakeRepo(),  # type: ignore[arg-type]
        )

    overlay = await load_latest_state_overlay(zone_id=zone_id)
    assert overlay.get("failed") is not True
    assert len(alerts) == 1
    assert "no-effect" in str(alerts[0].get("dedupe_key") or "")
    assert decision.dose_decision is not None
    assert decision.dose_decision.allow_pulse is False
    assert decision.dose_decision.blocks_shot is False
    assert decision.failed is False
