"""Tests for node event MQTT ingestion."""
import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_handle_node_event_stores_zone_event_from_numeric_zone_uid():
    """Event with zn-{id} zone uid should be persisted without DB zone lookup."""
    from mqtt_handlers import handle_node_event

    topic = "hydro/gh-1/zn-7/nd-irrig-1/storage_state/event"
    payload = json.dumps(
        {
            "event_code": "clean_fill_completed",
        }
    ).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event, \
         patch("mqtt_handlers.notify_zone_event_ingested", new_callable=AsyncMock) as mock_notify_zone_event, \
         patch("mqtt_handlers.NODE_EVENT_RECEIVED") as mock_event_received, \
         patch("mqtt_handlers.NODE_EVENT_UNKNOWN") as mock_event_unknown:
        await handle_node_event(topic, payload)

        mock_fetch.assert_not_awaited()
        mock_create_zone_event.assert_awaited_once()
        call_args = mock_create_zone_event.await_args.args
        assert call_args[0] == 7
        assert call_args[1] == "CLEAN_FILL_COMPLETED"
        assert call_args[2]["channel"] == "storage_state"
        assert call_args[2]["node_uid"] == "nd-irrig-1"
        mock_notify_zone_event.assert_awaited_once()
        mock_event_received.labels.assert_called_once_with(event_code="CLEAN_FILL_COMPLETED")
        mock_event_unknown.inc.assert_not_called()


@pytest.mark.asyncio
async def test_handle_node_event_storage_state_state_fallback_persists_irr_snapshot_event():
    """storage_state/event со state (без snapshot) должен писать IRR_STATE_SNAPSHOT."""
    from mqtt_handlers import handle_node_event

    topic = "hydro/gh-1/zn-7/nd-irrig-1/storage_state/event"
    payload = json.dumps(
        {
            "event_code": "clean_fill_completed",
            "cmd_id": "cmd-state-event-legacy",
            "ts": 1737979200014,
            "state": {
                "level_clean_min": 1,
                "level_clean_max": 1,
                "level_solution_min": 0,
                "level_solution_max": 0,
                "pump_main": 0,
            },
        }
    ).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event, \
         patch("mqtt_handlers.notify_zone_event_ingested", new_callable=AsyncMock) as mock_notify_zone_event, \
         patch("mqtt_handlers.NODE_EVENT_RECEIVED") as mock_event_received, \
         patch("mqtt_handlers.NODE_EVENT_UNKNOWN") as mock_event_unknown:
        await handle_node_event(topic, payload)

        mock_fetch.assert_not_awaited()
        assert mock_create_zone_event.await_count == 2

        first_args = mock_create_zone_event.await_args_list[0].args
        assert first_args[0] == 7
        assert first_args[1] == "CLEAN_FILL_COMPLETED"

        snapshot_args = mock_create_zone_event.await_args_list[1].args
        assert snapshot_args[0] == 7
        assert snapshot_args[1] == "IRR_STATE_SNAPSHOT"
        assert snapshot_args[2]["cmd_id"] == "cmd-state-event-legacy"
        assert snapshot_args[2]["snapshot"]["clean_level_max"] is True
        assert snapshot_args[2]["snapshot"]["pump_main"] is False

        mock_notify_zone_event.assert_awaited_once()
        mock_event_received.labels.assert_called_once_with(event_code="CLEAN_FILL_COMPLETED")
        mock_event_unknown.inc.assert_not_called()


