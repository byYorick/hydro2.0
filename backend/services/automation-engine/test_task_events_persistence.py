from __future__ import annotations

import pytest

from executor.task_events_persistence import persist_zone_event_safe


class _ZoneDeletedFKError(Exception):
    sqlstate = "23503"


@pytest.mark.asyncio
async def test_persist_zone_event_safe_skips_alert_for_deleted_zone_fk_violation():
    log_calls = []
    infra_alert_calls = []

    async def create_zone_event_fn(*_args, **_kwargs):
        raise _ZoneDeletedFKError(
            "insert or update on table \"zone_events\" violates foreign key constraint "
            "\"zone_events_zone_id_foreign\""
        )

    async def send_infra_alert_fn(**kwargs):
        infra_alert_calls.append(dict(kwargs))

    def log_warning(message, *args, **kwargs):
        log_calls.append({"message": message, "args": args, "kwargs": kwargs})

    ok = await persist_zone_event_safe(
        zone_id=21,
        event_type="SCHEDULE_TASK_EXECUTION_FINISHED",
        payload={"success": True},
        task_type="diagnostics",
        context={"task_id": "st-21", "correlation_id": "corr-21"},
        create_zone_event_fn=create_zone_event_fn,
        send_infra_alert_fn=send_infra_alert_fn,
        log_warning=log_warning,
    )

    assert ok is False
    assert len(log_calls) == 1
    assert "deleted zone" in log_calls[0]["message"]
    assert infra_alert_calls == []


@pytest.mark.asyncio
async def test_persist_zone_event_safe_sends_alert_for_unexpected_errors():
    log_calls = []
    infra_alert_calls = []

    async def create_zone_event_fn(*_args, **_kwargs):
        raise RuntimeError("db write failed")

    async def send_infra_alert_fn(**kwargs):
        infra_alert_calls.append(dict(kwargs))

    def log_warning(message, *args, **kwargs):
        log_calls.append({"message": message, "args": args, "kwargs": kwargs})

    ok = await persist_zone_event_safe(
        zone_id=22,
        event_type="SCHEDULE_TASK_EXECUTION_FINISHED",
        payload={"success": True},
        task_type="diagnostics",
        context={"task_id": "st-22", "correlation_id": "corr-22"},
        create_zone_event_fn=create_zone_event_fn,
        send_infra_alert_fn=send_infra_alert_fn,
        log_warning=log_warning,
    )

    assert ok is False
    assert len(log_calls) == 1
    assert "Failed to persist scheduler task zone event" in log_calls[0]["message"]
    assert log_calls[0]["kwargs"].get("exc_info") is True
    assert len(infra_alert_calls) == 1
    assert infra_alert_calls[0]["code"] == "infra_scheduler_task_event_persist_failed"

