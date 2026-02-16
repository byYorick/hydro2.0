"""Unit tests for application.task_events helpers."""

from datetime import datetime

from application.task_events import build_task_event_payload


def test_build_task_event_payload_increments_sequence_and_sets_base_fields():
    context = {"task_id": "st-1", "correlation_id": "corr-1"}
    payload = build_task_event_payload(
        zone_id=21,
        task_type="diagnostics",
        context=context,
        event_type="TANK_LEVEL_CHECKED",
        event_id_factory=lambda: "evt-fixed",
        occurred_at_factory=lambda: datetime(2026, 2, 16, 12, 0, 0),
    )

    assert context["event_seq"] == 1
    assert payload["event_id"] == "evt-fixed"
    assert payload["event_seq"] == 1
    assert payload["event_type"] == "TANK_LEVEL_CHECKED"
    assert payload["occurred_at"] == "2026-02-16T12:00:00"
    assert payload["zone_id"] == 21
    assert payload["task_type"] == "diagnostics"
    assert payload["task_id"] == "st-1"
    assert payload["correlation_id"] == "corr-1"


def test_build_task_event_payload_merges_custom_payload_and_continues_sequence():
    context = {"event_seq": 7}
    payload = build_task_event_payload(
        zone_id=9,
        task_type="irrigation",
        context=context,
        event_type="CUSTOM_EVENT",
        payload={"custom": 123, "event_type": "OVERRIDDEN"},
        event_id_factory=lambda: "evt-2",
        occurred_at_factory=lambda: datetime(2026, 2, 16, 13, 30, 0),
    )

    assert context["event_seq"] == 8
    assert payload["event_seq"] == 8
    assert payload["event_type"] == "OVERRIDDEN"
    assert payload["custom"] == 123
