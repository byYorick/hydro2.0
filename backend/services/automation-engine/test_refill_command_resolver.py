"""Unit tests for application.refill_command_resolver helpers."""

import asyncio
from unittest.mock import AsyncMock

from application.refill_command_resolver import resolve_refill_command


def _normalize_list(raw, default):
    if isinstance(raw, (list, tuple)):
        values = [str(item).strip().lower() for item in raw if str(item).strip()]
        return values or list(default)
    return list(default)


def test_resolve_refill_command_returns_none_when_node_not_found():
    result = asyncio.run(
        resolve_refill_command(
            zone_id=1,
            payload={},
            extract_refill_config_fn=lambda _: {},
            normalize_node_type_list_fn=_normalize_list,
            normalize_text_list_fn=_normalize_list,
            resolve_refill_node_fn=AsyncMock(return_value=None),
            resolve_refill_duration_ms_fn=lambda _: 30000,
        )
    )
    assert result is None


def test_resolve_refill_command_sets_default_duration_for_run_pump():
    result = asyncio.run(
        resolve_refill_command(
            zone_id=2,
            payload={},
            extract_refill_config_fn=lambda _: {"cmd": "run_pump"},
            normalize_node_type_list_fn=_normalize_list,
            normalize_text_list_fn=_normalize_list,
            resolve_refill_node_fn=AsyncMock(return_value={"node_uid": "nd-1", "channel": "pump_main"}),
            resolve_refill_duration_ms_fn=lambda _: 45000,
        )
    )
    assert result is not None
    assert result["cmd"] == "run_pump"
    assert result["params"]["duration_ms"] == 45000


def test_resolve_refill_command_sets_default_state_for_set_relay():
    result = asyncio.run(
        resolve_refill_command(
            zone_id=3,
            payload={},
            extract_refill_config_fn=lambda _: {"cmd": "set_relay", "params": {}},
            normalize_node_type_list_fn=_normalize_list,
            normalize_text_list_fn=_normalize_list,
            resolve_refill_node_fn=AsyncMock(return_value={"node_uid": "nd-2", "channel": "valve_clean_fill"}),
            resolve_refill_duration_ms_fn=lambda _: 1000,
        )
    )
    assert result is not None
    assert result["cmd"] == "set_relay"
    assert result["params"]["state"] is True
