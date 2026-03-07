from __future__ import annotations

import json

import httpx
import pytest

from ae3lite.domain.errors import CommandPublishError
from ae3lite.infrastructure.clients import HistoryLoggerClient


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
