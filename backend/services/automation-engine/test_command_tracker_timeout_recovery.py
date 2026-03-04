from __future__ import annotations

from datetime import datetime, timezone

import pytest

from infrastructure.command_tracker import CommandTracker


def _pending_command(*, cmd_id: str, zone_id: int = 6, cmd: str = "state") -> dict:
    return {
        "cmd_id": cmd_id,
        "zone_id": zone_id,
        "command": {"cmd": cmd, "node_uid": "nd-test-irrig-1", "channel": "storage_state"},
        "command_type": cmd,
        "sent_at": datetime.now(timezone.utc),
        "status": "SENT",
        "context": {},
    }


@pytest.mark.asyncio
async def test_command_tracker_cold_start_probes_timeout_resolve_once(monkeypatch):
    tracker = CommandTracker(command_timeout=10, poll_interval=1)
    tracker.pending_commands["cmd-1"] = _pending_command(cmd_id="cmd-1")

    resolved_calls = []

    async def fake_send_infra_resolved_alert(**kwargs):
        resolved_calls.append(dict(kwargs))
        return True

    monkeypatch.setattr("common.infra_alerts.send_infra_resolved_alert", fake_send_infra_resolved_alert)

    await tracker._confirm_command_internal("cmd-1", "DONE")

    assert len(resolved_calls) == 1
    assert resolved_calls[0]["code"] == "infra_command_timeout"
    assert resolved_calls[0]["details"]["recovery_probe"] == "cold_start"
    assert tracker._timeout_alert_probe_done_by_zone[6] is True
    assert tracker._timeout_alert_active_by_zone[6] is False

    tracker.pending_commands["cmd-2"] = _pending_command(cmd_id="cmd-2")
    resolved_calls.clear()
    await tracker._confirm_command_internal("cmd-2", "DONE")
    assert resolved_calls == []


@pytest.mark.asyncio
async def test_command_tracker_resolves_timeout_after_real_timeout_failure(monkeypatch):
    tracker = CommandTracker(command_timeout=10, poll_interval=1)
    tracker.pending_commands["cmd-timeout"] = _pending_command(cmd_id="cmd-timeout")

    async def fake_send_infra_alert(**_kwargs):
        return True

    resolved_calls = []

    async def fake_send_infra_resolved_alert(**kwargs):
        resolved_calls.append(dict(kwargs))
        return True

    monkeypatch.setattr("common.infra_alerts.send_infra_alert", fake_send_infra_alert)
    monkeypatch.setattr("common.infra_alerts.send_infra_resolved_alert", fake_send_infra_resolved_alert)

    await tracker._confirm_command_internal("cmd-timeout", "TIMEOUT", error="timeout")
    assert tracker._timeout_alert_active_by_zone[6] is True

    tracker.pending_commands["cmd-done"] = _pending_command(cmd_id="cmd-done")
    await tracker._confirm_command_internal("cmd-done", "DONE")

    assert len(resolved_calls) == 1
    assert resolved_calls[0]["code"] == "infra_command_timeout"
    assert resolved_calls[0]["details"]["recovery_probe"] == "tracked"
    assert tracker._timeout_alert_active_by_zone[6] is False