@pytest.mark.asyncio
async def test_handle_node_event_storage_state_snapshot_persists_irr_snapshot_event():
    """storage_state/event со snapshot должен дополнительно писать IRR_STATE_SNAPSHOT."""
    from mqtt_handlers import handle_node_event

    topic = "hydro/gh-1/zn-7/nd-irrig-1/storage_state/event"
    payload = json.dumps(
        {
            "event_code": "clean_fill_completed",
            "cmd_id": "cmd-state-event-1",
            "ts": 1737979200014,
            "snapshot": {
                "clean_level_max": True,
                "clean_level_min": True,
                "solution_level_max": False,
                "solution_level_min": True,
                "valve_clean_fill": False,
                "valve_clean_supply": True,
                "valve_solution_fill": True,
                "valve_solution_supply": False,
                "pump_main": False,
            },
        }
    ).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event, \
         patch("mqtt_handlers.notify_zone_event_ingested", new_callable=AsyncMock) as mock_notify_zone_event, \
         patch("mqtt_handlers.NODE_EVENT_RECEIVED") as mock_event_received, \
         patch("mqtt_handlers.NODE_EVENT_UNKNOWN") as mock_event_unknown:
        await handle_node_event(topic, payload)

        mock_fetch.assert_not_awaited()
        assert mock_create_zone_event.await_count == 2

        first_args = mock_create_zone_event.await_args_list[0].args
        assert first_args[0] == 7
        assert first_args[1] == "CLEAN_FILL_COMPLETED"

        snapshot_args = mock_create_zone_event.await_args_list[1].args
        assert snapshot_args[0] == 7
        assert snapshot_args[1] == "IRR_STATE_SNAPSHOT"
        assert snapshot_args[2]["cmd_id"] == "cmd-state-event-1"
        assert snapshot_args[2]["snapshot"]["pump_main"] is False
        assert "valve_irrigation" not in snapshot_args[2]["snapshot"]

        mock_notify_zone_event.assert_awaited_once()
        mock_event_received.labels.assert_called_once_with(event_code="CLEAN_FILL_COMPLETED")
        mock_event_unknown.inc.assert_not_called()


@pytest.mark.asyncio
async def test_handle_node_event_irrigation_solution_low_notifies_payload_for_ae_runtime():
    """Fail-safe storage_state/event должен публиковать notify payload, пригодный для AE3 runtime callback."""
    from mqtt_handlers import handle_node_event

    topic = "hydro/gh-1/zn-7/nd-irrig-1/storage_state/event"
    payload = json.dumps(
        {
            "event_code": "irrigation_solution_low",
            "cmd_id": "cmd-state-event-2",
            "snapshot": {
                "solution_level_min": False,
                "pump_main": False,
                "valve_solution_supply": False,
                "valve_irrigation": False,
            },
        }
    ).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event, \
         patch("mqtt_handlers.notify_zone_event_ingested", new_callable=AsyncMock) as mock_notify_zone_event:
        await handle_node_event(topic, payload)

        mock_fetch.assert_not_awaited()
        assert mock_create_zone_event.await_count == 2
        notify_kwargs = mock_notify_zone_event.await_args.kwargs
        assert notify_kwargs["zone_id"] == 7
        assert notify_kwargs["event_type"] == "IRRIGATION_SOLUTION_LOW"
        assert notify_kwargs["payload"]["channel"] == "storage_state"
        assert notify_kwargs["payload"]["snapshot"]["solution_level_min"] is False
        assert notify_kwargs["payload"]["cmd_id"] == "cmd-state-event-2"


