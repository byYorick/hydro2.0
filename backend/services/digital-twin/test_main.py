"""Tests for digital-twin main simulation helpers."""
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from common.schemas import SimulationRequest, SimulationScenario
from main import get_recipe_revision_phases, simulate_zone


@pytest.mark.asyncio
async def test_get_recipe_revision_phases_converts_days_and_targets():
    """Duration in days should be converted to hours and targets normalized."""
    with patch("main.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = [
            [{"id": 10}],
            [
                {
                    "phase_index": 0,
                    "name": "Phase 1",
                    "duration_hours": None,
                    "duration_days": Decimal("2"),
                    "ph_target": Decimal("6.2"),
                    "ec_target": None,
                    "temp_air_target": None,
                    "humidity_target": None,
                    "co2_target": None,
                    "irrigation_mode": None,
                    "irrigation_interval_sec": None,
                    "irrigation_duration_sec": None,
                    "lighting_photoperiod_hours": None,
                    "lighting_start_time": None,
                    "mist_interval_sec": None,
                    "mist_duration_sec": None,
                    "mist_mode": None,
                    "extensions": None,
                }
            ],
        ]

        phases = await get_recipe_revision_phases(3)

    assert len(phases) == 1
    assert phases[0]["duration_hours"] == 48.0
    assert phases[0]["targets"]["ph"] == 6.2


@pytest.mark.asyncio
async def test_simulate_zone_requires_recipe_id():
    """Simulation must require recipe_id in scenario."""
    request = SimulationRequest(
        zone_id=1,
        duration_hours=1,
        step_minutes=30,
        scenario=SimulationScenario(),
    )

    with pytest.raises(HTTPException) as exc:
        await simulate_zone(request)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_simulate_zone_returns_points():
    """Simulation should return points for each step."""
    request = SimulationRequest(
        zone_id=1,
        duration_hours=1,
        step_minutes=30,
        scenario=SimulationScenario(recipe_id=5, initial_state={"ph": 6.0, "ec": 1.2}),
    )
    phases = [
        {
            "phase_index": 0,
            "name": "Phase 1",
            "duration_hours": 2.0,
            "targets": {"ph": 6.5, "ec": 1.4, "temp_air": 22.0, "humidity_air": 60.0},
        }
    ]

    with patch("main.get_recipe_revision_phases", new_callable=AsyncMock) as mock_phases:
        mock_phases.return_value = phases
        result = await simulate_zone(request)

    assert result["status"] == "ok"
    data = result["data"]
    assert data["duration_hours"] == 1
    assert data["step_minutes"] == 30
    assert len(data["points"]) == 2
    assert data["points"][0]["phase_index"] == 0
    assert data["points"][0]["t"] == pytest.approx(0.0)
    assert data["points"][1]["t"] == pytest.approx(0.5)
