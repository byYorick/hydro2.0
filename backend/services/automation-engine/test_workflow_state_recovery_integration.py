from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

from ae2lite.api_recovery import recover_zone_workflow_states


class _WorkflowStore:
    def __init__(self, rows):
        self._rows = rows
        self.set_calls = []

    async def list_active(self):
        return list(self._rows)

    async def set(self, *, zone_id, workflow_phase, payload, scheduler_task_id):
        self.set_calls.append(
            {
                "zone_id": zone_id,
                "workflow_phase": workflow_phase,
                "payload": payload,
                "scheduler_task_id": scheduler_task_id,
            }
        )


@pytest.mark.asyncio
async def test_recover_zone_workflow_states_enqueues_continuation():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    store = _WorkflowStore(
        [
            {
                "zone_id": 21,
                "workflow_phase": "tank_filling",
                "workflow_phase_raw": "tank_filling",
                "payload": {
                    "workflow": "startup",
                    "clean_fill_started_at": (now - timedelta(minutes=2)).isoformat(),
                    "payload_contract_version": "v2",
                },
                "updated_at": now - timedelta(seconds=30),
                "scheduler_task_id": "st-old-1",
            }
        ]
    )
    events = []
    enqueue_calls = []

    async def create_zone_event_fn(zone_id, event_type, details):
        events.append((zone_id, event_type, details))

    async def enqueue_internal_scheduler_task_fn(**kwargs):
        enqueue_calls.append(kwargs)
        return {"enqueue_id": "enq-21", "correlation_id": "corr-21"}

    async def send_infra_exception_alert_fn(**kwargs):
        return None

    summary = await recover_zone_workflow_states(
        enabled=True,
        stale_timeout_sec=300,
        workflow_state_store=store,
        logger=logging.getLogger("test.workflow_recovery"),
        create_zone_event_fn=create_zone_event_fn,
        enqueue_internal_scheduler_task_fn=enqueue_internal_scheduler_task_fn,
        send_infra_exception_alert_fn=send_infra_exception_alert_fn,
        get_trace_id_fn=lambda: "trace-recovery-1",
    )

    assert summary["active"] == 1
    assert summary["recovered"] == 1
    assert summary["failed"] == 0
    assert len(enqueue_calls) == 1
    assert enqueue_calls[0]["zone_id"] == 21
    assert enqueue_calls[0]["task_type"] == "diagnostics"
    assert enqueue_calls[0]["payload"]["workflow"] == "clean_fill_check"
    assert len(store.set_calls) == 1
    assert store.set_calls[0]["scheduler_task_id"] == "enq-21"
    assert any(event_type == "WORKFLOW_RECOVERY_ENQUEUED" for _, event_type, _ in events)
