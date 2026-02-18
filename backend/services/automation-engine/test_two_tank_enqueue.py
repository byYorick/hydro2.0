"""Unit tests for application.two_tank_enqueue helpers."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from application.two_tank_enqueue import enqueue_two_tank_check
from services.resilience_contract import SCHEDULER_SOURCE_TWO_TANK_STARTUP


@pytest.mark.asyncio
async def test_enqueue_two_tank_check_clamps_scheduled_for_to_timeout():
    enqueue_task = AsyncMock(return_value={"status": "queued"})
    timeout_at = datetime(2026, 2, 16, 12, 0, 10)
    result = await enqueue_two_tank_check(
        zone_id=1,
        payload={},
        workflow="clean_fill_check",
        phase_started_at=datetime(2026, 2, 16, 12, 0, 0),
        phase_timeout_at=timeout_at,
        poll_interval_sec=30,
        phase_cycle=1,
        build_two_tank_check_payload_fn=lambda **kwargs: {"workflow": kwargs["workflow"]},
        enqueue_task_fn=enqueue_task,
        now_factory=lambda: datetime(2026, 2, 16, 12, 0, 0),
    )
    assert result["status"] == "queued"
    kwargs = enqueue_task.await_args.kwargs
    assert kwargs["scheduled_for"] == timeout_at.isoformat()
    assert kwargs["expires_at"] == timeout_at.isoformat()
    assert kwargs["source"] == SCHEDULER_SOURCE_TWO_TANK_STARTUP
