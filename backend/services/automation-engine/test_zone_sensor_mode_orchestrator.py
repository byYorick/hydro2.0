from __future__ import annotations

import logging

import pytest

from services.resilience_contract import (
    REASON_CORRECTION_GATING_PASSED,
    REASON_CORRECTION_STALE_FLAGS,
)
from services.zone_automation_constants import SENSOR_MODE_POLICY
from services.zone_sensor_mode_orchestrator import (
    resolve_correction_sensor_nodes,
    resolve_sensor_mode_action,
    set_sensor_mode,
)


class _CommandGateway:
    def __init__(self) -> None:
        self.calls = []

    async def publish_controller_command(self, zone_id, command):
        self.calls.append({"zone_id": zone_id, "command": dict(command)})
        return True


@pytest.mark.asyncio
async def test_set_sensor_mode_keeps_dedupe_enabled_for_sensor_commands():
    gateway = _CommandGateway()
    cache = {}
    logger = logging.getLogger("test_zone_sensor_mode")
    nodes = {
        "ph": {"node_uid": "nd-ph-1", "type": "ph"},
        "ec": {"node_uid": "nd-ec-1", "type": "ec"},
    }

    async def _noop_emit(*_args, **_kwargs):
        return None

    await set_sensor_mode(
        zone_id=2,
        nodes=nodes,
        activate=True,
        reason=REASON_CORRECTION_STALE_FLAGS,
        command_gateway=gateway,
        correction_sensor_mode_state=cache,
        emit_controller_circuit_open_signal_fn=_noop_emit,
        logger=logger,
        resolve_correction_sensor_nodes_fn=resolve_correction_sensor_nodes,
    )

    assert len(gateway.calls) == 2
    for call in gateway.calls:
        assert call["zone_id"] == 2
        assert call["command"]["channel"] == "system"
        assert call["command"]["cmd"] == "activate_sensor_mode"
        assert call["command"].get("dedupe_bypass") is False
        assert call["command"]["params"] == {"stabilization_time_sec": 60}


def test_resolve_sensor_mode_action_stale_flags_prefers_activate():
    action = resolve_sensor_mode_action(
        REASON_CORRECTION_STALE_FLAGS,
        can_run=False,
        sensor_mode_policy=SENSOR_MODE_POLICY,
    )
    assert action == "activate"


def test_resolve_sensor_mode_action_gating_passed_prefers_activate():
    action = resolve_sensor_mode_action(
        REASON_CORRECTION_GATING_PASSED,
        can_run=True,
        sensor_mode_policy=SENSOR_MODE_POLICY,
    )
    assert action == "activate"
