from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_state():
    from handlers.solution_temp_threshold_alerts import reset_solution_temp_alert_state_for_tests

    reset_solution_temp_alert_state_for_tests()
    yield
    reset_solution_temp_alert_state_for_tests()


def test_is_solution_temp_channel_accepts_aliases() -> None:
    from handlers.solution_temp_threshold_alerts import is_solution_temp_channel

    assert is_solution_temp_channel("solution_temp_c")
    assert is_solution_temp_channel("temp_solution")
    assert is_solution_temp_channel("solution_temp")
    assert not is_solution_temp_channel("air_temp_c")


@pytest.mark.asyncio
async def test_raises_high_alert_after_sustained_breach() -> None:
    from handlers.solution_temp_threshold_alerts import process_solution_temp_telemetry_batch

    t0 = datetime(2026, 7, 8, 10, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=11)
    thresholds = {
        1: type("T", (), {"target": 20.0, "min_c": 18.0, "max_c": 22.0})(),
    }

    with patch(
        "handlers.solution_temp_threshold_alerts._load_thresholds_for_zones",
        new=AsyncMock(return_value=thresholds),
    ), patch(
        "handlers.solution_temp_threshold_alerts._publisher.raise_active",
        new=AsyncMock(return_value=True),
    ) as raise_mock, patch(
        "handlers.solution_temp_threshold_alerts._publisher.resolve",
        new=AsyncMock(return_value=True),
    ) as resolve_mock:
        await process_solution_temp_telemetry_batch(
            [{"zone_id": 1, "channel": "solution_temp_c", "value": 24.0, "ts": t0}]
        )
        raise_mock.assert_not_awaited()

        await process_solution_temp_telemetry_batch(
            [{"zone_id": 1, "channel": "solution_temp_c", "value": 24.5, "ts": t1}]
        )
        raise_mock.assert_awaited_once()
        assert raise_mock.await_args.kwargs["code"] == "biz_solution_temp_high"
        resolve_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolves_high_alert_when_back_in_band() -> None:
    from handlers.solution_temp_threshold_alerts import process_solution_temp_telemetry_batch

    t0 = datetime(2026, 7, 8, 10, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=11)
    t2 = t1 + timedelta(minutes=1)
    thresholds = {
        2: type("T", (), {"target": 20.0, "min_c": 18.0, "max_c": 22.0})(),
    }

    with patch(
        "handlers.solution_temp_threshold_alerts._load_thresholds_for_zones",
        new=AsyncMock(return_value=thresholds),
    ), patch(
        "handlers.solution_temp_threshold_alerts._publisher.raise_active",
        new=AsyncMock(return_value=True),
    ), patch(
        "handlers.solution_temp_threshold_alerts._publisher.resolve",
        new=AsyncMock(return_value=True),
    ) as resolve_mock:
        await process_solution_temp_telemetry_batch(
            [{"zone_id": 2, "channel": "solution_temp_c", "value": 25.0, "ts": t0}]
        )
        await process_solution_temp_telemetry_batch(
            [{"zone_id": 2, "channel": "solution_temp_c", "value": 25.0, "ts": t1}]
        )
        await process_solution_temp_telemetry_batch(
            [{"zone_id": 2, "channel": "solution_temp_c", "value": 20.0, "ts": t2}]
        )

        assert resolve_mock.await_count == 1
        assert resolve_mock.await_args.kwargs["code"] == "biz_solution_temp_high"


@pytest.mark.asyncio
async def test_raises_low_alert_after_sustained_breach() -> None:
    from handlers.solution_temp_threshold_alerts import process_solution_temp_telemetry_batch

    t0 = datetime(2026, 7, 8, 10, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=10)
    thresholds = {
        3: type("T", (), {"target": 20.0, "min_c": 18.0, "max_c": 22.0})(),
    }

    with patch(
        "handlers.solution_temp_threshold_alerts._load_thresholds_for_zones",
        new=AsyncMock(return_value=thresholds),
    ), patch(
        "handlers.solution_temp_threshold_alerts._publisher.raise_active",
        new=AsyncMock(return_value=True),
    ) as raise_mock:
        await process_solution_temp_telemetry_batch(
            [{"zone_id": 3, "channel": "solution_temp_c", "value": 16.0, "ts": t0}]
        )
        await process_solution_temp_telemetry_batch(
            [{"zone_id": 3, "channel": "solution_temp_c", "value": 15.5, "ts": t1}]
        )

        assert raise_mock.await_count == 1
        assert raise_mock.await_args.kwargs["code"] == "biz_solution_temp_low"


@pytest.mark.asyncio
async def test_skips_zone_without_thresholds() -> None:
    from handlers.solution_temp_threshold_alerts import process_solution_temp_telemetry_batch

    t0 = datetime(2026, 7, 8, 10, 0, tzinfo=timezone.utc)

    with patch(
        "handlers.solution_temp_threshold_alerts._load_thresholds_for_zones",
        new=AsyncMock(return_value={}),
    ), patch(
        "handlers.solution_temp_threshold_alerts._publisher.raise_active",
        new=AsyncMock(return_value=True),
    ) as raise_mock:
        await process_solution_temp_telemetry_batch(
            [{"zone_id": 9, "channel": "solution_temp_c", "value": 30.0, "ts": t0}]
        )
        raise_mock.assert_not_awaited()
