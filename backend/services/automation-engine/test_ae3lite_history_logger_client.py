from __future__ import annotations

import json

import httpx
import pytest

from ae3lite.domain.errors import CommandPublishError
from ae3lite.infrastructure.clients import HistoryLoggerClient
from ae3lite.infrastructure.clients import history_logger_client as history_logger_client_module


@pytest.mark.asyncio
async def test_history_logger_client_posts_canonical_publish_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://history-logger:9300/commands"
        assert request.headers["Authorization"] == "Bearer dev-token-12345"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload == {
            "greenhouse_uid": "gh-1",
            "zone_id": 9,
            "node_uid": "nd-irrig-1",
            "channel": "pump_main",
            "cmd": "set_relay",
            "params": {"state": True},
            "source": "automation-engine",
        }
        return httpx.Response(200, json={"status": "ok", "data": {"command_id": "cmd-123"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = HistoryLoggerClient(
        base_url="http://history-logger:9300",
        token="dev-token-12345",
        source="automation-engine",
        client=client,
    )

    try:
        command_id = await gateway.publish(
            greenhouse_uid="gh-1",
            zone_id=9,
            node_uid="nd-irrig-1",
            channel="pump_main",
            cmd="set_relay",
            params={"state": True},
        )
    finally:
        await client.aclose()

    assert command_id == "cmd-123"


@pytest.mark.asyncio
async def test_history_logger_client_fails_closed_on_invalid_response() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "published_but_status_not_persisted"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = HistoryLoggerClient(base_url="http://history-logger:9300", client=client)

    try:
        with pytest.raises(CommandPublishError, match="published_but_status_not_persisted"):
            await gateway.publish(
                greenhouse_uid="gh-1",
                zone_id=9,
                node_uid="nd-irrig-1",
                channel="pump_main",
                cmd="set_relay",
                params={"state": True},
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_history_logger_client_retries_once_on_retryable_http_status(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0
    sleep_calls: list[float] = []

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, json={"detail": "temporary_unavailable"})
        return httpx.Response(200, json={"status": "ok", "data": {"command_id": "cmd-456"}})

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(history_logger_client_module.asyncio, "sleep", fake_sleep)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = HistoryLoggerClient(base_url="http://history-logger:9300", client=client)

    try:
        command_id = await gateway.publish(
            greenhouse_uid="gh-1",
            zone_id=9,
            node_uid="nd-irrig-1",
            channel="pump_main",
            cmd="set_relay",
            params={"state": True},
        )
    finally:
        await client.aclose()

    assert command_id == "cmd-456"
    assert attempts == 2
    assert sleep_calls == [1.0]


@pytest.mark.asyncio
async def test_history_logger_client_retries_once_on_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0
    sleep_calls: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("connection dropped", request=request)
        return httpx.Response(200, json={"status": "ok", "data": {"command_id": "cmd-789"}})

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(history_logger_client_module.asyncio, "sleep", fake_sleep)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = HistoryLoggerClient(base_url="http://history-logger:9300", client=client)

    try:
        command_id = await gateway.publish(
            greenhouse_uid="gh-1",
            zone_id=9,
            node_uid="nd-irrig-1",
            channel="pump_main",
            cmd="set_relay",
            params={"state": True},
        )
    finally:
        await client.aclose()

    assert command_id == "cmd-789"
    assert attempts == 2
    assert sleep_calls == [1.0]


@pytest.mark.asyncio
async def test_history_logger_client_request_error_without_message_still_has_context() -> None:
    request = httpx.Request("POST", "http://history-logger:9300/commands")

    async def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = HistoryLoggerClient(base_url="http://history-logger:9300", client=client, max_retries=0)

    try:
        with pytest.raises(CommandPublishError) as exc_info:
            await gateway.publish(
                greenhouse_uid="gh-1",
                zone_id=9,
                node_uid="nd-irrig-1",
                channel="pump_main",
                cmd="set_relay",
                params={"state": True},
            )
    finally:
        await client.aclose()

    message = str(exc_info.value)
    assert "ReadTimeout" in message
    assert "url=http://history-logger:9300/commands" in message
