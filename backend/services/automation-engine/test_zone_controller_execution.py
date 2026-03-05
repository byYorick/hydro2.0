from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.zone_controller_execution import publish_controller_action_with_event_integrity


@pytest.mark.asyncio
async def test_publish_controller_action_skips_primary_event_on_dedupe():
    emitted_events = []

    async def create_zone_event_safe_fn(*, zone_id, event_type, details, signal_name):
        emitted_events.append(
            {
                "zone_id": zone_id,
                "event_type": event_type,
                "details": dict(details),
                "signal_name": signal_name,
            }
        )
        return True

    async def emit_controller_circuit_open_signal_fn(*_args, **_kwargs):
        raise AssertionError("unexpected circuit-open signal")

    async def publish_controller_command(*_args, **_kwargs):
        return True

    command_gateway = SimpleNamespace(publish_controller_command=publish_controller_command)

    command = {
        "cmd": "set_relay",
        "node_uid": "nd-test-climate-1",
        "channel": "fan_air",
        "cmd_id": "cmd-123",
        "dedupe_decision": "duplicate_no_effect",
        "event_type": "CLIMATE_COOLING_ON",
        "event_details": {"reason": "temp_above_target"},
    }

    ok = await publish_controller_action_with_event_integrity(
        zone_id=4,
        controller_name="climate",
        command=command,
        command_gateway=command_gateway,
        create_zone_event_safe_fn=create_zone_event_safe_fn,
        emit_controller_circuit_open_signal_fn=emit_controller_circuit_open_signal_fn,
        append_correlation_id_fn=lambda details, correlation_id: (
            {**details, "correlation_id": correlation_id} if correlation_id else dict(details)
        ),
    )

    assert ok is True
    assert emitted_events == []
