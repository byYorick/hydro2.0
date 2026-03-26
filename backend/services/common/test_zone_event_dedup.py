from unittest.mock import AsyncMock, patch

import pytest

from common.db import create_zone_event


@pytest.mark.asyncio
async def test_create_zone_event_skips_duplicate_ae_task_started_for_same_task_stage():
    details = {
        "task_id": 11,
        "stage": "prepare_recirculation_check",
        "topology": "two_tank",
        "intent_trigger": "diagnostics_tick",
    }

    with patch("common.db.fetch", new=AsyncMock(return_value=[{"payload": dict(details)}])) as mock_fetch, \
         patch("common.db.execute", new=AsyncMock()) as mock_execute:
        await create_zone_event(7, "AE_TASK_STARTED", details)

    mock_fetch.assert_awaited_once()
    mock_execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_zone_event_allows_ae_task_started_after_stage_change():
    previous = {
        "task_id": 11,
        "stage": "solution_fill_check",
    }
    current = {
        "task_id": 11,
        "stage": "prepare_recirculation_check",
        "topology": "two_tank",
        "intent_trigger": "diagnostics_tick",
    }

    with patch("common.db.fetch", new=AsyncMock(return_value=[{"payload": previous}])) as mock_fetch, \
         patch("common.db.execute", new=AsyncMock()) as mock_execute:
        await create_zone_event(7, "AE_TASK_STARTED", current)

    mock_fetch.assert_awaited_once()
    mock_execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_zone_event_does_not_dedupe_other_event_types():
    with patch("common.db.fetch", new=AsyncMock()) as mock_fetch, \
         patch("common.db.execute", new=AsyncMock()) as mock_execute:
        await create_zone_event(7, "PH_CORRECTED", {"task_id": 11, "stage": "prepare_recirculation_check"})

    mock_fetch.assert_not_awaited()
    mock_execute.assert_awaited_once()
