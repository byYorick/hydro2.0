import asyncio

import pytest

from infrastructure.command_bus_dedupe import (
    bind_dedupe_cmd_id,
    build_dedupe_reference_key,
    build_dedupe_scope_key,
    complete_command_dedupe,
    evict_conflicting_scope_entries_locked,
    normalized_json_payload,
    prune_dedupe_store_locked,
    reserve_command_dedupe,
)


class _DummyCommandBus:
    def __init__(self) -> None:
        self.command_dedupe_enabled = True
        self.command_dedupe_ttl_sec = 3600
        self._dedupe_store = {}
        self._dedupe_lock = asyncio.Lock()

    _normalized_json_payload = staticmethod(normalized_json_payload)
    _build_dedupe_reference_key = build_dedupe_reference_key
    _build_dedupe_scope_key = build_dedupe_scope_key
    _prune_dedupe_store_locked = prune_dedupe_store_locked
    _evict_conflicting_scope_entries_locked = evict_conflicting_scope_entries_locked
    _reserve_command_dedupe = reserve_command_dedupe
    _bind_dedupe_cmd_id = bind_dedupe_cmd_id
    _complete_command_dedupe = complete_command_dedupe


@pytest.mark.asyncio
async def test_dedupe_blocks_same_command_while_reserved() -> None:
    bus = _DummyCommandBus()
    first = await bus._reserve_command_dedupe(
        zone_id=25,
        node_uid="nd-irrig-e2e",
        channel="valve_clean_supply",
        cmd="set_relay",
        params={"state": True},
        cmd_id="cmd-1",
        dedupe_ttl_sec=3600,
    )
    second = await bus._reserve_command_dedupe(
        zone_id=25,
        node_uid="nd-irrig-e2e",
        channel="valve_clean_supply",
        cmd="set_relay",
        params={"state": True},
        cmd_id="cmd-2",
        dedupe_ttl_sec=3600,
    )
    assert first["decision"] == "new"
    assert second["decision"] == "duplicate_blocked"


@pytest.mark.asyncio
async def test_dedupe_allows_reapply_after_opposite_state_command() -> None:
    bus = _DummyCommandBus()

    first_on = await bus._reserve_command_dedupe(
        zone_id=25,
        node_uid="nd-irrig-e2e",
        channel="valve_clean_supply",
        cmd="set_relay",
        params={"state": True},
        cmd_id="cmd-on-1",
        dedupe_ttl_sec=3600,
    )
    assert first_on["decision"] == "new"
    await bus._complete_command_dedupe(first_on, success=True)

    duplicate_on = await bus._reserve_command_dedupe(
        zone_id=25,
        node_uid="nd-irrig-e2e",
        channel="valve_clean_supply",
        cmd="set_relay",
        params={"state": True},
        cmd_id="cmd-on-2",
        dedupe_ttl_sec=3600,
    )
    assert duplicate_on["decision"] == "duplicate_no_effect"

    off = await bus._reserve_command_dedupe(
        zone_id=25,
        node_uid="nd-irrig-e2e",
        channel="valve_clean_supply",
        cmd="set_relay",
        params={"state": False},
        cmd_id="cmd-off-1",
        dedupe_ttl_sec=3600,
    )
    assert off["decision"] == "new"
    await bus._complete_command_dedupe(off, success=True)

    second_on = await bus._reserve_command_dedupe(
        zone_id=25,
        node_uid="nd-irrig-e2e",
        channel="valve_clean_supply",
        cmd="set_relay",
        params={"state": True},
        cmd_id="cmd-on-3",
        dedupe_ttl_sec=3600,
    )
    assert second_on["decision"] == "new"
