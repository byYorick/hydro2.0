from __future__ import annotations

from datetime import datetime

import pytest

from ae2lite.api_zone_state import load_automation_timeline


@pytest.mark.asyncio
async def test_load_automation_timeline_compacts_noisy_duplicates_per_second() -> None:
    created_second = datetime(2026, 3, 3, 11, 53, 32)

    # SQL query in loader returns rows in DESC order.
    rows = [
        {
            "id": 110,
            "type": "SCHEDULE_TASK_EXECUTION_FINISHED",
            "payload_json": {"event_type": "SCHEDULE_TASK_EXECUTION_FINISHED"},
            "created_at": created_second.replace(microsecond=400000),
        },
        {
            "id": 109,
            "type": "TASK_FINISHED",
            "payload_json": {"event_type": "TASK_FINISHED", "reason_code": "prepare_recirculation_started"},
            "created_at": created_second.replace(microsecond=300000),
        },
        {
            "id": 108,
            "type": "SCHEDULE_TASK_EXECUTION_FINISHED",
            "payload_json": {"event_type": "SCHEDULE_TASK_EXECUTION_FINISHED"},
            "created_at": created_second.replace(microsecond=200000),
        },
        {
            "id": 107,
            "type": "TASK_FINISHED",
            "payload_json": {"event_type": "TASK_FINISHED", "reason_code": "prepare_recirculation_started"},
            "created_at": created_second.replace(microsecond=100000),
        },
        {
            "id": 106,
            "type": "COMMAND_DISPATCHED",
            "payload_json": {"event_type": "COMMAND_DISPATCHED", "reason_code": "prepare_recirculation_started"},
            "created_at": datetime(2026, 3, 3, 11, 53, 31, 200000),
        },
        {
            "id": 105,
            "type": "COMMAND_DISPATCHED",
            "payload_json": {"event_type": "COMMAND_DISPATCHED", "reason_code": "solution_fill_completed"},
            "created_at": datetime(2026, 3, 3, 11, 53, 31, 100000),
        },
        {
            "id": 104,
            "type": "TASK_STARTED",
            "payload_json": {"event_type": "TASK_STARTED"},
            "created_at": datetime(2026, 3, 3, 11, 53, 30, 100000),
        },
    ]

    async def fake_fetch(*_args, **_kwargs):
        return rows

    timeline = await load_automation_timeline(
        8,
        fetch_fn=fake_fetch,
        extract_timeline_reason_fn=lambda payload: payload.get("reason_code"),
        build_timeline_label_fn=lambda event_type, _reason: event_type,
        limit=24,
    )

    assert [item["event"] for item in timeline] == [
        "TASK_STARTED",
        "COMMAND_DISPATCHED",
        "COMMAND_DISPATCHED",
        "TASK_FINISHED",
        "SCHEDULE_TASK_EXECUTION_FINISHED",
    ]
    assert timeline[3]["label"] == "TASK_FINISHED ×2"
    assert timeline[3]["count"] == 2
    assert timeline[4]["label"] == "SCHEDULE_TASK_EXECUTION_FINISHED ×2"
    assert timeline[4]["count"] == 2
    assert timeline[2]["label"] == "COMMAND_DISPATCHED"
    assert timeline[2]["count"] == 1
    assert timeline[-1]["active"] is True
