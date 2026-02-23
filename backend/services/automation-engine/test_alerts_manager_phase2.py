import json

import pytest

import alerts_manager
from common.alerts import AlertCode, AlertSource


@pytest.mark.asyncio
async def test_ensure_alert_updates_existing_active_alert(monkeypatch):
    execute_calls = []
    create_alert_calls = []
    zone_event_calls = []

    async def fake_fetch(*args, **kwargs):
        return [{"id": 42, "details": {"legacy": True}}]

    async def fake_execute(*args, **kwargs):
        execute_calls.append((args, kwargs))

    async def fake_create_alert(*args, **kwargs):
        create_alert_calls.append((args, kwargs))

    async def fake_create_zone_event(*args, **kwargs):
        zone_event_calls.append((args, kwargs))

    monkeypatch.setattr(alerts_manager, "fetch", fake_fetch)
    monkeypatch.setattr(alerts_manager, "execute", fake_execute)
    monkeypatch.setattr(alerts_manager, "create_alert", fake_create_alert)
    monkeypatch.setattr(alerts_manager, "create_zone_event", fake_create_zone_event)

    details = {"value": 7.1, "threshold": 6.8}
    await alerts_manager.ensure_alert(zone_id=10, alert_type="PH_HIGH", details=details)

    assert len(execute_calls) == 1
    (execute_args, _) = execute_calls[0]
    assert "UPDATE alerts" in execute_args[0]
    assert json.loads(execute_args[1]) == details
    assert execute_args[2] == 42
    assert create_alert_calls == []
    assert zone_event_calls == []


@pytest.mark.asyncio
async def test_ensure_alert_creates_new_alert_with_mapping_and_event(monkeypatch):
    create_alert_calls = []
    zone_event_calls = []

    async def fake_fetch(*args, **kwargs):
        return []

    async def fake_execute(*args, **kwargs):
        raise AssertionError("execute must not be called for new alert")

    async def fake_create_alert(*args, **kwargs):
        create_alert_calls.append((args, kwargs))

    async def fake_create_zone_event(*args, **kwargs):
        zone_event_calls.append((args, kwargs))

    monkeypatch.setattr(alerts_manager, "fetch", fake_fetch)
    monkeypatch.setattr(alerts_manager, "execute", fake_execute)
    monkeypatch.setattr(alerts_manager, "create_alert", fake_create_alert)
    monkeypatch.setattr(alerts_manager, "create_zone_event", fake_create_zone_event)

    details = {"flow": 0.0}
    await alerts_manager.ensure_alert(zone_id=3, alert_type="NO_FLOW", details=details)

    assert len(create_alert_calls) == 1
    (_, kwargs) = create_alert_calls[0]
    assert kwargs["zone_id"] == 3
    assert kwargs["source"] == AlertSource.BIZ.value
    assert kwargs["code"] == AlertCode.BIZ_NO_FLOW.value
    assert kwargs["type"] == "NO_FLOW"
    assert kwargs["details"] == details

    assert len(zone_event_calls) == 1
    (event_args, _) = zone_event_calls[0]
    assert event_args[0] == 3
    assert event_args[1] == "ALERT_CREATED"
    assert event_args[2]["alert_type"] == "NO_FLOW"


@pytest.mark.asyncio
async def test_resolve_alert_returns_false_when_not_found(monkeypatch):
    execute_calls = []

    async def fake_fetch(*args, **kwargs):
        return []

    async def fake_execute(*args, **kwargs):
        execute_calls.append((args, kwargs))

    async def fake_create_zone_event(*args, **kwargs):
        raise AssertionError("zone event must not be emitted when alert missing")

    monkeypatch.setattr(alerts_manager, "fetch", fake_fetch)
    monkeypatch.setattr(alerts_manager, "execute", fake_execute)
    monkeypatch.setattr(alerts_manager, "create_zone_event", fake_create_zone_event)

    result = await alerts_manager.resolve_alert(zone_id=4, alert_type="EC_LOW")

    assert result is False
    assert execute_calls == []


@pytest.mark.asyncio
async def test_resolve_alert_closes_active_alert_and_emits_event(monkeypatch):
    execute_calls = []
    zone_event_calls = []

    async def fake_fetch(*args, **kwargs):
        return [{"id": 99}]

    async def fake_execute(*args, **kwargs):
        execute_calls.append((args, kwargs))

    async def fake_create_zone_event(*args, **kwargs):
        zone_event_calls.append((args, kwargs))

    monkeypatch.setattr(alerts_manager, "fetch", fake_fetch)
    monkeypatch.setattr(alerts_manager, "execute", fake_execute)
    monkeypatch.setattr(alerts_manager, "create_zone_event", fake_create_zone_event)

    result = await alerts_manager.resolve_alert(zone_id=8, alert_type="TEMP_LOW")

    assert result is True
    assert len(execute_calls) == 1
    (execute_args, _) = execute_calls[0]
    assert "SET status = 'RESOLVED'" in execute_args[0]
    assert execute_args[1] == 99

    assert len(zone_event_calls) == 1
    (event_args, _) = zone_event_calls[0]
    assert event_args[0] == 8
    assert event_args[1] == "ALERT_RESOLVED"
    assert event_args[2]["alert_id"] == 99


@pytest.mark.asyncio
async def test_find_active_alert_returns_normalized_payload(monkeypatch):
    async def fake_fetch(*args, **kwargs):
        return [
            {
                "id": 5,
                "type": "PH_LOW",
                "details": {"value": 5.3},
                "status": "ACTIVE",
                "created_at": "2026-02-21T10:00:00Z",
            }
        ]

    monkeypatch.setattr(alerts_manager, "fetch", fake_fetch)

    result = await alerts_manager.find_active_alert(zone_id=2, alert_type="PH_LOW")

    assert result == {
        "id": 5,
        "type": "PH_LOW",
        "details": {"value": 5.3},
        "status": "ACTIVE",
        "created_at": "2026-02-21T10:00:00Z",
    }
