from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from ae3lite.api.contracts import StartCycleRequest
from ae3lite.infrastructure.metrics import INTENT_CLAIMED, INTENT_STALE_RECLAIMED, INTENT_TERMINAL
from ae3lite.infrastructure.repositories.zone_intent_repository import PgZoneIntentRepository


NOW = datetime(2026, 3, 12, 12, 0, 0)

_MODULE = "ae3lite.infrastructure.repositories.zone_intent_repository"


@pytest.mark.asyncio
async def test_claim_start_cycle_records_claim_and_stale_reclaim_metrics() -> None:
    before_claimed = INTENT_CLAIMED.labels(source_status="claimed")._value.get()
    before_stale = INTENT_STALE_RECLAIMED._value.get()

    claimed_row = {
        "id": 101,
        "zone_id": 7,
        "status": "claimed",
        "previous_status": "claimed",
    }

    with patch(f"{_MODULE}.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [claimed_row]
        repo = PgZoneIntentRepository()
        result = await repo.claim_start_cycle(
            zone_id=7,
            req=StartCycleRequest(source="laravel_scheduler", idempotency_key="intent-key-123"),
            now=NOW,
        )

    assert result["decision"] == "claimed"
    assert result["intent"]["status"] == "claimed"
    assert "previous_status" not in result["intent"]
    assert INTENT_CLAIMED.labels(source_status="claimed")._value.get() == before_claimed + 1
    assert INTENT_STALE_RECLAIMED._value.get() == before_stale + 1


@pytest.mark.asyncio
async def test_mark_terminal_records_metric_only_on_updated_rows() -> None:
    before_failed = INTENT_TERMINAL.labels(status="failed")._value.get()

    with patch(f"{_MODULE}.execute", new_callable=AsyncMock) as mock_execute:
        mock_execute.return_value = "UPDATE 1"
        repo = PgZoneIntentRepository()
        await repo.mark_terminal(
            intent_id=42,
            now=NOW,
            success=False,
            error_code="command_timeout",
            error_message="terminal_timeout",
        )

    assert INTENT_TERMINAL.labels(status="failed")._value.get() == before_failed + 1

    # No metric increment when 0 rows affected
    with patch(f"{_MODULE}.execute", new_callable=AsyncMock) as mock_execute:
        mock_execute.return_value = "UPDATE 0"
        repo = PgZoneIntentRepository()
        await repo.mark_terminal(
            intent_id=42,
            now=NOW,
            success=False,
            error_code="command_timeout",
            error_message="terminal_timeout",
        )

    assert INTENT_TERMINAL.labels(status="failed")._value.get() == before_failed + 1
