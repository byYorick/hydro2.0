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


def test_resolve_skips_binding_from_other_zone_when_zone_id_present():
    registry = ActuatorRegistry()
    bindings = {
        "ph_acid_pump": {"node_uid": "nd-1", "channel": "pump_acid", "zone_id": 2},
    }

    resolved = registry.resolve(zone_id=1, bindings=bindings, nodes={})

    assert "ph_acid_pump" not in resolved


def test_resolve_accepts_binding_without_zone_id_for_backward_compatibility():
    registry = ActuatorRegistry()
    bindings = {
        "ph_acid_pump": {"node_uid": "nd-1", "channel": "pump_acid"},
    }

    resolved = registry.resolve(zone_id=1, bindings=bindings, nodes={})

    assert "ph_acid_pump" in resolved
    assert resolved["ph_acid_pump"]["zone_id"] is None


def test_resolve_continues_alias_scan_when_first_alias_zone_mismatch():
    registry = ActuatorRegistry()
    bindings = {
        "main_pump": {"node_uid": "nd-main", "channel": "pump_1", "zone_id": 2},
        "irrigation_pump": {"node_uid": "nd-irrig", "channel": "pump_1", "zone_id": 1},
    }

    resolved = registry.resolve(zone_id=1, bindings=bindings, nodes={})

    assert "irrigation_pump" in resolved
    assert resolved["irrigation_pump"]["node_uid"] == "nd-irrig"
