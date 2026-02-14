"""Tests for CommandTracker terminal status handling."""

import asyncio
from datetime import datetime

import pytest
from unittest.mock import AsyncMock, patch

from infrastructure.command_tracker import CommandTracker


@pytest.mark.asyncio
async def test_wait_for_command_done_returns_true_only_for_done():
    tracker = CommandTracker(command_timeout=5, poll_interval=1)
    tracker.pending_commands["cmd-done-1"] = {"zone_id": 1, "command_type": "run_pump"}

    with patch.object(
        tracker,
        "_get_command_status_from_db",
        new=AsyncMock(side_effect=["ACK", "DONE"]),
    ), patch.object(tracker, "_confirm_command_internal", new=AsyncMock()) as mock_confirm:
        result = await tracker.wait_for_command_done(
            cmd_id="cmd-done-1",
            timeout_sec=0.2,
            poll_interval_sec=0.01,
        )

    assert result is True
    mock_confirm.assert_awaited_once_with("cmd-done-1", "DONE")


@pytest.mark.asyncio
async def test_wait_for_command_done_treats_no_effect_as_failure():
    tracker = CommandTracker(command_timeout=5, poll_interval=1)
    tracker.pending_commands["cmd-no-effect-1"] = {"zone_id": 1, "command_type": "run_pump"}

    with patch.object(
        tracker,
        "_get_command_status_from_db",
        new=AsyncMock(return_value="NO_EFFECT"),
    ), patch.object(tracker, "_confirm_command_internal", new=AsyncMock()) as mock_confirm:
        result = await tracker.wait_for_command_done(
            cmd_id="cmd-no-effect-1",
            timeout_sec=0.2,
            poll_interval_sec=0.01,
        )

    assert result is False
    mock_confirm.assert_awaited_once_with(
        "cmd-no-effect-1",
        "NO_EFFECT",
        error="Command NO_EFFECT",
    )


@pytest.mark.asyncio
async def test_wait_for_command_done_returns_none_on_timeout():
    tracker = CommandTracker(command_timeout=5, poll_interval=1)

    with patch.object(
        tracker,
        "_get_command_status_from_db",
        new=AsyncMock(return_value="ACK"),
    ):
        result = await tracker.wait_for_command_done(
            cmd_id="cmd-timeout-1",
            timeout_sec=0.03,
            poll_interval_sec=0.01,
        )

    assert result is None


@pytest.mark.asyncio
async def test_check_timeout_confirms_done_when_db_has_terminal_done():
    tracker = CommandTracker(command_timeout=0, poll_interval=1)
    tracker.pending_commands["cmd-done-timeout-check"] = {
        "zone_id": 1,
        "command_type": "run_pump",
        "status": "QUEUED",
        "command": {"cmd": "run_pump"},
    }

    with patch.object(
        tracker,
        "_get_command_status_from_db",
        new=AsyncMock(return_value="DONE"),
    ), patch.object(tracker, "_confirm_command_internal", new=AsyncMock()) as mock_confirm:
        await tracker._check_timeout("cmd-done-timeout-check")

    mock_confirm.assert_awaited_once_with(
        "cmd-done-timeout-check",
        "DONE",
        error=None,
    )


@pytest.mark.asyncio
async def test_check_timeout_confirms_failure_when_db_has_terminal_no_effect():
    tracker = CommandTracker(command_timeout=0, poll_interval=1)
    tracker.pending_commands["cmd-no-effect-timeout-check"] = {
        "zone_id": 1,
        "command_type": "run_pump",
        "status": "QUEUED",
        "command": {"cmd": "run_pump"},
    }

    with patch.object(
        tracker,
        "_get_command_status_from_db",
        new=AsyncMock(return_value="NO_EFFECT"),
    ), patch.object(tracker, "_confirm_command_internal", new=AsyncMock()) as mock_confirm:
        await tracker._check_timeout("cmd-no-effect-timeout-check")

    mock_confirm.assert_awaited_once_with(
        "cmd-no-effect-timeout-check",
        "NO_EFFECT",
        error="Command NO_EFFECT",
    )


