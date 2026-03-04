from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from executor.two_tank_enqueue import enqueue_two_tank_check


@pytest.mark.asyncio
async def test_enqueue_two_tank_check_keeps_expires_at_after_scheduled_boundary():
    captured = {}

    def _build_payload(**_kwargs):
        return {"workflow": "prepare_recirculation_check"}

    async def _enqueue_task(**kwargs):
        captured.update(kwargs)
        return {"status": "pending"}

    now = datetime(2026, 3, 4, 11, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    phase_timeout_at = now + timedelta(seconds=30)

    result = await enqueue_two_tank_check(
        zone_id=2,
        payload={"workflow": "prepare_recirculation_check"},
        workflow="prepare_recirculation_check",
        phase_started_at=now - timedelta(seconds=60),
        phase_timeout_at=phase_timeout_at,
        poll_interval_sec=60,
        phase_cycle=1,
        build_two_tank_check_payload_fn=_build_payload,
        enqueue_task_fn=_enqueue_task,
        now_factory=lambda: now,
    )

    assert result == {"status": "pending"}
    assert captured["scheduled_for"] == phase_timeout_at.isoformat()
    assert captured["expires_at"] == (phase_timeout_at + timedelta(seconds=5)).isoformat()
