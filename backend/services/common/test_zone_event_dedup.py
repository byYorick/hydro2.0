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


@pytest.mark.asyncio
async def test_create_zone_event_skips_duplicate_level_switch_changed_within_window():
    current = {
        "channel": "level_solution_min",
        "state": False,
        "initial": False,
        "payload": {
            "channel": "level_solution_min",
            "state": False,
            "initial": False,
        },
    }

    with patch(
        "common.db.fetch",
        new=AsyncMock(
            return_value=[
                {
                    "payload": {
                        "channel": "level_solution_min",
                        "state": False,
                        "initial": False,
                    }
                }
            ]
        ),
    ) as mock_fetch, patch("common.db.execute", new=AsyncMock()) as mock_execute:
        inserted = await create_zone_event(7, "LEVEL_SWITCH_CHANGED", current)

    assert inserted is False
    mock_fetch.assert_awaited_once()
    mock_execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_zone_event_allows_level_switch_changed_when_state_changes():
    current = {
        "channel": "level_solution_min",
        "state": True,
        "initial": False,
    }

    with patch(
        "common.db.fetch",
        new=AsyncMock(
            return_value=[
                {
                    "payload": {
                        "channel": "level_solution_min",
                        "state": False,
                        "initial": False,
                    }
                }
            ]
        ),
    ) as mock_fetch, patch("common.db.execute", new=AsyncMock()) as mock_execute:
        inserted = await create_zone_event(7, "LEVEL_SWITCH_CHANGED", current)

    assert inserted is True
    mock_fetch.assert_awaited_once()
    mock_execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_zone_event_skips_level_switch_duplicate_even_with_intermediate_other_channel():
    current = {
        "channel": "level_solution_min",
        "state": False,
        "initial": False,
    }

    with patch(
        "common.db.fetch",
        new=AsyncMock(
            return_value=[
                {
                    "payload": {
                        "channel": "level_solution_min",
                        "state": False,
                        "initial": False,
                    }
                }
            ]
        ),
    ) as mock_fetch, patch("common.db.execute", new=AsyncMock()) as mock_execute:
        inserted = await create_zone_event(7, "LEVEL_SWITCH_CHANGED", current)

    assert inserted is False
    mock_fetch.assert_awaited_once()
    fetch_args = mock_fetch.await_args.args
    assert fetch_args[3] == "level_solution_min"
    mock_execute.assert_not_awaited()
