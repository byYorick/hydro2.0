"""Reliability tests for MQTT handler error surfacing and fail-closed metrics."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_handle_status_offline_raises_node_offline_alert() -> None:
    from handlers.heartbeat_status import handle_status

    with patch(
        "handlers.heartbeat_status.execute",
        new=AsyncMock(return_value="UPDATE 1"),
    ), patch(
        "handlers.heartbeat_status.raise_node_offline_alert",
        new=AsyncMock(),
    ) as alert_mock, patch(
        "handlers.heartbeat_status.STATUS_RECEIVED"
    ):
        await handle_status(
            "hydro/gh-6464/zn-4345/nd-irrig-1/status",
            b'{"status":"OFFLINE"}',
        )

    alert_mock.assert_awaited_once_with(
        node_uid="nd-irrig-1",
        reason="mqtt_status_offline",
    )


@pytest.mark.asyncio
async def test_handle_status_offline_unknown_node_skips_alert_and_increments_metric() -> None:
    from handlers.heartbeat_status import handle_status
    from metrics import NODE_UPDATE_ZERO_ROWS

    before = NODE_UPDATE_ZERO_ROWS.labels(handler="status")._value.get()

    with patch(
        "handlers.heartbeat_status.execute",
        new=AsyncMock(return_value="UPDATE 0"),
    ), patch(
        "handlers.heartbeat_status.raise_node_offline_alert",
        new=AsyncMock(),
    ) as alert_mock, patch(
        "handlers.heartbeat_status.STATUS_RECEIVED"
    ):
        await handle_status(
            "hydro/gh-6464/zn-4345/unknown-node/status",
            b'{"status":"OFFLINE"}',
        )

    alert_mock.assert_not_awaited()
    after = NODE_UPDATE_ZERO_ROWS.labels(handler="status")._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_handle_config_report_preserves_existing_node_secret() -> None:
    from handlers.config_report import handle_config_report

    topic = "hydro/gh-1/zn-1/nd-ph-1/config_report"
    payload = b'{"node_id":"nd-ph-1","version":3,"channels":[]}'
    existing_secret = "a" * 64

    with patch("handlers.config_report.fetch", new_callable=AsyncMock) as mock_fetch, patch(
        "handlers.config_report.execute", new_callable=AsyncMock
    ) as mock_execute, patch(
        "handlers.config_report.sync_node_channels_from_payload", new_callable=AsyncMock
    ), patch(
        "handlers.config_report._complete_binding_after_config_report",
        new_callable=AsyncMock,
        return_value=True,
    ), patch(
        "handlers.config_report._complete_sensor_calibrations_after_config_report",
        new_callable=AsyncMock,
    ), patch(
        "handlers.config_report.refresh_node_cache_for_uid", new_callable=AsyncMock
    ), patch(
        "handlers.config_report.CONFIG_REPORT_RECEIVED"
    ), patch(
        "handlers.config_report.CONFIG_REPORT_PROCESSED"
    ):
        mock_fetch.return_value = [
            {
                "id": 1,
                "uid": "nd-ph-1",
                "lifecycle_state": "ASSIGNED_TO_ZONE",
                "zone_id": 1,
                "pending_zone_id": None,
                "config": {"node_secret": existing_secret, "version": 2},
            }
        ]

        await handle_config_report(topic, payload)

        stored = mock_execute.await_args.args[1]
        assert stored["node_secret"] == existing_secret
        assert "node_secret" not in __import__("json").loads(payload)


def test_preserve_existing_node_secret_keeps_db_value() -> None:
    from handlers.config_report import _preserve_existing_node_secret

    out = _preserve_existing_node_secret(
        {"node_secret": "b" * 64, "version": 1},
        {"version": 3, "channels": []},
    )
    assert out["node_secret"] == "b" * 64
    assert out["version"] == 3


def test_preserve_existing_node_secret_noop_when_absent() -> None:
    from handlers.config_report import _preserve_existing_node_secret

    incoming = {"version": 3}
    assert _preserve_existing_node_secret({}, incoming) is incoming
    assert _preserve_existing_node_secret(None, incoming) is incoming


@pytest.mark.asyncio
async def test_handle_config_report_does_not_mark_processed_on_laravel_ack_fail() -> None:
    from handlers.config_report import handle_config_report

    topic = "hydro/gh-1/zn-1/nd-ph-1/config_report"
    payload = b'{"node_id":"nd-ph-1","version":3,"channels":[]}'

    with patch("handlers.config_report.fetch", new_callable=AsyncMock) as mock_fetch, patch(
        "handlers.config_report.execute", new_callable=AsyncMock
    ), patch(
        "handlers.config_report.sync_node_channels_from_payload", new_callable=AsyncMock
    ), patch(
        "handlers.config_report._complete_binding_after_config_report",
        new_callable=AsyncMock,
        return_value=False,
    ), patch(
        "handlers.config_report.refresh_node_cache_for_uid", new_callable=AsyncMock
    ), patch(
        "handlers.config_report.CONFIG_REPORT_RECEIVED"
    ) as mock_received, patch(
        "handlers.config_report.CONFIG_REPORT_PROCESSED"
    ) as mock_processed, patch(
        "handlers.config_report.CONFIG_REPORT_ACK_FAILED"
    ) as mock_ack_failed:
        mock_fetch.return_value = [
            {
                "id": 1,
                "uid": "nd-ph-1",
                "lifecycle_state": "REGISTERED_BACKEND",
                "zone_id": 1,
                "pending_zone_id": None,
            }
        ]

        await handle_config_report(topic, payload)

    mock_received.inc.assert_called_once()
    mock_processed.inc.assert_not_called()
    mock_ack_failed.labels.assert_called_once_with(node_uid="nd-ph-1")
    mock_ack_failed.labels.return_value.inc.assert_called_once()


@pytest.mark.asyncio
async def test_handle_config_report_does_not_mark_processed_on_channel_sync_fail() -> None:
    from handlers.config_report import handle_config_report

    topic = "hydro/gh-1/zn-1/nd-ph-1/config_report"
    payload = b'{"node_id":"nd-ph-1","version":3,"channels":[{"name":"ph_sensor"}]}'

    with patch("handlers.config_report.fetch", new_callable=AsyncMock) as mock_fetch, patch(
        "handlers.config_report.execute", new_callable=AsyncMock
    ), patch(
        "handlers.config_report.sync_node_channels_from_payload",
        new_callable=AsyncMock,
        side_effect=RuntimeError("sync failed"),
    ), patch(
        "handlers.config_report._complete_binding_after_config_report",
        new_callable=AsyncMock,
        return_value=True,
    ), patch(
        "handlers.config_report.CONFIG_REPORT_PROCESSED"
    ) as mock_processed, patch(
        "handlers.config_report.CONFIG_REPORT_CHANNEL_SYNC_FAILED"
    ) as mock_channel_failed:
        mock_fetch.return_value = [
            {
                "id": 1,
                "uid": "nd-ph-1",
                "lifecycle_state": "REGISTERED_BACKEND",
                "zone_id": 1,
                "pending_zone_id": None,
            }
        ]

        await handle_config_report(topic, payload)

    mock_processed.inc.assert_not_called()
    mock_channel_failed.labels.assert_called_once_with(node_uid="nd-ph-1")
    mock_channel_failed.labels.return_value.inc.assert_called_once()


def test_mqtt_async_handler_done_callback_logs_and_records_metric(caplog) -> None:
    import concurrent.futures
    import logging

    from common.mqtt import _make_async_done_callback, register_async_handler_error_callback
    from common.env import Settings

    recorded: list[tuple[str, str, BaseException]] = []

    def _capture(handler_name: str, topic: str, exc: BaseException) -> None:
        recorded.append((handler_name, topic, exc))

    register_async_handler_error_callback(_capture)

    async def failing_handler(topic: str, payload: bytes) -> None:
        raise ValueError("async handler boom")

    future: concurrent.futures.Future = concurrent.futures.Future()
    future.set_exception(ValueError("async handler boom"))

    with caplog.at_level(logging.ERROR):
        callback = _make_async_done_callback(
            failing_handler,
            "hydro/gh-1/zn-1/nd-ph-1/heartbeat",
        )
        callback(future)

    assert recorded
    handler_name, topic, exc = recorded[-1]
    assert handler_name == "failing_handler"
    assert topic == "hydro/gh-1/zn-1/nd-ph-1/heartbeat"
    assert isinstance(exc, ValueError)
    assert any("async handler boom" in record.message for record in caplog.records)
