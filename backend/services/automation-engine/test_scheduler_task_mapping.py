"""Tests for scheduler task mapping configuration."""

from config.scheduler_task_mapping import get_task_mapping


def test_default_mapping_for_irrigation():
    mapping = get_task_mapping("irrigation", {})
    assert mapping.cmd == "run_pump"
    assert "irrigation" in mapping.node_types
    assert mapping.default_duration_sec == 60.0


def test_mapping_override_from_execution_config():
    mapping = get_task_mapping(
        "mist",
        {
            "execution": {
                "cmd": "set_relay",
                "node_types": ["fogger"],
                "params": {"state": False, "pulse_ms": 3000},
                "default_state": False,
            }
        },
    )
    assert mapping.cmd == "set_relay"
    assert mapping.node_types == ("fogger",)
    assert mapping.default_params["pulse_ms"] == 3000
    assert mapping.default_state is False
