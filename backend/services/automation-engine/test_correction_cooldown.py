from datetime import datetime, timedelta

import pytest

import correction_cooldown


def _fake_fetch_from_events(events):
    async def _fake_fetch(_query, zone_id, event_types, payload_markers):
        assert isinstance(payload_markers, list)
        matched = []
        for event in events:
            if event.get("zone_id") != zone_id:
                continue
            if event.get("type") not in event_types:
                continue
            payload = event.get("payload_json") or {}
            correction_marker = str(payload.get("correction_type") or "").strip().lower()
            type_marker = str(payload.get("type") or "").strip().lower()
            if correction_marker in payload_markers or type_marker in payload_markers:
                matched.append({"created_at": event["created_at"]})

        matched.sort(key=lambda row: row["created_at"], reverse=True)
        return matched[:1]

    return _fake_fetch


def test_resolve_correction_event_filters_are_exact():
    ec_filters = correction_cooldown._resolve_correction_event_filters("ec")
    ph_filters = correction_cooldown._resolve_correction_event_filters("ph")

    assert ec_filters is not None
    assert ph_filters is not None

    ec_event_types, ec_payload_markers = ec_filters
    ph_event_types, ph_payload_markers = ph_filters

    assert "EC_DOSING" in ec_event_types
    assert "PH_CORRECTED" in ph_event_types
    assert "ec_correction" in ec_payload_markers
    assert "ph_correction" in ph_payload_markers
    assert "ph_correction" not in ec_payload_markers
    assert "ec_correction" not in ph_payload_markers


@pytest.mark.asyncio
async def test_get_last_correction_time_ec_ignores_recent_ph_dosing(monkeypatch):
    now = datetime.utcnow()
    events = [
        {
            "zone_id": 77,
            "type": "DOSING",
            "created_at": now - timedelta(minutes=1),
            "payload_json": {"type": "ph_correction", "correction_type": "add_acid"},
        },
        {
            "zone_id": 77,
            "type": "EC_DOSING",
            "created_at": now - timedelta(minutes=5),
            "payload_json": {"correction_type": "add_nutrients"},
        },
    ]
    monkeypatch.setattr(correction_cooldown, "fetch", _fake_fetch_from_events(events))

    last = await correction_cooldown.get_last_correction_time(77, "ec")
    assert last == now - timedelta(minutes=5)


@pytest.mark.asyncio
async def test_is_in_cooldown_ec_false_when_only_recent_ph_dosing(monkeypatch):
    now = datetime.utcnow()
    events = [
        {
            "zone_id": 88,
            "type": "DOSING",
            "created_at": now - timedelta(minutes=1),
            "payload_json": {"type": "ph_correction", "correction_type": "add_acid"},
        }
    ]
    monkeypatch.setattr(correction_cooldown, "fetch", _fake_fetch_from_events(events))

    in_cooldown = await correction_cooldown.is_in_cooldown(88, "ec", cooldown_minutes=10)
    assert in_cooldown is False


@pytest.mark.asyncio
async def test_get_last_correction_time_ec_ignores_substring_marker(monkeypatch):
    now = datetime.utcnow()
    events = [
        {
            "zone_id": 91,
            "type": "DOSING",
            "created_at": now - timedelta(minutes=1),
            "payload_json": {"type": "ecology", "correction_type": "ecology_mode"},
        },
        {
            "zone_id": 91,
            "type": "EC_DOSING",
            "created_at": now - timedelta(minutes=4),
            "payload_json": {"correction_type": "add_nutrients"},
        },
    ]
    monkeypatch.setattr(correction_cooldown, "fetch", _fake_fetch_from_events(events))

    last = await correction_cooldown.get_last_correction_time(91, "ec")
    assert last == now - timedelta(minutes=4)


@pytest.mark.asyncio
async def test_get_last_correction_time_unknown_type_returns_none(monkeypatch):
    async def _unexpected_fetch(*_args, **_kwargs):
        raise AssertionError("fetch should not be called for unknown correction type")

    monkeypatch.setattr(correction_cooldown, "fetch", _unexpected_fetch)

    last = await correction_cooldown.get_last_correction_time(99, "orp")
    assert last is None


@pytest.mark.asyncio
async def test_should_apply_correction_bypasses_cooldown_for_critical_diff(monkeypatch):
    async def _unexpected_is_in_cooldown(*_args, **_kwargs):
        raise AssertionError("is_in_cooldown must be skipped for critical deviation")

    monkeypatch.setattr(correction_cooldown, "is_in_cooldown", _unexpected_is_in_cooldown)

    allowed, reason = await correction_cooldown.should_apply_correction(
        zone_id=2,
        correction_type="ec",
        current_value=0.4,
        target_value=1.05,
        diff=-0.65,
        cooldown_minutes=10,
    )

    assert allowed is True
    assert "cooldown bypass" in reason


@pytest.mark.asyncio
async def test_should_apply_correction_ec_bypasses_cooldown_for_significant_diff(monkeypatch):
    async def _unexpected_is_in_cooldown(*_args, **_kwargs):
        raise AssertionError("is_in_cooldown must be skipped for EC critical deviation")

    monkeypatch.setattr(correction_cooldown, "is_in_cooldown", _unexpected_is_in_cooldown)

    allowed, reason = await correction_cooldown.should_apply_correction(
        zone_id=2,
        correction_type="ec",
        current_value=0.6,
        target_value=1.05,
        diff=-0.35,
        cooldown_minutes=10,
    )

    assert allowed is True
    assert "cooldown bypass" in reason


@pytest.mark.asyncio
async def test_should_apply_correction_ph_keeps_cooldown_for_non_critical_diff(monkeypatch):
    now = datetime.utcnow()

    async def _is_in_cooldown(*_args, **_kwargs):
        return True

    async def _last_correction(*_args, **_kwargs):
        return now - timedelta(minutes=1)

    monkeypatch.setattr(correction_cooldown, "is_in_cooldown", _is_in_cooldown)
    monkeypatch.setattr(correction_cooldown, "get_last_correction_time", _last_correction)

    allowed, reason = await correction_cooldown.should_apply_correction(
        zone_id=2,
        correction_type="ph",
        current_value=6.2,
        target_value=5.75,
        diff=0.45,
        cooldown_minutes=10,
    )

    assert allowed is False
    assert "cooldown периоде" in reason


@pytest.mark.asyncio
async def test_should_apply_correction_respects_cooldown_for_non_critical_diff(monkeypatch):
    now = datetime.utcnow()

    async def _is_in_cooldown(*_args, **_kwargs):
        return True

    async def _last_correction(*_args, **_kwargs):
        return now - timedelta(minutes=2)

    monkeypatch.setattr(correction_cooldown, "is_in_cooldown", _is_in_cooldown)
    monkeypatch.setattr(correction_cooldown, "get_last_correction_time", _last_correction)

    allowed, reason = await correction_cooldown.should_apply_correction(
        zone_id=2,
        correction_type="ec",
        current_value=1.01,
        target_value=1.05,
        diff=-0.04,
        cooldown_minutes=10,
    )

    assert allowed is False
    assert "cooldown периоде" in reason
