from executor.two_tank_runtime_config import (
    default_two_tank_command_plan,
    normalize_command_plan,
    resolve_two_tank_runtime_config,
)


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
            {
                "channel": "valve_solution_fill",
                "params": {"state": False},
                "allow_no_effect": True,
                "dedupe_bypass": False,
            },
        ],
        default_plan=[{"channel": "fallback", "cmd": "set_relay", "params": {"state": False}}],
        default_node_types=["irrig"],
        default_allow_no_effect=False,
        default_dedupe_bypass=True,
        normalize_node_type_list_fn=_normalize_node_types,
    )

    assert len(normalized) == 2
    assert normalized[0]["channel"] == "pump_main"
    assert normalized[0]["allow_no_effect"] is False
    assert normalized[0]["dedupe_bypass"] is True
    assert normalized[1]["channel"] == "valve_solution_fill"
    assert normalized[1]["allow_no_effect"] is True
    assert normalized[1]["dedupe_bypass"] is False


def test_resolve_two_tank_runtime_config_uses_payload_overrides():
    payload = {
        "config": {
            "execution": {
                "startup": {
                    "clean_fill_timeout_sec": 1500,
                    "level_poll_interval_sec": 45,
                    "required_node_types": ["irrig", "relay"],
                    "clean_level_retry_attempts": 9,
                    "clean_level_retry_delay_sec": 0.25,
                    "sensor_mode_stabilization_time_sec": 75,
                    "sensor_mode_telemetry_grace_sec": 120,
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
    assert cfg["startup_clean_level_retry_attempts"] == 9
    assert cfg["startup_clean_level_retry_delay_sec"] == 0.25
    assert cfg["sensor_mode_stabilization_time_sec"] == 75
    assert cfg["sensor_mode_telemetry_grace_sec"] == 120
    assert cfg["target_ph"] == 6.1
    assert cfg["target_ec"] == 1.8
    assert cfg["commands"]["clean_fill_start"][0]["channel"] == "valve_clean_fill"
    assert cfg["commands"]["clean_fill_start"][0]["dedupe_bypass"] is True


def test_default_irrigation_recovery_stop_restores_irrigation_valve_last():
    plan = default_two_tank_command_plan("irrigation_recovery_stop")

    assert plan[-1] == {
        "channel": "valve_irrigation",
        "cmd": "set_relay",
        "params": {"state": True},
    }


def test_resolve_two_tank_runtime_config_warns_when_targets_use_defaults(caplog):
    payload = {"config": {"execution": {}}}

    with caplog.at_level("WARNING", logger="executor.two_tank_runtime_config"):
        cfg = resolve_two_tank_runtime_config(
            payload,
            refill_check_delay_sec=60,
            extract_execution_config_fn=lambda p: p.get("config", {}).get("execution", {}),
            normalize_node_type_list_fn=_normalize_node_types,
            resolve_int_fn=_resolve_int,
            resolve_float_fn=_resolve_float,
            normalize_labels_fn=_normalize_labels,
        )

    assert cfg["target_ph"] == 5.8
    assert cfg["target_ec"] == 1.6
    assert cfg["startup_clean_level_retry_attempts"] == 6
    assert cfg["startup_clean_level_retry_delay_sec"] == 1.0
    assert cfg["sensor_mode_stabilization_time_sec"] == 60
    assert cfg["sensor_mode_telemetry_grace_sec"] == 90
    assert "both target_ph and target_ec resolved to defaults" in caplog.text
