"""Tests for BUG-1 (mist params in effective targets) and BUG-5 (cache invalidation)."""
from __future__ import annotations

from datetime import datetime

import pytest

import repositories.effective_targets_sql_read_model as sql_read_model
from ae2lite.effective_targets_notify_runtime import (
    handle_ae_signal_update_payload,
    should_invalidate_for_kind,
)
from repositories.effective_targets_sql_read_model import EffectiveTargetsSqlReadModel
from repositories.effective_targets_sql_utils import build_base_targets


def _normalize_query(query: str) -> str:
    return " ".join(str(query).split()).lower()


# ---------------------------------------------------------------------------
# BUG-1: build_base_targets includes mist parameters
# ---------------------------------------------------------------------------


def test_build_base_targets_includes_mist_when_present():
    phase = {
        "ph_target": 6.0,
        "ph_min": 5.8,
        "ph_max": 6.2,
        "ec_target": None,
        "irrigation_mode": None,
        "lighting_photoperiod_hours": None,
        "temp_air_target": None,
        "humidity_target": None,
        "co2_target": None,
        "mist_interval_sec": 1800,
        "mist_duration_sec": 30,
        "mist_mode": "SPRAY",
        "extensions": None,
    }
    targets = build_base_targets(phase)

    assert "mist" in targets
    assert targets["mist"]["interval_sec"] == 1800
    assert targets["mist"]["duration_sec"] == 30
    assert targets["mist"]["mode"] == "SPRAY"


def test_build_base_targets_omits_mist_when_all_none():
    phase = {
        "ph_target": 6.0,
        "ph_min": None,
        "ph_max": None,
        "ec_target": None,
        "irrigation_mode": None,
        "lighting_photoperiod_hours": None,
        "temp_air_target": None,
        "humidity_target": None,
        "co2_target": None,
        "mist_interval_sec": None,
        "mist_duration_sec": None,
        "mist_mode": None,
        "extensions": None,
    }
    targets = build_base_targets(phase)
    assert "mist" not in targets


def test_build_base_targets_mist_with_partial_fields():
    phase = {
        "ph_target": None,
        "ec_target": None,
        "irrigation_mode": None,
        "lighting_photoperiod_hours": None,
        "temp_air_target": None,
        "humidity_target": None,
        "co2_target": None,
        "mist_interval_sec": 600,
        "mist_duration_sec": None,
        "mist_mode": None,
        "extensions": None,
    }
    targets = build_base_targets(phase)
    assert "mist" in targets
    assert targets["mist"]["interval_sec"] == 600
    assert targets["mist"]["duration_sec"] is None


# ---------------------------------------------------------------------------
# BUG-1: SQL read-model loads mist columns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sql_read_model_loads_mist_fields(monkeypatch):
    """Ensure _load_phases SELECT includes mist columns and they reach targets."""
    query_calls = []

    async def fake_fetch(query, *args):
        normalized = _normalize_query(query)
        query_calls.append(normalized)

        if "from grow_cycles gc" in normalized:
            return [
                {
                    "cycle_id": 1,
                    "zone_id": 10,
                    "status": "RUNNING",
                    "current_phase_id": 100,
                    "current_stage_code": "VEG",
                    "phase_started_at": datetime(2026, 1, 1, 0, 0),
                    "progress_meta": {},
                }
            ]
        if "from grow_cycle_phases" in normalized:
            assert "mist_interval_sec" in normalized, (
                "SQL query must SELECT mist_interval_sec"
            )
            assert "mist_duration_sec" in normalized
            assert "mist_mode" in normalized
            return [
                {
                    "id": 100,
                    "name": "VEG",
                    "progress_model": "TIME",
                    "duration_hours": 12,
                    "duration_days": None,
                    "base_temp_c": None,
                    "ph_target": 6.0,
                    "ph_min": 5.8,
                    "ph_max": 6.2,
                    "ec_target": None,
                    "ec_min": None,
                    "ec_max": None,
                    "irrigation_mode": None,
                    "irrigation_interval_sec": None,
                    "irrigation_duration_sec": None,
                    "lighting_photoperiod_hours": None,
                    "lighting_start_time": None,
                    "temp_air_target": None,
                    "humidity_target": None,
                    "co2_target": None,
                    "mist_interval_sec": 900,
                    "mist_duration_sec": 15,
                    "mist_mode": "NORMAL",
                    "extensions": None,
                }
            ]
        return []

    monkeypatch.setattr(sql_read_model, "fetch", fake_fetch)

    reader = EffectiveTargetsSqlReadModel(cache_ttl_sec=0)
    result = await reader.get_effective_targets(10)

    assert result is not None
    assert "mist" in result["targets"]
    assert result["targets"]["mist"]["interval_sec"] == 900
    assert result["targets"]["mist"]["duration_sec"] == 15
    assert result["targets"]["mist"]["mode"] == "NORMAL"


