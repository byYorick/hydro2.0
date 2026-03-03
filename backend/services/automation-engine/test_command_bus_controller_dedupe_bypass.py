from __future__ import annotations

import pytest

from infrastructure.command_bus_controller import publish_controller_command


class _Validator:
    def validate_command(self, _command):
        return True, None


class _Audit:
    async def audit_command(self, *_args, **_kwargs):
        return None


class _CommandBus:
    def __init__(self) -> None:
        self.validator = _Validator()
        self.audit = _Audit()
        self.tracker = None
        self.reserve_calls = 0
        self.publish_calls = []
        self.zone_events = []

    def _resolve_dedupe_ttl_sec(self, _params):
        return 3600

    async def _reserve_command_dedupe(self, **_kwargs):
        self.reserve_calls += 1
        return {
            "decision": "new",
            "reference_key": "key",
            "scope_key": "scope",
            "dedupe_ttl_sec": 3600,
            "reservation_token": "token",
            "effective_cmd_id": None,
        }

    async def publish_command(self, *_args, **kwargs):
        self.publish_calls.append(kwargs)
        return True

    async def _safe_create_zone_event(self, zone_id, event_type, payload):
        self.zone_events.append((zone_id, event_type, payload))

    async def _bind_dedupe_cmd_id(self, *_args, **_kwargs):
        return None

    async def _complete_command_dedupe(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_publish_controller_command_skips_reserve_when_dedupe_bypass_enabled():
    bus = _CommandBus()
    command = {
        "node_uid": "nd-irrig-1",
        "channel": "pump_main",
        "cmd": "set_relay",
        "params": {"state": True},
        "dedupe_bypass": True,
    }

    success = await publish_controller_command(
        bus,
        zone_id=2,
        command=command,
        context={"task_id": "st-1"},
    )

    assert success is True
    assert bus.reserve_calls == 0
    assert command["dedupe_decision"] == "bypass"
    assert len(bus.publish_calls) == 1
    assert bus.publish_calls[0]["dedupe_state"]["decision"] == "bypass"
    assert any(event_type == "COMMAND_DEDUPE_BYPASSED" for _, event_type, _ in bus.zone_events)


@pytest.mark.asyncio
async def test_publish_controller_command_uses_reserve_when_dedupe_bypass_disabled():
    bus = _CommandBus()
    command = {
        "node_uid": "nd-irrig-1",
        "channel": "pump_main",
        "cmd": "set_relay",
        "params": {"state": True},
        "dedupe_bypass": False,
    }

    success = await publish_controller_command(
        bus,
        zone_id=2,
        command=command,
        context={"task_id": "st-2"},
    )

    assert success is True
    assert bus.reserve_calls == 1
    assert command["dedupe_decision"] == "new"
    assert len(bus.publish_calls) == 1
    assert bus.publish_calls[0]["dedupe_state"]["decision"] == "new"
