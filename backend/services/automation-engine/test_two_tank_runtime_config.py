from application.two_tank_runtime_config import normalize_command_plan, resolve_two_tank_runtime_config


def _normalize_node_types(raw, default):
    if isinstance(raw, (list, tuple)):
        values = [str(v).strip().lower() for v in raw if str(v).strip()]
        return values or list(default)
    return list(default)


def _resolve_int(raw, default, minimum):
    try:
        value = int(raw)
    except Exception:
        value = int(default)
    return max(value, int(minimum))


def _resolve_float(raw, default, minimum, maximum):
    try:
        value = float(raw)
    except Exception:
        value = float(default)
    return max(float(minimum), min(float(maximum), value))


def _normalize_labels(raw, default):
    if isinstance(raw, (list, tuple)):
        values = [str(v).strip().lower() for v in raw if str(v).strip()]
        return values or list(default)
    return list(default)


def test_normalize_command_plan_filters_invalid_items_and_applies_defaults():
    normalized = normalize_command_plan(
        [
            {"channel": " pump_main ", "cmd": "set_relay", "params": {"state": True}},
            {"channel": "", "cmd": "set_relay"},
            "bad-item",
            {"channel": "valve_solution_fill", "params": {"state": False}, "allow_no_effect": True},
        ],
        default_plan=[{"channel": "fallback", "cmd": "set_relay", "params": {"state": False}}],
        default_node_types=["irrig"],
        default_allow_no_effect=False,
        normalize_node_type_list_fn=_normalize_node_types,
    )

    assert len(normalized) == 2
    assert normalized[0]["channel"] == "pump_main"
    assert normalized[0]["allow_no_effect"] is False
    assert normalized[1]["channel"] == "valve_solution_fill"
    assert normalized[1]["allow_no_effect"] is True


def test_resolve_two_tank_runtime_config_uses_payload_overrides():
    payload = {
        "config": {
            "execution": {
                "startup": {
                    "clean_fill_timeout_sec": 1500,
                    "level_poll_interval_sec": 45,
                    "required_node_types": ["irrig", "relay"],
                },
                "target_ph": 6.1,
                "target_ec": 1.8,
                "two_tank_commands": {
                    "clean_fill_start": [
                        {"channel": "valve_clean_fill", "cmd": "set_relay", "params": {"state": True}}
                    ]
                },
            }
        }
    }

    cfg = resolve_two_tank_runtime_config(
        payload,
        refill_check_delay_sec=60,
        extract_execution_config_fn=lambda p: p.get("config", {}).get("execution", {}),
        normalize_node_type_list_fn=_normalize_node_types,
        resolve_int_fn=_resolve_int,
        resolve_float_fn=_resolve_float,
        normalize_labels_fn=_normalize_labels,
    )

    assert cfg["clean_fill_timeout_sec"] == 1500
    assert cfg["poll_interval_sec"] == 45
    assert cfg["required_node_types"] == ["irrig", "relay"]
    assert cfg["target_ph"] == 6.1
    assert cfg["target_ec"] == 1.8
    assert cfg["commands"]["clean_fill_start"][0]["channel"] == "valve_clean_fill"
