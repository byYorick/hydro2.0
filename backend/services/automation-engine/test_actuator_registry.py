from actuator_registry import ActuatorRegistry


def test_resolve_selects_alias_and_preserves_binding_fields():
    registry = ActuatorRegistry()
    bindings = {
        "pump": {
            "node_id": 11,
            "node_uid": "node-11",
            "node_channel_id": 101,
            "channel": "relay_1",
            "asset_type": "pump",
            "direction": "out",
            "zone_id": 5,
            "ml_per_sec": 12.5,
            "k_ms_per_ml_l": 8.2,
            "pump_calibration": {"slope": 1.1},
        }
    }

    resolved = registry.resolve(zone_id=5, bindings=bindings)

    assert "irrigation_pump" in resolved
    actuator = resolved["irrigation_pump"]
    assert actuator["role"] == "pump"
    assert actuator["node_id"] == 11
    assert actuator["zone_id"] == 5
    assert actuator["ml_per_sec"] == 12.5
    assert actuator["pump_calibration"] == {"slope": 1.1}


def test_resolve_filters_zone_mismatch_fail_closed():
    registry = ActuatorRegistry()
    bindings = {
        "pump": {
            "node_id": 1,
            "zone_id": 99,
        }
    }

    resolved = registry.resolve(zone_id=5, bindings=bindings)

    assert "irrigation_pump" not in resolved


def test_resolve_allows_binding_without_zone_id_for_backward_compatibility():
    registry = ActuatorRegistry()
    bindings = {
        "recirc": {
            "node_id": 7,
            "node_uid": "recirc-7",
            "node_channel_id": 55,
            "asset_type": "pump",
            "direction": "out",
        }
    }

    resolved = registry.resolve(zone_id=2, bindings=bindings)

    assert resolved["recirculation_pump"]["node_uid"] == "recirc-7"
    assert resolved["recirculation_pump"]["channel"] == "default"


def test_resolve_rejects_invalid_binding_zone_value():
    registry = ActuatorRegistry()
    bindings = {
        "fan": {
            "node_id": 3,
            "zone_id": "not-a-number",
        }
    }

    resolved = registry.resolve(zone_id=3, bindings=bindings)

    assert "fan" not in resolved
