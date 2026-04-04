"""Tests for LegacyIntentMapper.

Covers the None-safe id/zone_id extraction pattern introduced to avoid
the ``int(x or 0) or None`` bug where a legitimate id=0 would be coerced
to None.  The fix uses ``int(v) if v is not None else None`` instead.
"""

from __future__ import annotations

import pytest

from ae3lite.application.adapters.legacy_intent_mapper import LegacyIntentMapper
from ae3lite.domain.errors import TaskCreateError


@pytest.fixture()
def mapper() -> LegacyIntentMapper:
    return LegacyIntentMapper()


def _intent_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {"topology": "two_tank"}
    row.update(overrides)
    return row


class TestExtractIntentMetadata:
    def test_intent_id_none_when_missing(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(source="test", intent_row=_intent_row())
        assert meta.intent_id is None

    def test_intent_id_preserved_as_int(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(source="test", intent_row=_intent_row(id=42))
        assert meta.intent_id == 42

    def test_intent_id_zero_preserved(self, mapper: LegacyIntentMapper) -> None:
        """id=0 must NOT be converted to None.

        Regression guard: the fix uses ``int(_raw_id) if _raw_id is not None else None``
        so that 0 (falsy but valid) is kept as 0, not discarded.
        """
        meta = mapper.extract_intent_metadata(source="test", intent_row=_intent_row(id=0))
        assert meta.intent_id == 0

    def test_intent_id_string_numeric_coerced(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(source="test", intent_row=_intent_row(id="77"))
        assert meta.intent_id == 77

    def test_intent_zone_id_none_when_missing(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(source="test", intent_row=_intent_row())
        assert meta.intent_meta["intent_zone_id"] is None

    def test_intent_zone_id_preserved(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(source="test", intent_row=_intent_row(zone_id=99))
        assert meta.intent_meta["intent_zone_id"] == 99

    def test_intent_zone_id_zero_preserved(self, mapper: LegacyIntentMapper) -> None:
        """zone_id=0 must NOT be converted to None.

        Regression guard: uses the same ``int(v) if v is not None else None``
        lambda so that 0 is kept, not fallen back to None.
        """
        meta = mapper.extract_intent_metadata(source="test", intent_row=_intent_row(zone_id=0))
        assert meta.intent_meta["intent_zone_id"] == 0

    def test_topology_missing_fails_closed(self, mapper: LegacyIntentMapper) -> None:
        with pytest.raises(TaskCreateError) as exc:
            mapper.extract_intent_metadata(source="test", intent_row={})

        assert exc.value.code == "start_cycle_intent_topology_missing"

    def test_topology_from_payload(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(
            source="test",
            intent_row={"payload": {"topology": "single_tank"}},
        )
        assert meta.topology == "single_tank"

    def test_topology_from_intent_row_when_payload_missing(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(
            source="test",
            intent_row={"topology": "single_tank"},
        )
        assert meta.topology == "single_tank"

    def test_lighting_tick_intent_maps_to_lighting_topology_and_task(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(
            source="laravel_scheduler",
            intent_row={
                "id": 5,
                "zone_id": 1,
                "intent_type": "LIGHTING_TICK",
                "payload": {
                    "source": "laravel_scheduler",
                    "task_type": "lighting_tick",
                    "workflow": "lighting_tick",
                    "topology": "lighting_tick",
                },
            },
        )
        assert meta.task_type == "lighting_tick"
        assert meta.topology == "lighting_tick"
        assert meta.current_stage == "apply"

    def test_source_defaults_to_laravel_scheduler(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(source="", intent_row=_intent_row())
        assert meta.intent_source == "laravel_scheduler"

    def test_source_none_defaults_to_laravel_scheduler(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(source=None, intent_row=_intent_row())  # type: ignore[arg-type]
        assert meta.intent_source == "laravel_scheduler"

    def test_source_preserved_when_given(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(source="cron", intent_row=_intent_row())
        assert meta.intent_source == "cron"

    def test_trigger_defaults_to_start_cycle_api_when_intent_type_missing(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(source="test", intent_row=_intent_row())
        assert meta.intent_trigger == "start_cycle_api"

    def test_trigger_uses_real_intent_type_when_present(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(
            source="test",
            intent_row=_intent_row(intent_type="VENTILATION_TICK"),
        )
        assert meta.intent_trigger == "ventilation_tick"

    def test_retry_count_defaults_to_zero(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(source="test", intent_row=_intent_row())
        assert meta.intent_meta["intent_retry_count"] == 0

    def test_retry_count_from_row(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(source="test", intent_row=_intent_row(retry_count=3))
        assert meta.intent_meta["intent_retry_count"] == 3

    def test_intent_type_lowercased(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(
            source="test",
            intent_row=_intent_row(intent_type="IRRIGATE_ONCE"),
        )
        assert meta.intent_meta["intent_type"] == "irrigate_once"

    def test_intent_type_none_when_missing(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(source="test", intent_row=_intent_row())
        assert meta.intent_meta["intent_type"] is None

    def test_intent_payload_empty_dict_when_no_payload(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(source="test", intent_row=_intent_row())
        assert meta.intent_meta["intent_payload"] == {}

    def test_intent_payload_extracted_from_mapping(self, mapper: LegacyIntentMapper) -> None:
        meta = mapper.extract_intent_metadata(
            source="test",
            intent_row={"payload": {"workflow": "cycle_start", "topology": "two_tank"}},
        )
        assert meta.intent_meta["intent_payload"]["workflow"] == "cycle_start"


class TestBuildCycleStartPayload:
    def test_intent_id_none_when_missing(self, mapper: LegacyIntentMapper) -> None:
        payload = mapper.build_cycle_start_payload(
            zone_id=5, source="test", intent_row={}, idempotency_key="k1-valid",
        )
        assert payload["intent_id"] is None

    def test_intent_id_positive_preserved(self, mapper: LegacyIntentMapper) -> None:
        payload = mapper.build_cycle_start_payload(
            zone_id=5, source="test", intent_row={"id": 77}, idempotency_key="k1-valid",
        )
        assert payload["intent_id"] == 77

    def test_intent_id_zero_preserved(self, mapper: LegacyIntentMapper) -> None:
        """Regression: id=0 must not become None.

        Uses ``int(v) if v is not None else None`` lambda, so 0 (falsy) stays 0.
        """
        payload = mapper.build_cycle_start_payload(
            zone_id=5, source="test", intent_row={"id": 0}, idempotency_key="k1-valid",
        )
        assert payload["intent_id"] == 0

    def test_intent_zone_id_uses_row_value(self, mapper: LegacyIntentMapper) -> None:
        """zone_id from intent_row takes precedence over fallback parameter."""
        payload = mapper.build_cycle_start_payload(
            zone_id=5, source="test", intent_row={"zone_id": 99}, idempotency_key="k1-valid",
        )
        assert payload["intent_zone_id"] == 99

    def test_intent_zone_id_falls_back_to_parameter(self, mapper: LegacyIntentMapper) -> None:
        """When zone_id absent from intent_row, the zone_id parameter is used as fallback."""
        payload = mapper.build_cycle_start_payload(
            zone_id=5, source="test", intent_row={}, idempotency_key="k1-valid",
        )
        assert payload["intent_zone_id"] == 5

    def test_idempotency_key_preserved(self, mapper: LegacyIntentMapper) -> None:
        payload = mapper.build_cycle_start_payload(
            zone_id=5, source="test", intent_row={}, idempotency_key="sch:z5:abc-key",
        )
        assert payload["idempotency_key"] == "sch:z5:abc-key"

    def test_workflow_always_cycle_start(self, mapper: LegacyIntentMapper) -> None:
        payload = mapper.build_cycle_start_payload(
            zone_id=5, source="test", intent_row={}, idempotency_key="k1-valid",
        )
        assert payload["workflow"] == "cycle_start"

    def test_trigger_defaults_to_start_cycle_api_when_intent_type_missing(self, mapper: LegacyIntentMapper) -> None:
        payload = mapper.build_cycle_start_payload(
            zone_id=5, source="test", intent_row={}, idempotency_key="k1-valid",
        )
        assert payload["trigger"] == "start_cycle_api"

    def test_trigger_uses_real_intent_type_when_present(self, mapper: LegacyIntentMapper) -> None:
        payload = mapper.build_cycle_start_payload(
            zone_id=5,
            source="test",
            intent_row={"intent_type": "LIGHTING_TICK"},
            idempotency_key="k1-valid",
        )
        assert payload["trigger"] == "lighting_tick"

    def test_source_defaults_to_laravel_scheduler_when_empty(self, mapper: LegacyIntentMapper) -> None:
        payload = mapper.build_cycle_start_payload(
            zone_id=5, source="", intent_row={}, idempotency_key="k1-valid",
        )
        assert payload["source"] == "laravel_scheduler"

    def test_retry_count_defaults_to_zero(self, mapper: LegacyIntentMapper) -> None:
        payload = mapper.build_cycle_start_payload(
            zone_id=5, source="test", intent_row={}, idempotency_key="k1-valid",
        )
        assert payload["intent_retry_count"] == 0
