"""Unit tests for application.two_tank_runtime_config helpers."""

from application.two_tank_runtime_config import (
    default_two_tank_command_plan,
    normalize_command_plan,
    resolve_two_tank_runtime_config,
)


def _normalize_node_type_list(raw, default):
    if isinstance(raw, (list, tuple)):
        values = [str(item).strip().lower() for item in raw if str(item).strip()]
        return values or list(default)
    return list(default)


def _resolve_int(raw, default, minimum):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _resolve_float(raw, default, minimum, maximum):
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _normalize_labels(raw, default):
    if isinstance(raw, (list, tuple)):
        values = [str(item).strip().lower() for item in raw if str(item).strip()]
        return values or list(default)
    return list(default)


def test_default_two_tank_command_plan_has_expected_start_command():
    plan = default_two_tank_command_plan("clean_fill_start")
    assert plan == [{"channel": "valve_clean_fill", "cmd": "set_relay", "params": {"state": True}}]


def test_normalize_command_plan_applies_defaults_and_filters_invalid_items():
    normalized = normalize_command_plan(
        raw=[
            {"channel": "PUMP_MAIN", "params": {"state": True}},
            {"channel": " ", "cmd": "set_relay"},
            123,
        ],
        default_plan=[],
        default_node_types=("irrig",),
        default_allow_no_effect=True,
        normalize_node_type_list_fn=_normalize_node_type_list,
    )
    assert len(normalized) == 1
    assert normalized[0]["channel"] == "pump_main"
    assert normalized[0]["cmd"] == "set_relay"
    assert normalized[0]["node_types"] == ["irrig"]
    assert normalized[0]["allow_no_effect"] is True


def test_resolve_two_tank_runtime_config_uses_payload_targets_and_runtime_defaults():
    payload = {
        "config": {
            "execution": {
                "startup": {
                    "required_node_types": ["irrig", "mix"],
                    "level_poll_interval_sec": 25,
                },
                "target_ec": 2.0,
                "prepare_tolerance": {"ec_pct": 30.0},
                "two_tank_commands": {
                    "clean_fill_start": [{"channel": "valve_a", "cmd": "set_relay", "params": {"state": True}}],
                },
            }
        },
        "targets": {
            "ph": {"target": 6.2},
            "nutrition": {"components": {"npk": {"ratio_pct": 50}}},
        },
    }

    result = resolve_two_tank_runtime_config(
        payload,
        refill_check_delay_sec=60,
        extract_execution_config_fn=lambda src: src.get("config", {}).get("execution", {}),
        normalize_node_type_list_fn=_normalize_node_type_list,
        resolve_int_fn=_resolve_int,
        resolve_float_fn=_resolve_float,
        normalize_labels_fn=_normalize_labels,
    )

    assert result["required_node_types"] == ["irrig", "mix"]
    assert result["poll_interval_sec"] == 25
    assert result["target_ph"] == 6.2
    assert result["target_ec"] == 2.0
    assert result["nutrient_npk_ratio_pct"] == 50.0
    assert result["target_ec_prepare"] == 1.0
    assert result["prepare_tolerance"]["ec_pct"] == 30.0
    assert result["commands"]["clean_fill_start"][0]["channel"] == "valve_a"
    assert result["irrigation_recovery_max_attempts"] == 2
    assert result["irrigation_recovery_retry_timeout_multiplier"] == 1.5
    assert result["irr_state_max_age_sec"] == 30
    assert result["clean_min_labels"] == ["level_clean_min", "clean_min"]
    assert result["solution_min_labels"] == ["level_solution_min", "solution_min"]
