"""Tests for BUG-3 (CO2 target) and BUG-4 (fan conflict prevention) in climate_controller."""
from __future__ import annotations

import pytest

import climate_controller as cc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bindings(*, fan=True, heater=True):
    bindings = {}
    if fan:
        bindings["fan"] = {
            "node_id": 1,
            "node_uid": "climate-1",
            "channel": "relay_0",
            "asset_type": "relay",
            "direction": "actuator",
        }
    if heater:
        bindings["heater"] = {
            "node_id": 2,
            "node_uid": "climate-2",
            "channel": "relay_1",
            "asset_type": "relay",
            "direction": "actuator",
        }
    return bindings


# ---------------------------------------------------------------------------
# BUG-3: CO2 target from recipe used instead of hardcoded threshold
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_co2_low_event_uses_target_from_recipe(monkeypatch):
    events = []

    async def fake_create_zone_event(zone_id, event_type, details):
        events.append((zone_id, event_type, details))

    async def fake_ensure_alert(*args, **kwargs):
        pass

    monkeypatch.setattr(cc, "create_zone_event", fake_create_zone_event)
    monkeypatch.setattr(cc, "ensure_alert", fake_ensure_alert)

    targets = {
        "climate_request": {
            "temp_air_target": 24.0,
            "humidity_target": 65.0,
            "co2_target": 1000.0,
        }
    }
    telemetry = {
        "TEMPERATURE": 24.0,
        "HUMIDITY": 65.0,
        "CO2": 800.0,
    }

    await cc.check_and_control_climate(
        zone_id=1,
        targets=targets,
        telemetry=telemetry,
        bindings=_make_bindings(),
    )

    co2_events = [e for e in events if e[1] == "CO2_LOW"]
    assert len(co2_events) == 1
    assert co2_events[0][2]["threshold"] == 1000.0
    assert co2_events[0][2]["target_co2"] == 1000.0
    assert co2_events[0][2]["co2"] == 800.0


@pytest.mark.asyncio
async def test_co2_no_event_when_above_target(monkeypatch):
    events = []

    async def fake_create_zone_event(zone_id, event_type, details):
        events.append((zone_id, event_type, details))

    async def fake_ensure_alert(*args, **kwargs):
        pass

    monkeypatch.setattr(cc, "create_zone_event", fake_create_zone_event)
    monkeypatch.setattr(cc, "ensure_alert", fake_ensure_alert)

    targets = {
        "climate_request": {
            "temp_air_target": 24.0,
            "co2_target": 600.0,
        }
    }
    telemetry = {
        "TEMPERATURE": 24.0,
        "CO2": 700.0,
    }

    await cc.check_and_control_climate(
        zone_id=1,
        targets=targets,
        telemetry=telemetry,
        bindings=_make_bindings(),
    )

    co2_events = [e for e in events if e[1] == "CO2_LOW"]
    assert len(co2_events) == 0


@pytest.mark.asyncio
async def test_co2_uses_default_threshold_when_no_target(monkeypatch):
    events = []

    async def fake_create_zone_event(zone_id, event_type, details):
        events.append((zone_id, event_type, details))

    async def fake_ensure_alert(*args, **kwargs):
        pass

    monkeypatch.setattr(cc, "create_zone_event", fake_create_zone_event)
    monkeypatch.setattr(cc, "ensure_alert", fake_ensure_alert)

    targets = {
        "climate_request": {
            "temp_air_target": 24.0,
        }
    }
    telemetry = {
        "TEMPERATURE": 24.0,
        "CO2": 350.0,
    }

    await cc.check_and_control_climate(
        zone_id=1,
        targets=targets,
        telemetry=telemetry,
        bindings=_make_bindings(),
    )

    co2_events = [e for e in events if e[1] == "CO2_LOW"]
    assert len(co2_events) == 1
    assert co2_events[0][2]["threshold"] == cc.CO2_LOW_THRESHOLD


