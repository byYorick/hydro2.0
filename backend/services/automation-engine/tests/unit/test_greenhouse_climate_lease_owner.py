"""Lease owner must distinguish overlapping ticks from the same worker."""

from unittest.mock import AsyncMock

import pytest

from ae3lite.greenhouse_climate import run_tick


@pytest.mark.asyncio
async def test_tick_uses_distinct_lease_owner_for_each_attempt(monkeypatch) -> None:
    monkeypatch.setattr(run_tick, "_ensure_state_row", AsyncMock())
    monkeypatch.setattr(run_tick, "fetch", AsyncMock(return_value=[{"intent_id": 12}]))
    monkeypatch.setattr(run_tick, "execute", AsyncMock())
    claim = AsyncMock(return_value=False)
    monkeypatch.setattr(run_tick, "_claim_greenhouse_lease", claim)

    for _ in range(2):
        result = await run_tick.run_greenhouse_climate_tick(
            greenhouse_id=7,
            idempotency_key="same-worker",
            history_logger_client=object(),
            worker_owner="worker-a",
        )
        assert result["reason"] == "greenhouse_climate_busy"

    first_owner = claim.await_args_list[0].kwargs["owner"]
    second_owner = claim.await_args_list[1].kwargs["owner"]
    assert first_owner != second_owner
    assert len(first_owner) <= 64
    assert len(second_owner) <= 64
