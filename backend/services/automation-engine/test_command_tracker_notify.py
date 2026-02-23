from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

import infrastructure.command_tracker as tracker_module
from infrastructure.command_tracker import CommandTracker


def _pending_command(*, zone_id: int = 12, status: str = "QUEUED") -> dict:
    return {
        "cmd_id": "cmd-1",
        "zone_id": zone_id,
        "command": {"cmd": "set_irrigation", "node_uid": "node-1", "channel": "irrigation"},
        "command_type": "set_irrigation",
        "sent_at": datetime.now(timezone.utc),
        "status": status,
        "context": {},
    }


@pytest.mark.asyncio
async def test_notify_payload_confirms_terminal_status(monkeypatch):
    tracker = CommandTracker(command_timeout=10, poll_interval=1)
    tracker.pending_commands["cmd-1"] = _pending_command()

    captured = {}

    async def fake_confirm(cmd_id: str, status: str, response=None, error=None):
        captured["cmd_id"] = cmd_id
        captured["status"] = status
        captured["error"] = error

    monkeypatch.setattr(tracker, "_confirm_command_internal", fake_confirm)

    await tracker._handle_notify_payload(json.dumps({"cmd_id": "cmd-1", "status": "DONE"}))

    assert captured == {"cmd_id": "cmd-1", "status": "DONE", "error": None}


@pytest.mark.asyncio
async def test_notify_payload_ignores_non_terminal_status(monkeypatch):
    tracker = CommandTracker(command_timeout=10, poll_interval=1)
    tracker.pending_commands["cmd-1"] = _pending_command()

    called = {"confirm": 0}

    async def fake_confirm(cmd_id: str, status: str, response=None, error=None):
        called["confirm"] += 1

    monkeypatch.setattr(tracker, "_confirm_command_internal", fake_confirm)

    await tracker._handle_notify_payload(json.dumps({"cmd_id": "cmd-1", "status": "ACK"}))

    assert called["confirm"] == 0


@pytest.mark.asyncio
async def test_start_polling_starts_poll_and_notify_tasks(monkeypatch):
    tracker = CommandTracker(command_timeout=10, poll_interval=1)
    poll_started = asyncio.Event()
    notify_started = asyncio.Event()

    async def fake_poll() -> None:
        poll_started.set()
        while not tracker._shutdown_event.is_set():
            await asyncio.sleep(0.01)

    async def fake_listen() -> None:
        notify_started.set()
        while not tracker._shutdown_event.is_set():
            await asyncio.sleep(0.01)

    monkeypatch.setattr(tracker, "_poll_command_statuses", fake_poll)
    monkeypatch.setattr(tracker, "_listen_command_statuses", fake_listen)

    await tracker.start_polling()
    await asyncio.wait_for(poll_started.wait(), timeout=1.0)
    await asyncio.wait_for(notify_started.wait(), timeout=1.0)

    assert tracker._poll_task is not None
    assert tracker._notify_task is not None
    assert not tracker._poll_task.done()
    assert not tracker._notify_task.done()

    await tracker.stop_polling()

    assert tracker._poll_task is None
    assert tracker._notify_task is None


@pytest.mark.asyncio
async def test_polling_reconciles_terminal_status_when_notify_missed(monkeypatch):
    tracker = CommandTracker(command_timeout=10, poll_interval=0.01)
    tracker.pending_commands["cmd-1"] = _pending_command(status="SENT")

    captured = {}

    async def fake_fetch(query, *args):
        return [
            {
                "cmd_id": "cmd-1",
                "status": "DONE",
                "ack_at": None,
                "failed_at": None,
                "error_message": None,
            }
        ]

    async def fake_confirm(cmd_id: str, status: str, response=None, error=None):
        captured["cmd_id"] = cmd_id
        captured["status"] = status
        captured["error"] = error
        tracker._shutdown_event.set()

    monkeypatch.setattr(tracker_module, "fetch", fake_fetch)
    monkeypatch.setattr(tracker, "_confirm_command_internal", fake_confirm)

    await asyncio.wait_for(tracker._poll_command_statuses(), timeout=1.0)

    assert captured == {"cmd_id": "cmd-1", "status": "DONE", "error": None}
