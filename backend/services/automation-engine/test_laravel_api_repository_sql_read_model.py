from __future__ import annotations

from datetime import datetime

import pytest

from repositories.laravel_api_repository import LaravelApiRepository
import repositories.effective_targets_sql_read_model as sql_read_model


def _normalize_query(query: str) -> str:
    return " ".join(str(query).split()).lower()


@pytest.mark.asyncio
async def test_effective_targets_read_model_uses_sql_and_merges_overrides(monkeypatch):
    query_calls = []

    async def fake_fetch(query, *args):
        normalized = _normalize_query(query)
        query_calls.append(normalized)

        if "from grow_cycles gc" in normalized:
            return [
                {
                    "cycle_id": 101,
                    "zone_id": 12,
                    "status": "RUNNING",
                    "current_phase_id": 201,
                    "current_stage_code": "VEG",
                    "phase_started_at": datetime(2026, 2, 22, 8, 0, 0),
                    "progress_meta": {"temp_avg_24h": 26.0},
                }
            ]
        if "from grow_cycle_phases" in normalized:
            return [
                {
                    "id": 201,
                    "name": "Vegetative",
                    "progress_model": "TIME",
                    "duration_hours": 12,
                    "duration_days": None,
                    "base_temp_c": 22.0,
                    "ph_target": 5.8,
                    "ph_min": 5.5,
                    "ph_max": 6.1,
                    "ec_target": 1.5,
                    "ec_min": 1.2,
                    "ec_max": 1.8,
                    "irrigation_mode": "SUBSTRATE",
                    "irrigation_interval_sec": 600,
                    "irrigation_duration_sec": 15,
                    "lighting_photoperiod_hours": 18,
                    "lighting_start_time": "06:00:00",
                    "temp_air_target": 24.0,
                    "humidity_target": 65.0,
                    "co2_target": 800,
                    "extensions": {"base": {"k": "v"}},
                }
            ]
        if "from grow_cycle_overrides" in normalized:
            return [
                {
                    "grow_cycle_id": 101,
                    "parameter": "ph.target",
                    "value_type": "decimal",
                    "value": "5.9",
                }
            ]
        if "from zone_automation_logic_profiles" in normalized:
            return [
                {
                    "zone_id": 12,
                    "mode": "auto",
                    "subsystems": {
                        "irrigation": {
                            "enabled": False,
                            "execution": {
                                "interval_sec": 900,
                                "duration_sec": 25,
                            },
                        }
                    },
                    "updated_at": datetime(2026, 2, 22, 7, 0, 0),
                }
            ]
        return []

    async def fail_make_request(*_args, **_kwargs):
        raise AssertionError("effective-targets runtime path must not call HTTP API")

    monkeypatch.setattr(sql_read_model, "fetch", fake_fetch)
    monkeypatch.setattr("repositories.laravel_api_repository.make_request", fail_make_request)

    repo = LaravelApiRepository()
    payload = await repo.get_effective_targets_batch([12])

    assert 12 in payload
    zone_payload = payload[12]
    assert zone_payload is not None
    assert zone_payload["cycle_id"] == 101
    assert zone_payload["phase"]["code"] == "VEG"
    assert zone_payload["targets"]["ph"]["target"] == pytest.approx(5.9)
    assert zone_payload["targets"]["irrigation"]["interval_sec"] == 900
    assert zone_payload["targets"]["irrigation"]["execution"]["force_skip"] is True
    assert any("from grow_cycles gc" in call for call in query_calls)
    assert any("from grow_cycle_phases" in call for call in query_calls)


@pytest.mark.asyncio
async def test_effective_targets_read_model_uses_cache(monkeypatch):
    call_counter = {"fetch": 0}

    async def fake_fetch(query, *args):
        call_counter["fetch"] += 1
        normalized = _normalize_query(query)
        if "from grow_cycles gc" in normalized:
            return [
                {
                    "cycle_id": 77,
                    "zone_id": 3,
                    "status": "RUNNING",
                    "current_phase_id": 700,
                    "current_stage_code": "FLOWERING",
                    "phase_started_at": datetime(2026, 2, 22, 10, 0, 0),
                    "progress_meta": {},
                }
            ]
        if "from grow_cycle_phases" in normalized:
            return [
                {
                    "id": 700,
                    "name": "Flower",
                    "progress_model": "TIME",
                    "duration_hours": 24,
                    "duration_days": None,
                    "base_temp_c": None,
                    "ph_target": None,
                    "ph_min": None,
                    "ph_max": None,
                    "ec_target": 2.0,
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
                    "extensions": None,
                }
            ]
        return []

    monkeypatch.setattr(sql_read_model, "fetch", fake_fetch)

    repo = LaravelApiRepository()
    first = await repo.get_effective_targets_batch([3])
    second = await repo.get_effective_targets_batch([3])

    assert first[3] is not None
    assert second[3] is not None
    assert first[3]["cycle_id"] == second[3]["cycle_id"] == 77
    assert call_counter["fetch"] == 4
