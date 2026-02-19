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
async def test_load_zone_current_levels_uses_payload_channel():
    async def _fetch(query, zone_id):
        assert zone_id == 3
        assert "payload_json->>'channel'" in query
        return [
            {"channel": "lvl_solution", "payload_json": {"value": 61.9}, "created_at": None},
            {"channel": "lvl_clean", "payload_json": {"details": {"value": 48.0}}, "created_at": None},
        ]

    levels = await load_zone_current_levels(zone_id=3, fetch_fn=_fetch)

    assert levels == {
        "clean_tank_level_percent": 48.0,
        "nutrient_tank_level_percent": 61.9,
    }

