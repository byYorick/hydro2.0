"""Tests for command_response handling."""
import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_handle_command_response_existing_command_sends_status():
    """Existing command should forward status to Laravel without creating stub."""
    from mqtt_handlers import handle_command_response
    from common.command_status_queue import CommandStatus

    topic = "hydro/gh-1/zn-1/nd-irrig-1/pump1/command_response"
    payload = json.dumps(
        {"cmd_id": "cmd-1", "status": "DONE", "ts": 1737979200000, "details": {"foo": "bar"}}
    ).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.execute", new_callable=AsyncMock) as mock_execute, \
         patch("mqtt_handlers.send_status_to_laravel", new_callable=AsyncMock) as mock_send, \
         patch("mqtt_handlers.record_simulation_event", new_callable=AsyncMock) as mock_record, \
         patch("mqtt_handlers.COMMAND_RESPONSE_RECEIVED") as mock_received, \
         patch("mqtt_handlers.COMMAND_RESPONSE_ERROR") as mock_error:
        mock_fetch.return_value = [{"status": "QUEUED", "zone_id": 12, "cmd": "irrigation"}]
        mock_send.return_value = True

        await handle_command_response(topic, payload)

        mock_received.inc.assert_called_once()
        mock_error.inc.assert_not_called()
        mock_execute.assert_not_called()
        mock_send.assert_awaited_once()

        call_args = mock_send.call_args[0]
        assert call_args[0] == "cmd-1"
        assert call_args[1] == CommandStatus.DONE
        details = call_args[2]
        assert details["foo"] == "bar"
        assert details["raw_status"] == "DONE"
        assert details["response_ts"] == 1737979200000
        assert details["node_uid"] == "nd-irrig-1"
        assert details["channel"] == "pump1"
        assert details["gh_uid"] == "gh-1"
        mock_record.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_command_response_creates_stub_for_missing_command():
    """Missing command should create stub record before reporting status."""
    from mqtt_handlers import handle_command_response
    from common.command_status_queue import CommandStatus

    topic = "hydro/gh-1/zn-1/nd-irrig-1/pump1/command_response"
    payload = json.dumps({"cmd_id": "cmd-2", "status": "ACK", "ts": 1737979200001}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.execute", new_callable=AsyncMock) as mock_execute, \
         patch("mqtt_handlers.send_status_to_laravel", new_callable=AsyncMock) as mock_send, \
         patch("mqtt_handlers.record_simulation_event", new_callable=AsyncMock) as mock_record, \
         patch("mqtt_handlers.COMMAND_RESPONSE_RECEIVED") as mock_received:
        mock_fetch.side_effect = [
            [],
            [{"id": 5, "zone_id": 9}],
        ]
        mock_send.return_value = True

        await handle_command_response(topic, payload)

        mock_received.inc.assert_called_once()
        mock_execute.assert_called_once()
        insert_args = mock_execute.call_args[0]
        assert insert_args[1] == 9
        assert insert_args[2] == 5
        assert insert_args[3] == "pump1"
        assert insert_args[4] == "unknown"
        assert insert_args[5] == {}
        assert insert_args[6] == CommandStatus.ACK.value
        assert insert_args[7] == "device"
        assert insert_args[8] == "cmd-2"
        mock_send.assert_awaited_once()
        mock_record.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_command_response_creates_preterminal_stub_for_terminal_status():
    """Missing command with terminal response must insert ACK stub before forwarding terminal status."""
    from mqtt_handlers import handle_command_response
    from common.command_status_queue import CommandStatus

    topic = "hydro/gh-1/zn-1/nd-irrig-1/pump1/command_response"
    payload = json.dumps({"cmd_id": "cmd-2-terminal", "status": "DONE", "ts": 1737979200010}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.execute", new_callable=AsyncMock) as mock_execute, \
         patch("mqtt_handlers.send_status_to_laravel", new_callable=AsyncMock) as mock_send, \
         patch("mqtt_handlers.record_simulation_event", new_callable=AsyncMock) as mock_record:
        mock_fetch.side_effect = [
            [],
            [{"id": 5, "zone_id": 9}],
        ]
        mock_send.return_value = True

        await handle_command_response(topic, payload)

        mock_execute.assert_called_once()
        insert_args = mock_execute.call_args[0]
        # Stub должен вставляться как ACK, а terminal DONE отправляется отдельно в Laravel.
        assert insert_args[6] == CommandStatus.ACK.value
        mock_send.assert_awaited_once()
        assert mock_send.call_args[0][1] == CommandStatus.DONE
        mock_record.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_command_response_timeout_uses_ack_stub_for_unknown_cmd():
    from mqtt_handlers import handle_command_response
    from common.command_status_queue import CommandStatus

    topic = "hydro/gh-1/zn-1/nd-irrig-1/pump1/command_response"
    payload = json.dumps({"cmd_id": "cmd-timeout-missing", "status": "TIMEOUT", "ts": 1737979200010}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.execute", new_callable=AsyncMock) as mock_execute, \
         patch("mqtt_handlers.send_status_to_laravel", new_callable=AsyncMock) as mock_send, \
         patch("mqtt_handlers.record_simulation_event", new_callable=AsyncMock):
        mock_fetch.side_effect = [
            [],
            [{"id": 5, "zone_id": 9}],
        ]
        mock_send.return_value = True

        await handle_command_response(topic, payload)

        insert_args = mock_execute.call_args[0]
        assert insert_args[6] == CommandStatus.ACK.value
        assert mock_send.call_args[0][1] == CommandStatus.TIMEOUT


@pytest.mark.asyncio
async def test_handle_command_response_missing_cmd_id():
    """Missing cmd_id should be rejected and not forwarded."""
    from mqtt_handlers import handle_command_response

    topic = "hydro/gh-1/zn-1/nd-irrig-1/pump1/command_response"
    payload = json.dumps({"status": "ACK", "ts": 1737979200002}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.send_status_to_laravel", new_callable=AsyncMock) as mock_send, \
         patch("mqtt_handlers.record_simulation_event", new_callable=AsyncMock) as mock_record, \
         patch("mqtt_handlers.COMMAND_RESPONSE_ERROR") as mock_error:
        await handle_command_response(topic, payload)

        mock_error.inc.assert_called_once()
        mock_fetch.assert_not_called()
        mock_send.assert_not_called()
        mock_record.assert_not_called()


@pytest.mark.asyncio
async def test_handle_command_response_unknown_status():
    """Unknown status should be rejected and not forwarded."""
    from mqtt_handlers import handle_command_response

    topic = "hydro/gh-1/zn-1/nd-irrig-1/pump1/command_response"
    payload = json.dumps({"cmd_id": "cmd-3", "status": "UNKNOWN", "ts": 1737979200003}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.send_status_to_laravel", new_callable=AsyncMock) as mock_send, \
         patch("mqtt_handlers.record_simulation_event", new_callable=AsyncMock) as mock_record, \
         patch("mqtt_handlers.COMMAND_RESPONSE_ERROR") as mock_error:
        await handle_command_response(topic, payload)

        mock_error.inc.assert_called_once()
        mock_fetch.assert_not_called()
        mock_send.assert_not_called()
        mock_record.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_status", ["ACCEPTED", "FAILED"])
async def test_handle_command_response_legacy_status_rejected(legacy_status):
    """Legacy статусы должны отклоняться как невалидные."""
    from mqtt_handlers import handle_command_response

    topic = "hydro/gh-1/zn-1/nd-irrig-1/pump1/command_response"
    payload = json.dumps(
        {"cmd_id": "cmd-legacy", "status": legacy_status, "ts": 1737979200004}
    ).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.send_status_to_laravel", new_callable=AsyncMock) as mock_send, \
         patch("mqtt_handlers.record_simulation_event", new_callable=AsyncMock) as mock_record, \
         patch("mqtt_handlers.COMMAND_RESPONSE_ERROR") as mock_error:
        await handle_command_response(topic, payload)

        mock_error.inc.assert_called_once()
        mock_fetch.assert_not_called()
        mock_send.assert_not_called()
        mock_record.assert_not_called()


@pytest.mark.asyncio
async def test_handle_command_response_no_effect_records_warning_level():
    """NO_EFFECT должен логироваться как warning для синхронизации с automation-engine."""
    from mqtt_handlers import handle_command_response

    topic = "hydro/gh-1/zn-1/nd-irrig-1/pump1/command_response"
    payload = json.dumps({"cmd_id": "cmd-4", "status": "NO_EFFECT", "ts": 1737979200005}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.send_status_to_laravel", new_callable=AsyncMock) as mock_send, \
         patch("mqtt_handlers.record_simulation_event", new_callable=AsyncMock) as mock_record:
        mock_fetch.return_value = [{"status": "SENT", "zone_id": 12, "cmd": "irrigation"}]
        mock_send.return_value = True

        await handle_command_response(topic, payload)

        mock_record.assert_awaited_once()
        assert mock_record.await_args.kwargs["status"] == "no_effect"
        assert mock_record.await_args.kwargs["level"] == "warning"


@pytest.mark.asyncio
async def test_handle_command_response_invalid_details_type_rejected():
    """String details must be rejected by fail-closed contract."""
    from mqtt_handlers import handle_command_response

    topic = "hydro/gh-1/zn-1/nd-irrig-1/pump1/command_response"
    payload = json.dumps(
        {"cmd_id": "cmd-5", "status": "ERROR", "ts": 1737979200006, "details": "Pump jammed"}
    ).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.send_status_to_laravel", new_callable=AsyncMock) as mock_send, \
         patch("mqtt_handlers.record_simulation_event", new_callable=AsyncMock) as mock_record, \
         patch("mqtt_handlers.COMMAND_RESPONSE_ERROR") as mock_error:
        mock_fetch.return_value = [{"status": "SENT", "zone_id": 12, "cmd": "irrigation"}]

        await handle_command_response(topic, payload)

        mock_error.inc.assert_called_once()
        mock_send.assert_not_called()
        mock_record.assert_not_called()


@pytest.mark.asyncio
async def test_handle_command_response_missing_details_keeps_metadata():
    """Missing details should still produce metadata-only payload."""
    from mqtt_handlers import handle_command_response
    from common.command_status_queue import CommandStatus

    topic = "hydro/gh-1/zn-1/nd-irrig-1/pump1/command_response"
    payload = json.dumps({"cmd_id": "cmd-6", "status": "ACK", "ts": 1737979200007}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.send_status_to_laravel", new_callable=AsyncMock) as mock_send, \
         patch("mqtt_handlers.record_simulation_event", new_callable=AsyncMock) as mock_record:
        mock_fetch.return_value = [{"status": "SENT", "zone_id": 12, "cmd": "irrigation"}]
        mock_send.return_value = True

        await handle_command_response(topic, payload)

        mock_send.assert_awaited_once()
        call_args = mock_send.call_args[0]
        assert call_args[0] == "cmd-6"
        assert call_args[1] == CommandStatus.ACK
        details = call_args[2]
        assert details["raw_status"] == "ACK"
        assert details["response_ts"] == 1737979200007
        assert details["node_uid"] == "nd-irrig-1"
        assert details["channel"] == "pump1"
        assert details["gh_uid"] == "gh-1"
        assert "message" not in details
        mock_record.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_command_response_uses_top_level_message_as_error_message():
    from mqtt_handlers import handle_command_response
    from common.command_status_queue import CommandStatus

    topic = "hydro/gh-1/zn-1/nd-irrig-1/pump1/command_response"
    payload = json.dumps(
        {
            "cmd_id": "cmd-error-message",
            "status": "ERROR",
            "message": "Command failed: invalid channel",
            "ts": 1737979200008,
        }
    ).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.send_status_to_laravel", new_callable=AsyncMock) as mock_send, \
         patch("mqtt_handlers.record_simulation_event", new_callable=AsyncMock) as mock_record:
        mock_fetch.return_value = [{"status": "SENT", "zone_id": 12, "cmd": "set_relay"}]
        mock_send.return_value = True

        await handle_command_response(topic, payload)

        mock_send.assert_awaited_once()
        call_args = mock_send.call_args[0]
        assert call_args[0] == "cmd-error-message"
        assert call_args[1] == CommandStatus.ERROR
        details = call_args[2]
        assert details["error_message"] == "Command failed: invalid channel"
        mock_record.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_command_response_missing_ts_rejected():
    """Missing ts should be rejected and not forwarded."""
    from mqtt_handlers import handle_command_response

    topic = "hydro/gh-1/zn-1/nd-irrig-1/pump1/command_response"
    payload = json.dumps({"cmd_id": "cmd-no-ts", "status": "ACK"}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.send_status_to_laravel", new_callable=AsyncMock) as mock_send, \
         patch("mqtt_handlers.record_simulation_event", new_callable=AsyncMock) as mock_record, \
         patch("mqtt_handlers.COMMAND_RESPONSE_ERROR") as mock_error:
        await handle_command_response(topic, payload)

        mock_error.inc.assert_called_once()
        mock_fetch.assert_not_called()
        mock_send.assert_not_called()
        mock_record.assert_not_called()


@pytest.mark.asyncio
async def test_handle_command_response_state_persists_irr_snapshot_event():
    from mqtt_handlers import handle_command_response

    topic = "hydro/gh-1/zn-1/nd-irrig-1/pump_main/command_response"
    payload = json.dumps(
        {
            "cmd_id": "cmd-state-1",
            "status": "DONE",
            "ts": 1737979200012,
            "details": {
                "snapshot": {
                    "clean_level_max": True,
                    "clean_level_min": True,
                    "solution_level_max": False,
                    "solution_level_min": True,
                    "valve_clean_fill": False,
                    "valve_clean_supply": True,
                    "valve_solution_fill": True,
                    "valve_solution_supply": False,
                    "valve_irrigation": False,
                    "pump_main": True,
                }
            },
        }
    ).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.send_status_to_laravel", new_callable=AsyncMock) as mock_send, \
         patch("mqtt_handlers.record_simulation_event", new_callable=AsyncMock), \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event:
        mock_fetch.return_value = [{"status": "SENT", "zone_id": 7, "cmd": "state"}]
        mock_send.return_value = True

        await handle_command_response(topic, payload)

        mock_create_zone_event.assert_awaited_once()
        args = mock_create_zone_event.await_args.args
        assert args[0] == 7
        assert args[1] == "IRR_STATE_SNAPSHOT"
        assert args[2]["snapshot"]["clean_level_max"] is True
        assert args[2]["snapshot"]["solution_level_max"] is False


@pytest.mark.asyncio
async def test_handle_command_response_storage_state_persists_snapshot_even_without_state_cmd():
    from mqtt_handlers import handle_command_response

    topic = "hydro/gh-1/zn-1/nd-irrig-1/storage_state/command_response"
    payload = json.dumps(
        {
            "cmd_id": "cmd-storage-state-1",
            "status": "DONE",
            "ts": 1737979200013,
            "details": {
                "snapshot": {
                    "clean_level_max": True,
                    "clean_level_min": True,
                    "solution_level_max": False,
                    "solution_level_min": True,
                    "valve_clean_fill": False,
                    "valve_clean_supply": True,
                    "valve_solution_fill": True,
                    "valve_solution_supply": False,
                    "pump_main": True,
                }
            },
        }
    ).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.send_status_to_laravel", new_callable=AsyncMock) as mock_send, \
         patch("mqtt_handlers.record_simulation_event", new_callable=AsyncMock), \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event:
        # cmd != state, но канал storage_state — snapshot всё равно должен попасть в zone_events.
        mock_fetch.return_value = [{"status": "SENT", "zone_id": 7, "cmd": "set_fault_mode"}]
        mock_send.return_value = True

        await handle_command_response(topic, payload)

        mock_create_zone_event.assert_awaited_once()
        args = mock_create_zone_event.await_args.args
        assert args[0] == 7
        assert args[1] == "IRR_STATE_SNAPSHOT"
        assert args[2]["snapshot"]["pump_main"] is True
        # Частичный snapshot допустим: отсутствующие поля не блокируют сохранение.
        assert "valve_irrigation" not in args[2]["snapshot"]