@pytest.mark.asyncio
async def test_confirm_command_internal_does_not_cancel_current_timeout_task():
    tracker = CommandTracker(command_timeout=0, poll_interval=1)
    cmd_id = "cmd-self-timeout-task"
    tracker.pending_commands[cmd_id] = {
        "cmd_id": cmd_id,
        "zone_id": 1,
        "command": {"cmd": "run_pump", "node_uid": "nd-irrig-1", "channel": "default"},
        "command_type": "run_pump",
        "sent_at": datetime.utcnow(),
        "status": "QUEUED",
        "context": {},
    }

    with patch.object(tracker, "_emit_failure_alert", new=AsyncMock()) as mock_alert:
        tracker._timeout_tasks[cmd_id] = asyncio.current_task()
        await tracker._confirm_command_internal(cmd_id, "TIMEOUT", error="timeout")

    assert cmd_id not in tracker.pending_commands
    assert cmd_id not in tracker._timeout_tasks
    mock_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_timeout_local_timeout_clears_pending_state():
    tracker = CommandTracker(command_timeout=0, poll_interval=1)
    cmd_id = "cmd-local-timeout-cleanup"
    tracker.pending_commands[cmd_id] = {
        "cmd_id": cmd_id,
        "zone_id": 1,
        "command": {"cmd": "run_pump", "node_uid": "nd-irrig-1", "channel": "default"},
        "command_type": "run_pump",
        "sent_at": datetime.utcnow(),
        "status": "QUEUED",
        "context": {},
    }
    tracker._timeout_tasks[cmd_id] = asyncio.current_task()

    with patch.object(
        tracker,
        "_get_command_status_from_db",
        new=AsyncMock(return_value=None),
    ), patch.object(tracker, "_emit_failure_alert", new=AsyncMock()), \
         patch.object(tracker, "confirm_command_status", new=AsyncMock()) as mock_confirm_status, \
         patch("infrastructure.command_tracker.create_zone_event", new=AsyncMock()) as mock_zone_event:
        await tracker._check_timeout(cmd_id)

    mock_confirm_status.assert_awaited_once_with(cmd_id, "TIMEOUT", error="timeout")
    mock_zone_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_restore_pending_commands_uses_deterministic_order():
    tracker = CommandTracker(command_timeout=5, poll_interval=1)

    with patch("infrastructure.command_tracker.fetch", new=AsyncMock(return_value=[])) as mock_fetch:
        await tracker.restore_pending_commands()

    query = " ".join(str(mock_fetch.await_args.args[0]).split()).lower()
    assert "order by created_at desc, cmd_id desc" in query


@pytest.mark.asyncio
async def test_confirm_command_status_timeout_persists_to_db_and_sends_laravel_ack():
    tracker = CommandTracker(command_timeout=5, poll_interval=1)
    tracker.pending_commands["cmd-timeout-persist"] = {
        "zone_id": 7,
        "command": {"cmd": "run_pump", "node_uid": "nd-irrig-1", "channel": "default"},
        "command_type": "run_pump",
        "sent_at": datetime.utcnow(),
        "status": "ACK",
        "context": {},
    }

    with patch("infrastructure.command_tracker.mark_command_timeout", new=AsyncMock(return_value=True)) as mock_mark, \
         patch("infrastructure.command_tracker.send_status_to_laravel", new=AsyncMock(return_value=True)) as mock_send, \
         patch.object(tracker, "_confirm_command_internal", new=AsyncMock()) as mock_confirm:
        await tracker.confirm_command_status("cmd-timeout-persist", "TIMEOUT", error="closed_loop_timeout")

    mock_mark.assert_awaited_once_with("cmd-timeout-persist")
    mock_send.assert_awaited_once()
    send_args = mock_send.await_args.args
    assert send_args[0] == "cmd-timeout-persist"
    assert send_args[1] == "TIMEOUT"
    assert send_args[2]["zone_id"] == 7
    assert send_args[2]["error_code"] == "TIMEOUT"
    mock_confirm.assert_awaited_once_with(
        "cmd-timeout-persist",
        "TIMEOUT",
        None,
        "closed_loop_timeout",
    )


@pytest.mark.asyncio
async def test_confirm_command_status_send_failed_persists_to_db_and_sends_laravel_ack():
    tracker = CommandTracker(command_timeout=5, poll_interval=1)
    tracker.pending_commands["cmd-send-failed-persist"] = {
        "zone_id": 9,
        "command": {"cmd": "run_pump", "node_uid": "nd-irrig-2", "channel": "pump1"},
        "command_type": "run_pump",
        "sent_at": datetime.utcnow(),
        "status": "QUEUED",
        "context": {},
    }

    with patch("infrastructure.command_tracker.mark_command_send_failed", new=AsyncMock(return_value=True)) as mock_mark, \
         patch("infrastructure.command_tracker.send_status_to_laravel", new=AsyncMock(return_value=True)) as mock_send, \
         patch.object(tracker, "_confirm_command_internal", new=AsyncMock()) as mock_confirm:
        await tracker.confirm_command_status("cmd-send-failed-persist", "SEND_FAILED", error="publish_failed")

    mock_mark.assert_awaited_once_with("cmd-send-failed-persist", error_message="publish_failed")
    mock_send.assert_awaited_once()
    send_args = mock_send.await_args.args
    assert send_args[0] == "cmd-send-failed-persist"
    assert send_args[1] == "SEND_FAILED"
    assert send_args[2]["zone_id"] == 9
    assert send_args[2]["error_code"] == "SEND_FAILED"
    mock_confirm.assert_awaited_once_with(
        "cmd-send-failed-persist",
        "SEND_FAILED",
        None,
        "publish_failed",
    )
