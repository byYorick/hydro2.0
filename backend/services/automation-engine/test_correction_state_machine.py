import pytest

from correction_state_machine import CorrectionStateMachine


@pytest.mark.asyncio
async def test_state_machine_emits_transition_event(monkeypatch):
    captured = {}

    async def _fake_create_zone_event(zone_id, event_type, payload):
        captured["zone_id"] = zone_id
        captured["event_type"] = event_type
        captured["payload"] = payload

    monkeypatch.setattr("correction_state_machine.create_zone_event", _fake_create_zone_event)

    sm = CorrectionStateMachine(zone_id=12, metric="ec", state="sense", correlation_id="corr-12")
    await sm.transition("gate", "sense_completed", {"current": 0.8, "target": 1.8})

    assert sm.state == "gate"
    assert captured["zone_id"] == 12
    assert captured["event_type"] == "CORRECTION_STATE_TRANSITION"
    assert captured["payload"]["from_state"] == "sense"
    assert captured["payload"]["to_state"] == "gate"
    assert captured["payload"]["reason_code"] == "sense_completed"
    assert captured["payload"]["correlation_id"] == "corr-12"
