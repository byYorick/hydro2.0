from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ae3lite.infrastructure.intent_status_listener import IntentStatusListener
from ae3lite.infrastructure.metrics import LISTENER_INVALID_PAYLOAD


@pytest.mark.asyncio
async def test_intent_listener_invalid_json_increments_metric() -> None:
    before = LISTENER_INVALID_PAYLOAD.labels(listener="intent_status")._value.get()
    listener = IntentStatusListener(dsn="postgresql://unused", on_terminal_intent=AsyncMock())
    listener._parse_payload(channel="scheduler_intent_terminal", payload="not-json")
    after = LISTENER_INVALID_PAYLOAD.labels(listener="intent_status")._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_intent_listener_missing_fields_increments_metric() -> None:
    before = LISTENER_INVALID_PAYLOAD.labels(listener="intent_status")._value.get()
    listener = IntentStatusListener(dsn="postgresql://unused", on_terminal_intent=AsyncMock())
    listener._parse_payload(
        channel="scheduler_intent_terminal",
        payload=json.dumps({"intent_id": 1}),
    )
    after = LISTENER_INVALID_PAYLOAD.labels(listener="intent_status")._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_intent_listener_replays_terminal_intents_after_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    dispatched: list[dict[str, object]] = []

    async def _on_terminal_intent(data: dict[str, object]) -> None:
        dispatched.append(dict(data))

    listener = IntentStatusListener(
        dsn="postgresql://unused",
        on_terminal_intent=_on_terminal_intent,
        replay_lookback_minutes=5,
    )
    listener._replay_on_connect = True

    conn = AsyncMock()
    conn.fetch = AsyncMock(
        return_value=[
            {
                "intent_id": 42,
                "zone_id": 7,
                "status": "completed",
                "error_code": None,
                "updated_at": datetime(2026, 7, 8, 9, 0, tzinfo=timezone.utc),
            }
        ]
    )

    await listener._replay_missed_terminal_intents(conn)

    assert len(dispatched) == 1
    assert dispatched[0]["intent_id"] == 42
    assert dispatched[0]["zone_id"] == 7
    assert dispatched[0]["status"] == "completed"
    assert dispatched[0]["replayed"] is True


@pytest.mark.asyncio
async def test_intent_listener_dispatch_calls_callback() -> None:
    dispatched: list[dict[str, object]] = []

    async def _on_terminal_intent(data: dict[str, object]) -> None:
        dispatched.append(dict(data))

    listener = IntentStatusListener(dsn="postgresql://unused", on_terminal_intent=_on_terminal_intent)
    await listener._dispatch({"intent_id": 11, "zone_id": 22, "status": "failed"})

    assert len(dispatched) == 1
    assert dispatched[0]["intent_id"] == 11
    assert dispatched[0]["zone_id"] == 22
    assert dispatched[0]["status"] == "failed"


def test_zone_event_listener_invalid_json_increments_metric() -> None:
    from unittest.mock import MagicMock

    from ae3lite.infrastructure.metrics import LISTENER_INVALID_PAYLOAD
    from ae3lite.infrastructure.zone_event_listener import ZoneEventListener

    before = LISTENER_INVALID_PAYLOAD.labels(listener="zone_event")._value.get()
    listener = ZoneEventListener(dsn="postgresql://unused", on_zone_event=AsyncMock())
    listener._notify_handler(MagicMock(), 1, "ae_zone_event", "not-json")
    after = LISTENER_INVALID_PAYLOAD.labels(listener="zone_event")._value.get()
    assert after == before + 1