# ---------------------------------------------------------------------------
# BUG-4: Fan conflict — temperature block has priority over humidity block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_humidity_does_not_override_temp_fan_command(monkeypatch):
    events = []

    async def fake_create_zone_event(zone_id, event_type, details):
        events.append((zone_id, event_type, details))

    async def fake_ensure_alert(*args, **kwargs):
        pass

    monkeypatch.setattr(cc, "create_zone_event", fake_create_zone_event)
    monkeypatch.setattr(cc, "ensure_alert", fake_ensure_alert)

    bindings = _make_bindings(fan=True, heater=False)
    targets = {
        "climate_request": {
            "temp_air_target": 24.0,
            "humidity_target": 50.0,
        }
    }
    telemetry = {
        "TEMPERATURE": 27.0,
        "HUMIDITY": 70.0,
    }

    commands = await cc.check_and_control_climate(
        zone_id=1,
        targets=targets,
        telemetry=telemetry,
        bindings=bindings,
    )

    fan_commands = [c for c in commands if c["node_uid"] == "climate-1"]
    assert len(fan_commands) == 1, (
        "Only one fan command should be issued (from temperature block); "
        f"got {len(fan_commands)}"
    )
    assert fan_commands[0]["event_type"] == "CLIMATE_COOLING_ON"


@pytest.mark.asyncio
async def test_humidity_fan_command_when_temp_ok(monkeypatch):
    events = []

    async def fake_create_zone_event(zone_id, event_type, details):
        events.append((zone_id, event_type, details))

    async def fake_ensure_alert(*args, **kwargs):
        pass

    monkeypatch.setattr(cc, "create_zone_event", fake_create_zone_event)
    monkeypatch.setattr(cc, "ensure_alert", fake_ensure_alert)

    bindings = _make_bindings(fan=True, heater=False)
    targets = {
        "climate_request": {
            "temp_air_target": 24.0,
            "humidity_target": 50.0,
        }
    }
    telemetry = {
        "TEMPERATURE": 24.0,
        "HUMIDITY": 70.0,
    }

    commands = await cc.check_and_control_climate(
        zone_id=1,
        targets=targets,
        telemetry=telemetry,
        bindings=bindings,
    )

    fan_commands = [c for c in commands if c["node_uid"] == "climate-1"]
    # Temperature block may issue FAN_OFF (temp in range), then humidity needs fan ON.
    # After the fix, fan_commanded set should not block humidity when temp sends FAN_OFF.
    # Actually, FAN_OFF is still a command to the fan, so humidity should not override.
    # Let's verify there's at most 2 commands (FAN_OFF from temp + potentially FAN_ON from humidity).
    # With the fix: temp in range → FAN_OFF is sent, humidity sees fan already commanded → skips.
    fan_on_commands = [c for c in fan_commands if c.get("event_type") == "FAN_ON"]
    fan_off_commands = [c for c in fan_commands if c.get("event_type") == "FAN_OFF"]

    # Temperature is in range, so it sends FAN_OFF.
    # Humidity block sees fan already commanded, so it should NOT send another command.
    assert len(fan_on_commands) == 0, "Humidity block should not override temp block FAN_OFF"


@pytest.mark.asyncio
async def test_humidity_fan_pwm_comes_from_targets(monkeypatch):
    events = []

    async def fake_create_zone_event(zone_id, event_type, details):
        events.append((zone_id, event_type, details))

    async def fake_ensure_alert(*args, **kwargs):
        pass

    monkeypatch.setattr(cc, "create_zone_event", fake_create_zone_event)
    monkeypatch.setattr(cc, "ensure_alert", fake_ensure_alert)

    bindings = _make_bindings(fan=True, heater=False)
    targets = {
        "climate_request": {
            "humidity_target": 50.0,
        },
        "ventilation": {
            "execution": {
                "params": {
                    "humidity_high_pwm": 77,
                }
            }
        },
    }
    telemetry = {
        "HUMIDITY": 70.0,
    }

    commands = await cc.check_and_control_climate(
        zone_id=1,
        targets=targets,
        telemetry=telemetry,
        bindings=bindings,
    )

    fan_pwm_commands = [c for c in commands if c.get("cmd") == "set_pwm" and c.get("node_uid") == "climate-1"]
    assert len(fan_pwm_commands) == 1
    assert fan_pwm_commands[0]["params"]["value"] == 77
