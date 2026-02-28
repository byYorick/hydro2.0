"""Tests for BUG-2: recirculation parameters extraction and controller fix."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.targets_accessor import get_recirculation_params


# ---------------------------------------------------------------------------
# get_recirculation_params unit tests
# ---------------------------------------------------------------------------


def test_recirculation_from_irrigation_section():
    targets = {
        "irrigation": {
            "mode": "SUBSTRATE",
            "interval_sec": 600,
            "recirculation_enabled": True,
            "recirculation_interval_min": 30,
            "recirculation_duration_sec": 120,
        }
    }
    enabled, interval, duration = get_recirculation_params(targets)
    assert enabled is True
    assert interval == 30
    assert duration == 120


def test_recirculation_disabled_in_irrigation():
    targets = {
        "irrigation": {
            "recirculation_enabled": False,
            "recirculation_interval_min": 30,
            "recirculation_duration_sec": 120,
        }
    }
    enabled, interval, duration = get_recirculation_params(targets)
    assert enabled is False
    assert interval == 30
    assert duration == 120


def test_recirculation_from_extensions():
    targets = {
        "irrigation": {"mode": "SUBSTRATE"},
        "extensions": {
            "recirculation": {
                "enabled": True,
                "interval_min": 15,
                "duration_sec": 60,
            }
        },
    }
    enabled, interval, duration = get_recirculation_params(targets)
    assert enabled is True
    assert interval == 15
    assert duration == 60


def test_recirculation_not_configured():
    targets = {
        "irrigation": {"mode": "SUBSTRATE", "interval_sec": 600},
    }
    enabled, interval, duration = get_recirculation_params(targets)
    assert enabled is False
    assert interval is None
    assert duration is None


def test_recirculation_legacy_top_level_ignored():
    targets = {
        "recirculation_enabled": True,
        "recirculation_interval_min": 10,
        "recirculation_duration_sec": 90,
    }
    enabled, interval, duration = get_recirculation_params(targets, zone_id=1)
    assert enabled is False


def test_recirculation_empty_targets():
    enabled, interval, duration = get_recirculation_params({})
    assert enabled is False
    assert interval is None
    assert duration is None


# ---------------------------------------------------------------------------
# Integration: check_and_control_recirculation uses accessor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recirculation_controller_uses_accessor(monkeypatch):
    import irrigation_controller

    fetch_calls = []

    async def fake_fetch(query, *args):
        fetch_calls.append(query)
        if "RECIRCULATION_CYCLE" in query:
            return []
        return []

    async def fake_check_water_level(zone_id):
        return True, 100.0

    async def fake_ensure_alert(*args, **kwargs):
        pass

    monkeypatch.setattr(irrigation_controller, "fetch", fake_fetch)
    monkeypatch.setattr(irrigation_controller, "check_water_level", fake_check_water_level)
    monkeypatch.setattr(irrigation_controller, "ensure_alert", fake_ensure_alert)

    # With recirculation in irrigation section — should work
    targets = {
        "irrigation": {
            "recirculation_enabled": True,
            "recirculation_interval_min": 10,
            "recirculation_duration_sec": 60,
        }
    }
    bindings = {
        "recirculation_pump": {
            "node_id": 1,
            "node_uid": "recirc-1",
            "channel": "relay_0",
            "asset_type": "relay",
            "direction": "actuator",
        }
    }

    result = await irrigation_controller.check_and_control_recirculation(
        zone_id=5,
        targets=targets,
        telemetry={},
        bindings=bindings,
        current_time=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )

    assert result is not None
    assert result["cmd"] == "run_pump"
    assert result["node_uid"] == "recirc-1"


@pytest.mark.asyncio
async def test_recirculation_controller_disabled_when_not_in_targets(monkeypatch):
    import irrigation_controller

    async def fake_fetch(query, *args):
        return []

    async def fake_check_water_level(zone_id):
        return True, 100.0

    async def fake_ensure_alert(*args, **kwargs):
        pass

    monkeypatch.setattr(irrigation_controller, "fetch", fake_fetch)
    monkeypatch.setattr(irrigation_controller, "check_water_level", fake_check_water_level)
    monkeypatch.setattr(irrigation_controller, "ensure_alert", fake_ensure_alert)

    # Legacy format — should NOT work (returns None)
    targets = {
        "recirculation_enabled": True,
        "recirculation_interval_min": 10,
    }
    result = await irrigation_controller.check_and_control_recirculation(
        zone_id=5,
        targets=targets,
        telemetry={},
        bindings={},
        current_time=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert result is None
