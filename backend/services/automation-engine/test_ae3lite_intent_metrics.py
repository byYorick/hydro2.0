from __future__ import annotations

from datetime import datetime

import pytest

from ae3lite.api.contracts import StartCycleRequest
from ae3lite.api.intents import claim_start_cycle_intent, mark_intent_terminal
from ae3lite.infrastructure.metrics import INTENT_CLAIMED, INTENT_STALE_RECLAIMED, INTENT_TERMINAL


NOW = datetime(2026, 3, 12, 12, 0, 0)


@pytest.mark.asyncio
async def test_claim_start_cycle_intent_records_claim_and_stale_reclaim_metrics() -> None:
    before_claimed = INTENT_CLAIMED.labels(source_status="claimed")._value.get()
    before_stale = INTENT_STALE_RECLAIMED._value.get()

    async def fetch_fn(*args, **kwargs):
        return [
            {
                "id": 101,
                "zone_id": 7,
                "status": "claimed",
                "previous_status": "claimed",
            }
        ]

    result = await claim_start_cycle_intent(
        zone_id=7,
        req=StartCycleRequest(source="laravel_scheduler", idempotency_key="intent-key-123"),
        now=NOW,
        fetch_fn=fetch_fn,
    )

    assert result["decision"] == "claimed"
    assert result["intent"]["status"] == "claimed"
    assert "previous_status" not in result["intent"]
    assert INTENT_CLAIMED.labels(source_status="claimed")._value.get() == before_claimed + 1
    assert INTENT_STALE_RECLAIMED._value.get() == before_stale + 1


@pytest.mark.asyncio
async def test_mark_intent_terminal_records_terminal_metric_only_on_updated_rows() -> None:
    before_failed = INTENT_TERMINAL.labels(status="failed")._value.get()

    async def execute_fn(*args, **kwargs):
        return "UPDATE 1"

    await mark_intent_terminal(
        intent_id=42,
        now=NOW,
        success=False,
        error_code="command_timeout",
        error_message="terminal_timeout",
        execute_fn=execute_fn,
    )

    assert INTENT_TERMINAL.labels(status="failed")._value.get() == before_failed + 1

    async def execute_noop(*args, **kwargs):
        return "UPDATE 0"

    await mark_intent_terminal(
        intent_id=42,
        now=NOW,
        success=False,
        error_code="command_timeout",
        error_message="terminal_timeout",
        execute_fn=execute_noop,
    )

    assert INTENT_TERMINAL.labels(status="failed")._value.get() == before_failed + 1
