from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

import pytest

from infrastructure.telemetry_query_adapter import read_level_switch


def _parse_iso_datetime(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _canonicalize_label(raw: Any) -> str:
    label = str(raw or "").strip().lower()
    if not label:
        return ""
    normalized = "".join(ch if ch.isalnum() else "_" for ch in label)
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_")


def _normalized_sql(sql: str) -> str:
    return " ".join(sql.split())


class _FetchStub:
    def __init__(self, responses: Sequence[Sequence[dict[str, Any]]]) -> None:
        self._responses = [list(chunk) for chunk in responses]
        self.queries: list[str] = []

    async def __call__(self, query: str, *_args: Any) -> list[dict[str, Any]]:
        self.queries.append(query)
        if not self._responses:
            return []
        return list(self._responses.pop(0))


@pytest.mark.asyncio
async def test_read_level_switch_queries_switch_type_on_exact_match() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    fetch_stub = _FetchStub(
        responses=[
            [
                {
                    "sensor_id": 31,
                    "sensor_label": "level_clean_max",
                    "level": 1,
                    "sample_ts": now,
                    "level_source": "telemetry_last",
                }
            ]
        ]
    )

    result = await read_level_switch(
        fetch_fn=fetch_stub,
        parse_iso_datetime=_parse_iso_datetime,
        canonicalize_label=_canonicalize_label,
        zone_id=6,
        sensor_labels=["level_clean_max"],
        threshold=0.5,
        telemetry_max_age_sec=60,
    )

    assert result["has_level"] is True
    assert result["is_triggered"] is True
    assert len(fetch_stub.queries) == 1
    assert "s.type IN ('WATER_LEVEL', 'WATER_LEVEL_SWITCH')" in _normalized_sql(fetch_stub.queries[0])


@pytest.mark.asyncio
async def test_read_level_switch_candidate_scan_queries_switch_type() -> None:
    fetch_stub = _FetchStub(
        responses=[
            [],
            [
                {
                    "sensor_id": 44,
                    "sensor_label": "clean_level_max",
                    "level": None,
                    "sample_ts": None,
                    "level_source": "none",
                }
            ],
        ]
    )

    result = await read_level_switch(
        fetch_fn=fetch_stub,
        parse_iso_datetime=_parse_iso_datetime,
        canonicalize_label=_canonicalize_label,
        zone_id=6,
        sensor_labels=["level_clean_max", "clean_max"],
        threshold=0.5,
        telemetry_max_age_sec=60,
    )

    assert result["has_level"] is False
    assert result["available_sensor_labels"] == ["clean_level_max"]
    assert len(fetch_stub.queries) == 2
    assert all(
        "s.type IN ('WATER_LEVEL', 'WATER_LEVEL_SWITCH')" in _normalized_sql(query)
        for query in fetch_stub.queries
    )
