from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.zone_controller_processors import process_irrigation_controller


def _logger_stub():
    return SimpleNamespace(
        debug=lambda *_args, **_kwargs: None,
        info=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
    )


@pytest.mark.asyncio
async def test_process_irrigation_controller_checks_safety_for_pump_node_and_resolves_alert():
    safety_calls = []
    resolved_calls = []
    published_calls = []

    async def check_and_control_irrigation_fn(*_args, **_kwargs):
        return {
            "node_uid": "nd-irrig-1",
            "channel": "pump_main",
            "cmd": "run_pump",
            "params": {"duration_ms": 60000},
            "event_type": "IRRIGATION_STARTED",
        }

    async def can_run_pump_fn(zone_id, pump_channel, node_id=None):
        safety_calls.append(
            {
                "zone_id": zone_id,
                "pump_channel": pump_channel,
                "node_id": node_id,
            }
        )
        return True, None

    async def send_infra_alert_fn(**_kwargs):
        raise AssertionError("unexpected infra alert")

    async def send_infra_resolved_alert_fn(**kwargs):
        resolved_calls.append(dict(kwargs))
        return True

    async def publish_controller_action_with_event_integrity_fn(**kwargs):
        published_calls.append(dict(kwargs))
        return True

    await process_irrigation_controller(
        zone_id=6,
        targets={},
        telemetry={},
        capabilities={"irrigation_control": True},
        workflow_phase="idle",
        bindings={},
        actuators={
            "main_pump": {
                "node_id": 2,
                "node_uid": "nd-irrig-1",
                "channel": "pump_main",
            }
        },
        current_time=None,
        time_scale=None,
        sim_clock=None,
        check_and_control_irrigation_fn=check_and_control_irrigation_fn,
        can_run_pump_fn=can_run_pump_fn,
        send_infra_alert_fn=send_infra_alert_fn,
        send_infra_resolved_alert_fn=send_infra_resolved_alert_fn,
        publish_controller_action_with_event_integrity_fn=publish_controller_action_with_event_integrity_fn,
        logger=_logger_stub(),
    )

    assert len(safety_calls) == 1
    assert safety_calls[0]["node_id"] == 2
    assert len(resolved_calls) == 1
    assert resolved_calls[0]["details"]["node_id"] == 2
    assert len(published_calls) == 1


@pytest.mark.asyncio
async def test_process_irrigation_controller_emits_blocked_alert_and_skips_publish():
    alert_calls = []
    published_calls = []

    async def check_and_control_irrigation_fn(*_args, **_kwargs):
        return {
            "node_uid": "nd-irrig-1",
            "channel": "pump_main",
            "cmd": "run_pump",
            "params": {"duration_ms": 60000},
            "event_type": "IRRIGATION_STARTED",
        }

    async def can_run_pump_fn(_zone_id, _pump_channel, node_id=None):
        _ = node_id
        return False, "MCU offline: Node 3 offline: no telemetry data"

    async def send_infra_alert_fn(**kwargs):
        alert_calls.append(dict(kwargs))
        return True

    async def send_infra_resolved_alert_fn(**_kwargs):
        raise AssertionError("unexpected resolved alert")

    async def publish_controller_action_with_event_integrity_fn(**kwargs):
        published_calls.append(dict(kwargs))
        return True

    await process_irrigation_controller(
        zone_id=6,
        targets={},
        telemetry={},
        capabilities={"irrigation_control": True},
        workflow_phase="idle",
        bindings={},
        actuators={
            "main_pump": {
                "node_id": 2,
                "node_uid": "nd-irrig-1",
                "channel": "pump_main",
            }
        },
        current_time=None,
        time_scale=None,
        sim_clock=None,
        check_and_control_irrigation_fn=check_and_control_irrigation_fn,
        can_run_pump_fn=can_run_pump_fn,
        send_infra_alert_fn=send_infra_alert_fn,
        send_infra_resolved_alert_fn=send_infra_resolved_alert_fn,
        publish_controller_action_with_event_integrity_fn=publish_controller_action_with_event_integrity_fn,
        logger=_logger_stub(),
    )

    assert len(alert_calls) == 1
    assert alert_calls[0]["code"] == "infra_irrigation_pump_blocked"
    assert "MCU offline" in str(alert_calls[0]["details"]["reason"])
    assert published_calls == []
