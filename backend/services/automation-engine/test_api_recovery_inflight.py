from __future__ import annotations

import asyncio
import logging

import pytest

from ae2lite.api_recovery_inflight import recover_inflight_scheduler_tasks
from services.resilience_contract import SCHEDULER_TASK_RECOVERED_AFTER_RESTART


def _norm(query: str) -> str:
    return " ".join(str(query).split()).lower()


class _GaugeStub:
    def __init__(self) -> None:
        self.value = None

    def set(self, value) -> None:
        self.value = value


@pytest.mark.asyncio
async def test_recover_inflight_scheduler_tasks_recovers_tasks_and_intents():
    scheduler_tasks = {}
    scheduler_tasks_lock = asyncio.Lock()
    persisted = []
    zone_events = []
    gauge = _GaugeStub()

    async def fetch_stub(query, *args):
        q = _norm(query)
        if "with recent_logs as" in q:
            return [
                {
                    "task_name": "ae_scheduler_task_st-101",
                    "status": "accepted",
                    "created_at": None,
                    "details": {
                        "task_id": "st-101",
                        "zone_id": 8,
                        "task_type": "diagnostics",
                        "status": "accepted",
                        "payload": {"workflow": "cycle_start"},
                    },
                }
            ]
        if "from zone_automation_intents" in q and "where status in ('claimed', 'running')" in q:
            return [{"id": 501, "zone_id": 8, "status": "running"}]
        if "update zone_automation_intents" in q and "returning id" in q:
            return [{"id": 501}]
        raise AssertionError(f"unexpected query: {q}")

    def build_result_stub(*, error_code, reason, mode, action_required=True, decision="fail", reason_code=None):
        return {
            "error_code": error_code,
            "reason": reason,
            "mode": mode,
            "action_required": action_required,
            "decision": decision,
            "reason_code": reason_code,
        }

    async def persist_snapshot_stub(task):
        persisted.append(dict(task))

    async def create_zone_event_stub(zone_id, event_type, details):
        zone_events.append((zone_id, event_type, dict(details)))

    async def send_alert_stub(**_kwargs):
        return None

    summary = await recover_inflight_scheduler_tasks(
        enabled=True,
        fetch_fn=fetch_stub,
        scan_limit=100,
        build_execution_terminal_result_fn=build_result_stub,
        scheduler_tasks=scheduler_tasks,
        scheduler_tasks_lock=scheduler_tasks_lock,
        persist_scheduler_task_snapshot_fn=persist_snapshot_stub,
        create_zone_event_fn=create_zone_event_stub,
        send_infra_exception_alert_fn=send_alert_stub,
        task_recovery_success_rate_gauge=gauge,
        logger=logging.getLogger("test.recovery.inflight"),
    )

    assert summary["scanned"] == 1
    assert summary["inflight"] == 1
    assert summary["recovered"] == 1
    assert summary["intents_scanned"] == 1
    assert summary["intents_recovered"] == 1
    assert gauge.value == 1.0
    assert scheduler_tasks["st-101"]["status"] == "failed"
    assert scheduler_tasks["st-101"]["error_code"] == SCHEDULER_TASK_RECOVERED_AFTER_RESTART
    assert len(persisted) == 1
    assert len([event_type for _, event_type, _ in zone_events if event_type == "SCHEDULE_TASK_FAILED"]) == 2
