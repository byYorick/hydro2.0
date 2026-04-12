"""Tests for PgZoneIntentRepository.extract_intent_metadata (typed columns)."""

from __future__ import annotations

import pytest

from ae3lite.domain.errors import TaskCreateError
from ae3lite.infrastructure.repositories.zone_intent_repository import PgZoneIntentRepository


@pytest.fixture
def repo() -> PgZoneIntentRepository:
    return PgZoneIntentRepository()


_BASE_ROW = {
    "id": 42,
    "zone_id": 7,
    "intent_type": "diagnostics_tick",
    "retry_count": 0,
    "task_type": "cycle_start",
    "topology": "two_tank",
    "intent_source": "laravel_scheduler",
    "irrigation_mode": None,
    "irrigation_requested_duration_sec": None,
}


class TestCycleStart:
    def test_basic_cycle_start(self, repo: PgZoneIntentRepository) -> None:
        meta = repo.extract_intent_metadata(source="laravel_scheduler", intent_row=_BASE_ROW)
        assert meta.task_type == "cycle_start"
        assert meta.current_stage == "startup"
        assert meta.workflow_phase == "idle"
        assert meta.topology == "two_tank"
        assert meta.intent_source == "laravel_scheduler"
        assert meta.intent_trigger == "diagnostics_tick"
        assert meta.intent_id == 42
        assert meta.irrigation_mode is None
        assert meta.irrigation_requested_duration_sec is None

    def test_intent_meta_populated(self, repo: PgZoneIntentRepository) -> None:
        meta = repo.extract_intent_metadata(source="laravel_scheduler", intent_row=_BASE_ROW)
        assert meta.intent_meta["intent_type"] == "diagnostics_tick"
        assert meta.intent_meta["intent_retry_count"] == 0
        assert meta.intent_meta["intent_zone_id"] == 7
        assert meta.intent_meta["intent_payload"] == {}


class TestIrrigation:
    def test_irrigation_start_maps_correctly(self, repo: PgZoneIntentRepository) -> None:
        row = {
            **_BASE_ROW,
            "task_type": "irrigation_start",
            "intent_type": "irrigate_once",
            "irrigation_mode": "normal",
            "irrigation_requested_duration_sec": 120,
        }
        meta = repo.extract_intent_metadata(source="zone_ui", intent_row=row)
        assert meta.task_type == "irrigation_start"
        assert meta.current_stage == "await_ready"
        assert meta.workflow_phase == "ready"
        assert meta.irrigation_mode == "normal"
        assert meta.irrigation_requested_duration_sec == 120

    def test_irrigation_force_mode(self, repo: PgZoneIntentRepository) -> None:
        row = {**_BASE_ROW, "task_type": "irrigation_start", "irrigation_mode": "force"}
        meta = repo.extract_intent_metadata(source="api", intent_row=row)
        assert meta.irrigation_mode == "force"

    def test_irrigation_missing_mode_defaults_normal(self, repo: PgZoneIntentRepository) -> None:
        row = {**_BASE_ROW, "task_type": "irrigation_start", "irrigation_mode": None}
        meta = repo.extract_intent_metadata(source="api", intent_row=row)
        assert meta.irrigation_mode == "normal"

    def test_irrigation_invalid_duration_ignored(self, repo: PgZoneIntentRepository) -> None:
        row = {**_BASE_ROW, "task_type": "irrigation_start", "irrigation_requested_duration_sec": "bad"}
        meta = repo.extract_intent_metadata(source="api", intent_row=row)
        assert meta.irrigation_requested_duration_sec is None

    def test_irrigation_duration_clamped_to_1(self, repo: PgZoneIntentRepository) -> None:
        row = {**_BASE_ROW, "task_type": "irrigation_start", "irrigation_requested_duration_sec": 0}
        meta = repo.extract_intent_metadata(source="api", intent_row=row)
        assert meta.irrigation_requested_duration_sec == 1


class TestLightingTick:
    def test_lighting_tick_maps_correctly(self, repo: PgZoneIntentRepository) -> None:
        row = {
            **_BASE_ROW,
            "task_type": "lighting_tick",
            "intent_type": "lighting_tick",
            "topology": "whatever",
        }
        meta = repo.extract_intent_metadata(source="laravel_scheduler", intent_row=row)
        assert meta.task_type == "lighting_tick"
        assert meta.current_stage == "apply"
        assert meta.workflow_phase == "ready"
        assert meta.topology == "lighting_tick"
        assert meta.irrigation_mode is None
        assert meta.irrigation_requested_duration_sec is None


class TestEdgeCases:
    def test_topology_missing_raises_task_create_error(self, repo: PgZoneIntentRepository) -> None:
        row = {**_BASE_ROW, "topology": ""}
        with pytest.raises(TaskCreateError) as exc:
            repo.extract_intent_metadata(source="test", intent_row=row)
        assert exc.value.code == "start_cycle_intent_topology_missing"
        assert exc.value.details["intent_id"] == 42

    def test_topology_none_raises(self, repo: PgZoneIntentRepository) -> None:
        row = {**_BASE_ROW, "topology": None}
        with pytest.raises(TaskCreateError):
            repo.extract_intent_metadata(source="test", intent_row=row)

    def test_intent_id_none_when_missing(self, repo: PgZoneIntentRepository) -> None:
        row = {**_BASE_ROW, "id": None}
        meta = repo.extract_intent_metadata(source="test", intent_row=row)
        assert meta.intent_id is None

    def test_intent_id_zero_preserved(self, repo: PgZoneIntentRepository) -> None:
        row = {**_BASE_ROW, "id": 0}
        meta = repo.extract_intent_metadata(source="test", intent_row=row)
        assert meta.intent_id == 0

    def test_source_from_intent_row_preferred(self, repo: PgZoneIntentRepository) -> None:
        row = {**_BASE_ROW, "intent_source": "custom_source"}
        meta = repo.extract_intent_metadata(source="fallback", intent_row=row)
        assert meta.intent_source == "custom_source"

    def test_source_fallback_to_param(self, repo: PgZoneIntentRepository) -> None:
        row = {**_BASE_ROW, "intent_source": None}
        meta = repo.extract_intent_metadata(source="from_param", intent_row=row)
        assert meta.intent_source == "from_param"

    def test_source_defaults_to_laravel_scheduler(self, repo: PgZoneIntentRepository) -> None:
        row = {**_BASE_ROW, "intent_source": None}
        meta = repo.extract_intent_metadata(source="", intent_row=row)
        assert meta.intent_source == "laravel_scheduler"

    def test_trigger_defaults_when_intent_type_missing(self, repo: PgZoneIntentRepository) -> None:
        row = {**_BASE_ROW, "intent_type": None}
        meta = repo.extract_intent_metadata(source="test", intent_row=row)
        assert meta.intent_trigger == "start_cycle_api"

    def test_retry_count_from_row(self, repo: PgZoneIntentRepository) -> None:
        row = {**_BASE_ROW, "retry_count": 3}
        meta = repo.extract_intent_metadata(source="test", intent_row=row)
        assert meta.intent_meta["intent_retry_count"] == 3

    def test_task_type_defaults_to_cycle_start(self, repo: PgZoneIntentRepository) -> None:
        row = {**_BASE_ROW, "task_type": None}
        meta = repo.extract_intent_metadata(source="test", intent_row=row)
        assert meta.task_type == "cycle_start"
