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


@pytest.mark.asyncio
async def test_zone_event_listener_replays_missed_node_events_after_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatched: list[dict[str, object]] = []

    async def _on_zone_event(data: dict[str, object]) -> None:
        dispatched.append(dict(data))

    from ae3lite.infrastructure.zone_event_listener import ZoneEventListener

    listener = ZoneEventListener(
        dsn="postgresql://unused",
        on_zone_event=_on_zone_event,
        replay_lookback_minutes=5,
    )
    listener._replay_on_connect = True

    conn = AsyncMock()
    conn.fetch = AsyncMock(
        return_value=[
            {
                "zone_id": 3,
                "type": "LEVEL_SWITCH_CHANGED",
                "payload_json": {
                    "source": "node_event",
                    "channel": "level_clean_min",
                    "state": True,
                },
                "created_at": datetime(2026, 7, 8, 9, 0, tzinfo=timezone.utc),
            }
        ]
    )

    await listener._replay_missed_zone_events(conn)

    assert len(dispatched) == 1
    assert dispatched[0]["zone_id"] == 3
    assert dispatched[0]["event_type"] == "LEVEL_SWITCH_CHANGED"
    assert dispatched[0]["replayed"] is True


@pytest.mark.asyncio
async def test_zone_event_listener_rearms_replay_on_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from ae3lite.infrastructure.zone_event_listener import ZoneEventListener

    listener = ZoneEventListener(dsn="postgresql://unused", on_zone_event=AsyncMock())
    listener._replay_on_connect = False
    replay_flags_after_error: list[bool] = []
    calls = {"n": 0}

    async def _run_once_stub() -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("listen disconnected")
        listener._stop_event.set()

    async def _sleep_stub(_delay: float) -> None:
        replay_flags_after_error.append(listener._replay_on_connect)

    listener._run_once = _run_once_stub  # type: ignore[method-assign]
    monkeypatch.setattr(asyncio, "sleep", _sleep_stub)

    await listener.run()

    assert replay_flags_after_error == [True]


def test_zone_event_listener_invalid_json_increments_metric() -> None:
    from unittest.mock import MagicMock

    from ae3lite.infrastructure.metrics import LISTENER_INVALID_PAYLOAD
    from ae3lite.infrastructure.zone_event_listener import ZoneEventListener

    before = LISTENER_INVALID_PAYLOAD.labels(listener="zone_event")._value.get()
    listener = ZoneEventListener(dsn="postgresql://unused", on_zone_event=AsyncMock())
    listener._notify_handler(MagicMock(), 1, "ae_zone_event", "not-json")
    after = LISTENER_INVALID_PAYLOAD.labels(listener="zone_event")._value.get()
    assert after == before + 1