# ---------------------------------------------------------------------------
# BUG-5: cache invalidation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_cache_single_zone(monkeypatch):
    call_count = {"n": 0}

    async def fake_fetch(query, *args):
        call_count["n"] += 1
        normalized = _normalize_query(query)
        if "from grow_cycles gc" in normalized:
            return [
                {
                    "cycle_id": 1,
                    "zone_id": 5,
                    "status": "RUNNING",
                    "current_phase_id": 50,
                    "current_stage_code": "FLOWER",
                    "phase_started_at": datetime(2026, 1, 1),
                    "progress_meta": {},
                }
            ]
        if "from grow_cycle_phases" in normalized:
            return [
                {
                    "id": 50,
                    "name": "Flower",
                    "progress_model": "TIME",
                    "duration_hours": 24,
                    "duration_days": None,
                    "base_temp_c": None,
                    "ph_target": 5.5,
                    "ph_min": None,
                    "ph_max": None,
                    "ec_target": None,
                    "ec_min": None,
                    "ec_max": None,
                    "irrigation_mode": None,
                    "irrigation_interval_sec": None,
                    "irrigation_duration_sec": None,
                    "lighting_photoperiod_hours": None,
                    "lighting_start_time": None,
                    "temp_air_target": None,
                    "humidity_target": None,
                    "co2_target": None,
                    "mist_interval_sec": None,
                    "mist_duration_sec": None,
                    "mist_mode": None,
                    "extensions": None,
                }
            ]
        return []

    monkeypatch.setattr(sql_read_model, "fetch", fake_fetch)

    reader = EffectiveTargetsSqlReadModel(cache_ttl_sec=300)

    # First call — populates cache
    r1 = await reader.get_effective_targets(5)
    assert r1 is not None
    fetch_after_first = call_count["n"]

    # Second call — should use cache (no new fetch calls)
    r2 = await reader.get_effective_targets(5)
    assert call_count["n"] == fetch_after_first

    # Invalidate and call again — should re-fetch
    reader.invalidate_cache(5)
    r3 = await reader.get_effective_targets(5)
    assert call_count["n"] > fetch_after_first


@pytest.mark.asyncio
async def test_invalidate_cache_all(monkeypatch):
    async def fake_fetch(query, *args):
        normalized = _normalize_query(query)
        if "from grow_cycles gc" in normalized:
            return []
        return []

    monkeypatch.setattr(sql_read_model, "fetch", fake_fetch)

    reader = EffectiveTargetsSqlReadModel(cache_ttl_sec=300)
    await reader.get_effective_targets(1)
    await reader.get_effective_targets(2)

    assert len(reader._cache) == 2
    reader.invalidate_cache()
    assert len(reader._cache) == 0


def test_should_invalidate_for_kind_filters_telemetry():
    assert should_invalidate_for_kind("telemetry_last") is False
    assert should_invalidate_for_kind("zone_event") is True


@pytest.mark.asyncio
async def test_notify_payload_invalidates_zone_cache():
    invalidated = []

    class _Logger:
        def debug(self, *_args, **_kwargs):
            return None

    await handle_ae_signal_update_payload(
        '{"zone_id": 7, "kind": "zone_event"}',
        invalidate_cache_fn=lambda zone_id: invalidated.append(zone_id),
        logger=_Logger(),
    )

    assert invalidated == [7]


@pytest.mark.asyncio
async def test_notify_payload_ignores_telemetry_kind():
    invalidated = []

    class _Logger:
        def debug(self, *_args, **_kwargs):
            return None

    await handle_ae_signal_update_payload(
        '{"zone_id": 7, "kind": "telemetry_last"}',
        invalidate_cache_fn=lambda zone_id: invalidated.append(zone_id),
        logger=_Logger(),
    )

    assert invalidated == []
