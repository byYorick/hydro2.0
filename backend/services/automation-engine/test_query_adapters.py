"""Unit tests for infrastructure query adapters used by SchedulerTaskExecutor."""

from datetime import datetime, timedelta, timezone

import pytest

from infrastructure.node_query_adapter import (
    check_required_nodes_online,
    fetch_zone_nodes,
    resolve_refill_node,
    resolve_online_node_for_channel,
)
from infrastructure.telemetry_query_adapter import (
    find_zone_event_since,
    read_latest_metric,
    read_level_switch,
)


def _parse_iso(value: str):
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@pytest.mark.asyncio
async def test_fetch_zone_nodes_normalizes_types_and_maps_result():
    async def _fetch(query, zone_id, node_types):
        assert zone_id == 12
        assert node_types == ["irrig", "ph"]
        return [{"uid": "nd-1", "type": "irrig", "channel": "pump_a"}]

    result = await fetch_zone_nodes(
        fetch_fn=_fetch,
        zone_id=12,
        node_types=["IRRIG", " ", "ph"],
    )

    assert result == [{"node_uid": "nd-1", "type": "irrig", "channel": "pump_a"}]


@pytest.mark.asyncio
async def test_resolve_online_node_for_channel_returns_none_for_blank_channel():
    async def _fetch(*_args, **_kwargs):
        raise AssertionError("fetch must not be called")

    result = await resolve_online_node_for_channel(
        fetch_fn=_fetch,
        zone_id=1,
        channel="",
        node_types=["ph"],
    )

    assert result is None


@pytest.mark.asyncio
async def test_check_required_nodes_online_calculates_missing_types():
    async def _fetch(_query, _zone_id, _types):
        return [{"node_type": "irrig", "online_count": 2}]

    state = await check_required_nodes_online(
        fetch_fn=_fetch,
        zone_id=7,
        required_types=["irrig", "ph"],
    )

    assert state["online_counts"] == {"irrig": 2}
    assert state["missing_types"] == ["ph"]


@pytest.mark.asyncio
async def test_resolve_refill_node_prefers_requested_channel():
    async def _fetch(_query, zone_id, node_types, channels):
        assert zone_id == 15
        assert node_types == ["irrig"]
        assert channels == ["pump_in", "valve_clean_fill"]
        return [
            {"node_uid": "nd-ir-1", "node_type": "irrig", "channel": "pump_in"},
            {"node_uid": "nd-ir-2", "node_type": "irrig", "channel": "valve_clean_fill"},
        ]

    node = await resolve_refill_node(
        fetch_fn=_fetch,
        zone_id=15,
        node_types=["IRRIG"],
        preferred_channels=["pump_in", "valve_clean_fill"],
        requested_channel="valve_clean_fill",
    )

    assert node == {"node_uid": "nd-ir-2", "type": "irrig", "channel": "valve_clean_fill"}


@pytest.mark.asyncio
async def test_resolve_refill_node_fallback_prefers_matching_type_for_same_channel_rank():
    async def _fetch(_query, _zone_id, _node_types, _channels):
        return [
            {"node_uid": "nd-cl-1", "node_type": "climate", "channel": "pump_in"},
            {"node_uid": "nd-ir-1", "node_type": "irrig", "channel": "pump_in"},
        ]

    node = await resolve_refill_node(
        fetch_fn=_fetch,
        zone_id=9,
        node_types=["irrig"],
        preferred_channels=["pump_in"],
        requested_channel="",
    )

    assert node == {"node_uid": "nd-ir-1", "type": "irrig", "channel": "pump_in"}


@pytest.mark.asyncio
async def test_read_latest_metric_marks_stale_for_old_sample():
    old_sample = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=601)).isoformat()

    async def _fetch(_query, _zone_id, _sensor_type):
        return [{"sensor_id": 1, "sensor_label": "outside", "value": 3.14, "sample_ts": old_sample}]

    metric = await read_latest_metric(
        fetch_fn=_fetch,
        parse_iso_datetime=_parse_iso,
        zone_id=1,
        sensor_type="OUTSIDE_TEMP",
        telemetry_max_age_sec=600,
    )

    assert metric["has_value"] is True
    assert metric["is_stale"] is True


@pytest.mark.asyncio
async def test_read_level_switch_uses_canonical_fallback_when_exact_missing():
    calls = {"count": 0}

    async def _fetch(_query, zone_id, *args):
        calls["count"] += 1
        assert zone_id == 3
        if calls["count"] == 1:
            return []
        return [
            {
                "sensor_id": 5,
                "sensor_label": "Clean Tank MAX",
                "level": 0.95,
                "sample_ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "level_source": "telemetry_last",
            }
        ]

    level = await read_level_switch(
        fetch_fn=_fetch,
        parse_iso_datetime=_parse_iso,
        canonicalize_label=lambda v: "".join(ch if ch.isalnum() else "_" for ch in str(v).lower()).strip("_"),
        zone_id=3,
        sensor_labels=["clean_tank_max"],
        threshold=0.9,
        telemetry_max_age_sec=600,
    )

    assert calls["count"] == 2
    assert level["has_level"] is True
    assert level["is_triggered"] is True
    assert level["matched_by"] == "canonical"


@pytest.mark.asyncio
async def test_find_zone_event_since_returns_none_for_empty_inputs():
    async def _fetch(*_args, **_kwargs):
        raise AssertionError("fetch must not be called")

    result = await find_zone_event_since(
        fetch_fn=_fetch,
        zone_id=1,
        event_types=[],
        since=None,
    )

    assert result is None


@pytest.mark.asyncio
async def test_find_zone_event_since_queries_payload_json_alias():
    captured = {}

    async def _fetch(query, zone_id, event_types, since):
        captured["query"] = query
        assert zone_id == 2
        assert event_types == ["PH_CORRECTED"]
        assert since is not None
        return [
            {
                "id": 77,
                "type": "PH_CORRECTED",
                "created_at": since,
                "details": {"correction_type": "ph"},
            }
        ]

    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    result = await find_zone_event_since(
        fetch_fn=_fetch,
        zone_id=2,
        event_types=["ph_corrected"],
        since=since,
    )

    assert "payload_json AS details" in captured["query"]
    assert result is not None
    assert result["id"] == 77
    assert result["details"]["correction_type"] == "ph"
