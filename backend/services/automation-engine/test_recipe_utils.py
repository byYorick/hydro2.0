"""Tests for recipe_utils module (DB access mocked)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from recipe_utils import (
    advance_phase,
    calculate_current_phase,
    get_phase_targets,
    get_recipe_by_id,
    get_recipe_phases,
)


@pytest.mark.asyncio
async def test_get_recipe_by_id_returns_row() -> None:
    with patch("recipe_utils.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [
            {"id": 5, "name": "R1", "description": "d", "created_at": None},
        ]
        result = await get_recipe_by_id(5)
        assert result == {"id": 5, "name": "R1", "description": "d", "created_at": None}
        mock_fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_recipe_by_id_returns_none_when_empty() -> None:
    with patch("recipe_utils.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []
        assert await get_recipe_by_id(99) is None


@pytest.mark.asyncio
async def test_get_recipe_phases_returns_ordered_rows() -> None:
    with patch("recipe_utils.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [
            {"id": 1, "recipe_id": 10, "phase_index": 0, "name": "A", "duration_hours": 1, "targets": {}, "created_at": None},
        ]
        rows = await get_recipe_phases(10)
        assert len(rows) == 1
        assert rows[0]["phase_index"] == 0


class _ClockTransition(datetime):
    """Подмена `recipe_utils.datetime`: фиксированный «сейчас» 2020-01-03 UTC."""

    _now_aware = datetime(2020, 1, 3, 0, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def fromisoformat(cls, date_string: str) -> datetime:  # noqa: ARG003
        return cls(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def utcnow(cls) -> datetime:
        return datetime(2020, 1, 3, 0, 0, 0)

    @classmethod
    def now(cls, tz=None):  # noqa: ANN001
        if tz is not None:
            return cls._now_aware.astimezone(tz)
        return cls.utcnow()


class _ClockNoTransition(datetime):
    """«Сейчас» 2020-01-01 06:00 UTC — внутри первой 24h фазы."""

    _now_aware = datetime(2020, 1, 1, 6, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def fromisoformat(cls, date_string: str) -> datetime:  # noqa: ARG003
        return cls(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def utcnow(cls) -> datetime:
        return datetime(2020, 1, 1, 6, 0, 0)

    @classmethod
    def now(cls, tz=None):  # noqa: ANN001
        if tz is not None:
            return cls._now_aware.astimezone(tz)
        return cls.utcnow()


@pytest.mark.asyncio
async def test_calculate_current_phase_should_transition() -> None:
    phases_rows = [
        {"id": 1, "recipe_id": 10, "phase_index": 0, "name": "P0", "duration_hours": 24, "targets": {}, "created_at": None},
        {"id": 2, "recipe_id": 10, "phase_index": 1, "name": "P1", "duration_hours": 24, "targets": {}, "created_at": None},
    ]
    instance_row = [
        {
            "id": 1,
            "zone_id": 1,
            "recipe_id": 10,
            "current_phase_index": 0,
            "started_at": "2020-01-01T00:00:00+00:00",
            "updated_at": None,
        },
    ]
    with patch("recipe_utils.fetch", new_callable=AsyncMock) as mock_fetch, patch(
        "recipe_utils.datetime",
        _ClockTransition,
    ):
        mock_fetch.side_effect = [instance_row, phases_rows]

        result = await calculate_current_phase(1)

        assert result is not None
        assert result["should_transition"] is True
        assert result["target_phase_index"] == 1


@pytest.mark.asyncio
async def test_calculate_current_phase_no_transition() -> None:
    phases_rows = [
        {"id": 1, "recipe_id": 10, "phase_index": 0, "name": "P0", "duration_hours": 24, "targets": {}, "created_at": None},
    ]
    instance_row = [
        {
            "id": 1,
            "zone_id": 1,
            "recipe_id": 10,
            "current_phase_index": 0,
            "started_at": "2020-01-01T00:00:00+00:00",
            "updated_at": None,
        },
    ]
    with patch("recipe_utils.fetch", new_callable=AsyncMock) as mock_fetch, patch(
        "recipe_utils.datetime",
        _ClockNoTransition,
    ):
        mock_fetch.side_effect = [instance_row, phases_rows]

        result = await calculate_current_phase(1)

        assert result is not None
        assert result["should_transition"] is False


@pytest.mark.asyncio
async def test_advance_phase_success() -> None:
    with patch("recipe_utils.execute", new_callable=AsyncMock) as mock_exec:
        ok = await advance_phase(7, 2)
        assert ok is True
        mock_exec.assert_awaited_once()


@pytest.mark.asyncio
async def test_advance_phase_returns_false_on_execute_error() -> None:
    with patch("recipe_utils.execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = RuntimeError("db down")
        ok = await advance_phase(7, 2)
        assert ok is False


@pytest.mark.asyncio
async def test_get_phase_targets_returns_payload() -> None:
    instance_row = [
        {
            "id": 1,
            "zone_id": 1,
            "recipe_id": 10,
            "current_phase_index": 0,
            "started_at": datetime(2020, 1, 1),
            "updated_at": None,
        },
    ]
    targets_row = [
        {"targets": {"ph": 6.5}, "phase_name": "Germination", "duration_hours": 168},
    ]
    with patch("recipe_utils.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = [instance_row, targets_row]
        result = await get_phase_targets(1)
        assert result is not None
        assert result["targets"] == {"ph": 6.5}
        assert result["phase_name"] == "Germination"
        assert result["duration_hours"] == 168
