"""Unit tests for application.task_context helpers."""

from application.task_context import build_task_context


def test_build_task_context_from_none():
    context = build_task_context(None)
    assert context == {
        "task_id": "",
        "correlation_id": "",
        "scheduled_for": None,
        "event_seq": 0,
    }


def test_build_task_context_normalizes_fields():
    context = build_task_context(
        {
            "task_id": 123,
            "correlation_id": "corr-1",
            "scheduled_for": "2026-02-16T12:00:00",
            "event_seq": 99,
        }
    )
    assert context == {
        "task_id": "123",
        "correlation_id": "corr-1",
        "scheduled_for": "2026-02-16T12:00:00",
        "event_seq": 0,
    }
