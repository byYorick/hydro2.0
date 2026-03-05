from __future__ import annotations

import logging

from services.zone_state_runtime import sync_sensor_mode_cache_with_workflow_phase


def test_sync_sensor_mode_cache_keeps_cache_for_external_to_external_transition():
    cache = {5: True}

    sync_sensor_mode_cache_with_workflow_phase(
        zone_id=5,
        previous_phase="tank_recirc",
        normalized_phase="tank_filling",
        correction_sensor_mode_state=cache,
        workflow_sensor_mode_external_phases={"tank_filling", "tank_recirc", "irrig_recirc"},
        logger=logging.getLogger("test_zone_state_runtime"),
    )

    assert cache[5] is True


def test_sync_sensor_mode_cache_resets_on_enter_external_boundary():
    cache = {5: False}

    sync_sensor_mode_cache_with_workflow_phase(
        zone_id=5,
        previous_phase="idle",
        normalized_phase="tank_filling",
        correction_sensor_mode_state=cache,
        workflow_sensor_mode_external_phases={"tank_filling", "tank_recirc", "irrig_recirc"},
        logger=logging.getLogger("test_zone_state_runtime"),
    )

    assert 5 not in cache


def test_sync_sensor_mode_cache_resets_on_leave_external_boundary():
    cache = {5: True}

    sync_sensor_mode_cache_with_workflow_phase(
        zone_id=5,
        previous_phase="tank_recirc",
        normalized_phase="idle",
        correction_sensor_mode_state=cache,
        workflow_sensor_mode_external_phases={"tank_filling", "tank_recirc", "irrig_recirc"},
        logger=logging.getLogger("test_zone_state_runtime"),
    )

    assert 5 not in cache

