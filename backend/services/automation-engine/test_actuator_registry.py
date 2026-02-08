from actuator_registry import ActuatorRegistry


def test_resolve_strict_ph_ec_roles():
    registry = ActuatorRegistry()
    bindings = {
        "ph_acid_pump": {"node_uid": "nd-1", "channel": "pump_acid"},
        "ph_base_pump": {"node_uid": "nd-1", "channel": "pump_base"},
        "ec_npk_pump": {"node_uid": "nd-2", "channel": "pump_a"},
        "ec_calcium_pump": {"node_uid": "nd-2", "channel": "pump_b"},
        "ec_magnesium_pump": {"node_uid": "nd-2", "channel": "pump_c"},
        "ec_micro_pump": {"node_uid": "nd-2", "channel": "pump_d"},
    }

    resolved = registry.resolve(zone_id=1, bindings=bindings, nodes={})

    assert "ph_acid_pump" in resolved
    assert "ph_base_pump" in resolved
    assert "ec_npk_pump" in resolved
    assert "ec_calcium_pump" in resolved
    assert "ec_magnesium_pump" in resolved
    assert "ec_micro_pump" in resolved


def test_resolve_does_not_accept_legacy_ec_aliases():
    registry = ActuatorRegistry()
    bindings = {
        "pump_nutrient_c": {"node_uid": "nd-legacy", "channel": "pump_c"},
    }

    resolved = registry.resolve(zone_id=1, bindings=bindings, nodes={})

    assert "ec_magnesium_pump" not in resolved
    assert "ec_micro_pump" not in resolved


def test_resolve_does_not_fallback_to_nodes_without_bindings():
    registry = ActuatorRegistry()
    nodes = {
        "ec:pump_a": {
            "node_uid": "nd-ec-a",
            "channel": "pump_a",
            "type": "ec",
        }
    }

    resolved = registry.resolve(zone_id=1, bindings={}, nodes=nodes)

    assert "ec_npk_pump" not in resolved