@pytest.mark.asyncio
async def test_handle_node_event_resolves_zone_via_db_uid_lookup():
    """Event with non-numeric zone uid should resolve zone_id from zones table."""
    from mqtt_handlers import handle_node_event

    topic = "hydro/gh-1/zone-alpha/nd-irrig-1/storage_state/event"
    payload = json.dumps({"event_code": "solution_fill_completed"}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event, \
         patch("mqtt_handlers.notify_zone_event_ingested", new_callable=AsyncMock):
        mock_fetch.side_effect = [
            [{"id": 42}],
        ]

        await handle_node_event(topic, payload)

        assert mock_fetch.await_count == 1
        mock_create_zone_event.assert_awaited_once()
        call_args = mock_create_zone_event.await_args.args
        assert call_args[0] == 42
        assert call_args[1] == "SOLUTION_FILL_COMPLETED"


@pytest.mark.asyncio
async def test_handle_node_event_skips_when_zone_not_resolved():
    """Handler should skip events when zone_id cannot be resolved."""
    from mqtt_handlers import handle_node_event

    topic = "hydro/gh-1/zone-alpha/nd-irrig-1/storage_state/event"
    payload = json.dumps({"event_code": "clean_fill_completed"}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event, \
         patch("mqtt_handlers.notify_zone_event_ingested", new_callable=AsyncMock), \
         patch("mqtt_handlers.NODE_EVENT_ERROR") as mock_event_error:
        # Сначала lookup по zones.uid, затем fallback lookup по nodes.uid
        mock_fetch.side_effect = [
            [],
            [],
        ]

        await handle_node_event(topic, payload)

        assert mock_fetch.await_count == 2
        mock_create_zone_event.assert_not_awaited()
        mock_event_error.labels.assert_called_once_with(reason="zone_not_resolved")


@pytest.mark.asyncio
async def test_handle_node_event_resolves_zone_via_node_uid_fallback():
    """Если zone_uid не разрешается, handler должен взять zone_id по node_uid."""
    from mqtt_handlers import handle_node_event

    topic = "hydro/gh-1/zone-alpha/nd-irrig-99/storage_state/event"
    payload = json.dumps({"event_code": "irrigation_recovery_started"}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event, \
         patch("mqtt_handlers.notify_zone_event_ingested", new_callable=AsyncMock):
        mock_fetch.side_effect = [
            [],  # lookup по zones.uid
            [{"zone_id": 77}],  # fallback lookup по nodes.uid
        ]

        await handle_node_event(topic, payload)

        assert mock_fetch.await_count == 2
        mock_create_zone_event.assert_awaited_once()
        call_args = mock_create_zone_event.await_args.args
        assert call_args[0] == 77
        assert call_args[1] == "IRRIGATION_RECOVERY_STARTED"


@pytest.mark.asyncio
async def test_handle_node_event_normalizes_event_type_symbols():
    """Символы/дефисы в event_code нормализуются в безопасный EVENT_TYPE."""
    from mqtt_handlers import handle_node_event

    topic = "hydro/gh-1/zn-5/nd-irrig-1/storage_state/event"
    payload = json.dumps({"event_code": "clean fill-completed/v2"}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event, \
         patch("mqtt_handlers.notify_zone_event_ingested", new_callable=AsyncMock), \
         patch("mqtt_handlers.NODE_EVENT_RECEIVED") as mock_event_received, \
         patch("mqtt_handlers.NODE_EVENT_UNKNOWN") as mock_event_unknown:
        await handle_node_event(topic, payload)

        mock_fetch.assert_not_awaited()
        mock_create_zone_event.assert_awaited_once()
        call_args = mock_create_zone_event.await_args.args
        assert call_args[0] == 5
        assert call_args[1] == "CLEAN_FILL_COMPLETED_V2"
        mock_event_received.labels.assert_called_once_with(event_code="OTHER")
        mock_event_unknown.inc.assert_called_once()


@pytest.mark.asyncio
async def test_handle_node_event_handler_exception_increments_metric():
    """Необработанное исключение внутри handler должно учитывать metric handler_exception."""
    from mqtt_handlers import handle_node_event

    topic = "hydro/gh-1/zn-9/nd-irrig-1/storage_state/event"
    payload = json.dumps({"event_code": "clean_fill_completed"}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event, \
         patch("mqtt_handlers.notify_zone_event_ingested", new_callable=AsyncMock), \
         patch("mqtt_handlers.NODE_EVENT_ERROR") as mock_event_error:
        mock_create_zone_event.side_effect = RuntimeError("db write failed")

        await handle_node_event(topic, payload)

        mock_fetch.assert_not_awaited()
        mock_create_zone_event.assert_awaited_once()
        mock_event_error.labels.assert_called_once_with(reason="handler_exception")


@pytest.mark.asyncio
async def test_handle_node_event_unknown_metric_code_falls_back_to_other():
    """Неизвестный event_code должен попадать в метрику как OTHER."""
    from mqtt_handlers import handle_node_event

    topic = "hydro/gh-1/zn-8/nd-irrig-1/storage_state/event"
    payload = json.dumps({"event_code": "brand_new_custom_event"}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event, \
         patch("mqtt_handlers.notify_zone_event_ingested", new_callable=AsyncMock), \
         patch("mqtt_handlers.NODE_EVENT_RECEIVED") as mock_event_received, \
         patch("mqtt_handlers.NODE_EVENT_UNKNOWN") as mock_event_unknown:
        await handle_node_event(topic, payload)

        mock_fetch.assert_not_awaited()
        mock_create_zone_event.assert_awaited_once()
        call_args = mock_create_zone_event.await_args.args
        assert call_args[0] == 8
        assert call_args[1] == "BRAND_NEW_CUSTOM_EVENT"
        mock_event_received.labels.assert_called_once_with(event_code="OTHER")
        mock_event_unknown.inc.assert_called_once()


@pytest.mark.asyncio
async def test_handle_node_event_prepare_recirculation_timeout_uses_dedicated_metric_code():
    """prepare_recirculation_timeout должен попадать в метрику без fallback OTHER."""
    from mqtt_handlers import handle_node_event

    topic = "hydro/gh-1/zn-8/nd-irrig-1/storage_state/event"
    payload = json.dumps({"event_code": "prepare_recirculation_timeout"}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event, \
         patch("mqtt_handlers.notify_zone_event_ingested", new_callable=AsyncMock), \
         patch("mqtt_handlers.NODE_EVENT_RECEIVED") as mock_event_received, \
         patch("mqtt_handlers.NODE_EVENT_UNKNOWN") as mock_event_unknown:
        await handle_node_event(topic, payload)

        mock_fetch.assert_not_awaited()
        mock_create_zone_event.assert_awaited_once()
        call_args = mock_create_zone_event.await_args.args
        assert call_args[0] == 8
        assert call_args[1] == "PREPARE_RECIRCULATION_TIMEOUT"
        mock_event_received.labels.assert_called_once_with(event_code="PREPARE_RECIRCULATION_TIMEOUT")
        mock_event_unknown.inc.assert_not_called()


@pytest.mark.asyncio
async def test_handle_node_event_emergency_stop_uses_dedicated_metric_code():
    """emergency_stop_activated должен попадать в метрику без fallback OTHER."""
    from mqtt_handlers import handle_node_event

    topic = "hydro/gh-1/zn-8/nd-irrig-1/storage_state/event"
    payload = json.dumps({"event_code": "emergency_stop_activated"}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event, \
         patch("mqtt_handlers.notify_zone_event_ingested", new_callable=AsyncMock), \
         patch("mqtt_handlers.NODE_EVENT_RECEIVED") as mock_event_received, \
         patch("mqtt_handlers.NODE_EVENT_UNKNOWN") as mock_event_unknown:
        await handle_node_event(topic, payload)

        mock_fetch.assert_not_awaited()
        mock_create_zone_event.assert_awaited_once()
        call_args = mock_create_zone_event.await_args.args
        assert call_args[0] == 8
        assert call_args[1] == "EMERGENCY_STOP_ACTIVATED"
        mock_event_received.labels.assert_called_once_with(event_code="EMERGENCY_STOP_ACTIVATED")
        mock_event_unknown.inc.assert_not_called()


@pytest.mark.asyncio
async def test_handle_node_event_truncates_long_event_type_with_hash_suffix():
    """Слишком длинный event_code должен безопасно усекаться до лимита БД."""
    from mqtt_handlers import handle_node_event

    topic = "hydro/gh-1/zn-6/nd-irrig-1/storage_state/event"
    long_event = "ev" + ("x" * 500)
    payload = json.dumps({"event_code": long_event}).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event, \
         patch("mqtt_handlers.notify_zone_event_ingested", new_callable=AsyncMock), \
         patch("mqtt_handlers.NODE_EVENT_RECEIVED") as mock_event_received, \
         patch("mqtt_handlers.NODE_EVENT_UNKNOWN") as mock_event_unknown:
        await handle_node_event(topic, payload)

        mock_fetch.assert_not_awaited()
        mock_create_zone_event.assert_awaited_once()
        call_args = mock_create_zone_event.await_args.args
        event_type = call_args[1]
        assert call_args[0] == 6
        assert len(event_type) == 255
        assert "_" in event_type
        suffix = event_type.rsplit("_", 1)[1]
        assert len(suffix) == 10
        assert all(ch in "0123456789ABCDEF" for ch in suffix)
        mock_event_received.labels.assert_called_once_with(event_code="OTHER")
        mock_event_unknown.inc.assert_called_once()


@pytest.mark.asyncio
async def test_handle_node_event_level_switch_changed_persists_normalized_payload_and_notifies():
    from mqtt_handlers import handle_node_event

    topic = "hydro/gh-1/zn-7/nd-irrig-1/level_solution_min/event"
    payload = json.dumps(
        {
            "event_code": "level_switch_changed",
            "channel": "level_solution_min",
            "state": False,
            "initial": False,
            "ts": 1737979200014,
            "snapshot": {
                "level_solution_min": 0,
                "level_solution_max": 0,
                "level_clean_min": 1,
            },
        }
    ).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event, \
         patch("mqtt_handlers.notify_zone_event_ingested", new_callable=AsyncMock) as mock_notify_zone_event, \
         patch("mqtt_handlers.NODE_EVENT_RECEIVED") as mock_event_received, \
         patch("mqtt_handlers.NODE_EVENT_UNKNOWN") as mock_event_unknown:
        await handle_node_event(topic, payload)

        mock_fetch.assert_not_awaited()
        mock_create_zone_event.assert_awaited_once()
        call_args = mock_create_zone_event.await_args.args
        assert call_args[0] == 7
        assert call_args[1] == "LEVEL_SWITCH_CHANGED"
        assert call_args[2]["channel"] == "level_solution_min"
        assert call_args[2]["state"] is False
        assert call_args[2]["initial"] is False
        assert call_args[2]["snapshot"]["solution_level_min"] is False
        assert call_args[2]["payload"]["snapshot"]["level_clean_min"] == 1
        mock_notify_zone_event.assert_awaited_once()
        notify_kwargs = mock_notify_zone_event.await_args.kwargs
        assert notify_kwargs["zone_id"] == 7
        assert notify_kwargs["event_type"] == "LEVEL_SWITCH_CHANGED"
        assert notify_kwargs["payload"]["channel"] == "level_solution_min"
        assert notify_kwargs["payload"]["state"] is False
        mock_event_received.labels.assert_called_once_with(event_code="LEVEL_SWITCH_CHANGED")
        mock_event_unknown.inc.assert_not_called()


@pytest.mark.asyncio
async def test_handle_node_event_skips_notify_when_deduped_insert_not_written():
    from mqtt_handlers import handle_node_event

    topic = "hydro/gh-1/zn-7/nd-irrig-1/level_solution_min/event"
    payload = json.dumps(
        {
            "event_code": "level_switch_changed",
            "channel": "level_solution_min",
            "state": True,
            "initial": False,
        }
    ).encode("utf-8")

    with patch("mqtt_handlers.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("mqtt_handlers.create_zone_event", new_callable=AsyncMock, return_value=False) as mock_create_zone_event, \
         patch("mqtt_handlers.notify_zone_event_ingested", new_callable=AsyncMock) as mock_notify_zone_event, \
         patch("mqtt_handlers.NODE_EVENT_RECEIVED") as mock_event_received, \
         patch("mqtt_handlers.NODE_EVENT_UNKNOWN") as mock_event_unknown:
        await handle_node_event(topic, payload)

        mock_fetch.assert_not_awaited()
        mock_create_zone_event.assert_awaited_once()
        mock_notify_zone_event.assert_not_awaited()
        mock_event_received.labels.assert_called_once_with(event_code="LEVEL_SWITCH_CHANGED")
        mock_event_unknown.inc.assert_not_called()
