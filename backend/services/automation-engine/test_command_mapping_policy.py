"""Unit tests for command mapping policy helpers."""

from types import SimpleNamespace

from domain.policies.command_mapping_policy import (
    extract_duration_sec,
    resolve_command_name,
    resolve_command_params,
    terminal_status_to_error_code,
)


def _mapping(**kwargs):
    defaults = {
        "duration_target_paths": [("irrigation", "duration_sec")],
        "default_duration_sec": 30.0,
        "state_key": None,
        "cmd_true": None,
        "cmd_false": None,
        "default_state": None,
        "cmd": "run_pump",
        "default_params": {},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_terminal_status_to_error_code_uses_default_for_unknown():
    codes = {"TIMEOUT": "command_timeout", "__default__": "command_effect_not_confirmed"}
    assert terminal_status_to_error_code("TIMEOUT", error_codes=codes) == "command_timeout"
    assert terminal_status_to_error_code("whatever", error_codes=codes) == "command_effect_not_confirmed"


def test_extract_duration_sec_reads_targets_when_config_missing():
    payload = {"targets": {"irrigation": {"duration_sec": 12}}}
    assert extract_duration_sec(payload, _mapping()) == 12.0


def test_resolve_command_name_uses_state_switch():
    mapping = _mapping(state_key="state", cmd_true="start", cmd_false="stop", default_state=False, cmd="noop")
    assert resolve_command_name({"state": True}, mapping) == "start"
    assert resolve_command_name({"state": False}, mapping) == "stop"


def test_resolve_command_params_applies_duration_and_state():
    mapping = _mapping(state_key="state", default_state=False, default_params={"a": 1})
    payload = {"config": {"duration_sec": 2}, "state": True}
    params = resolve_command_params(payload, mapping)
    assert params["duration_ms"] == 2000
    assert params["state"] is True
    assert params["a"] == 1
