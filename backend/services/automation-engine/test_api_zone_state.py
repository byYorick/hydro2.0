"""Unit tests for API zone state helpers."""

import pytest

from application.api_zone_state import (
    load_zone_current_levels,
    load_zone_system_config,
)


@pytest.mark.asyncio
async def test_load_zone_system_config_reads_two_tank_from_zone_settings():
    async def _fetch(_query, zone_id):
        assert zone_id == 7
        return [
            {
                "settings": {
                    "automation": {
                        "two_tank": {
                            "tanks_count": 3,
                            "system_type": "ebb_flow",
                            "clean_tank_fill_l": 140,
                            "nutrient_tank_target_l": 95,
                        }
                    }
                }
            }
        ]

    config = await load_zone_system_config(
        zone_id=7,
        task_payload={"config": {"execution": {"tanks_count": 2, "system_type": "drip"}}},
        fetch_fn=_fetch,
    )

    assert config == {
        "tanks_count": 3,
        "system_type": "ebb_flow",
        "clean_tank_capacity_l": 140,
        "nutrient_tank_capacity_l": 95,
    }


@pytest.mark.asyncio
async def test_load_zone_current_levels_uses_telemetry_last():
    async def _fetch(query, zone_id):
        assert zone_id == 3
        # Новый запрос использует telemetry_last JOIN sensors — проверяем ключевые слова
        assert "telemetry_last" in query
        assert "sensors" in query
        return [
            {"sensor_type": "WATER_LEVEL", "sensor_label": "lvl_clean", "value": 48.0},
            {"sensor_type": "WATER_LEVEL", "sensor_label": "lvl_solution", "value": 61.9},
        ]

    levels = await load_zone_current_levels(zone_id=3, fetch_fn=_fetch)

    assert levels == {
        "clean_tank_level_percent": 48.0,
        "nutrient_tank_level_percent": 61.9,
        "ph": None,
        "ec": None,
    }


@pytest.mark.asyncio
async def test_load_zone_current_levels_includes_ph_and_ec():
    async def _fetch(query, zone_id):
        assert zone_id == 5
        return [
            {"sensor_type": "WATER_LEVEL", "sensor_label": "lvl_clean", "value": 72.5},
            {"sensor_type": "WATER_LEVEL", "sensor_label": "lvl_solution", "value": 55.0},
            {"sensor_type": "PH", "sensor_label": "ph", "value": 6.47},
            {"sensor_type": "EC", "sensor_label": "ec", "value": 2.13},
        ]

    levels = await load_zone_current_levels(zone_id=5, fetch_fn=_fetch)

    assert levels["clean_tank_level_percent"] == 72.5
    assert levels["nutrient_tank_level_percent"] == 55.0
    assert levels["ph"] == 6.47
    assert levels["ec"] == 2.1  # round(2.13, 1)


@pytest.mark.asyncio
async def test_load_zone_current_levels_returns_defaults_on_db_error():
    async def _fetch(query, zone_id):
        raise RuntimeError("DB unavailable")

    levels = await load_zone_current_levels(zone_id=1, fetch_fn=_fetch)

    assert levels == {
        "clean_tank_level_percent": None,
        "nutrient_tank_level_percent": None,
        "ph": None,
        "ec": None,
    }


@pytest.mark.asyncio
async def test_load_zone_current_levels_ignores_none_values():
    async def _fetch(query, zone_id):
        return [
            {"sensor_type": "WATER_LEVEL", "sensor_label": "lvl_clean", "value": None},
            {"sensor_type": "PH", "sensor_label": "ph", "value": None},
        ]

    levels = await load_zone_current_levels(zone_id=2, fetch_fn=_fetch)

    assert levels["clean_tank_level_percent"] is None
    assert levels["ph"] is None
