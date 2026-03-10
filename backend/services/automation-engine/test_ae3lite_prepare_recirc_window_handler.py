from __future__ import annotations

from datetime import datetime, timezone

from ae3lite.application.handlers.prepare_recirc_window import PrepareRecircWindowHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.services.topology_registry import StageDef


NOW = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)


def _make_task(*, retry_count: int) -> AutomationTask:
    return AutomationTask.from_row({
        "id": 8,
        "zone_id": 80,
        "task_type": "cycle_start",
        "status": "running",
        "idempotency_key": "k8",
        "scheduled_for": NOW,
        "due_at": NOW,
        "claimed_by": "w1",
        "claimed_at": NOW,
        "error_code": None,
        "error_message": None,
        "created_at": NOW,
        "updated_at": NOW,
        "completed_at": None,
        "topology": "two_tank",
        "intent_source": None,
        "intent_trigger": None,
        "intent_id": None,
        "intent_meta": {},
        "current_stage": "prepare_recirculation_window_exhausted",
        "workflow_phase": "tank_recirc",
        "stage_deadline_at": None,
        "stage_retry_count": retry_count,
        "stage_entered_at": NOW,
        "clean_fill_cycle": 1,
        "corr_step": None,
    })


class _MockPlan:
    runtime = {
        "correction": {
            "prepare_recirculation_max_attempts": 3,
        }
    }
    named_plans = {
        "prepare_recirculation_stop": ("stop",),
        "sensor_mode_deactivate": ("deactivate",),
        "sensor_mode_activate": ("activate",),
        "prepare_recirculation_start": ("start",),
    }


class _MockGateway:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def run_batch(self, *, task, commands, now):
        self.calls.append(tuple(commands))
        return {"success": True, "error_code": None, "error_message": None}


class _MockAlertRepo:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create_or_update_active(self, **kwargs):
        self.calls.append(kwargs)
        return 101


async def test_prepare_recirc_window_restarts_when_limit_not_reached():
    gateway = _MockGateway()
    alerts = _MockAlertRepo()
    handler = PrepareRecircWindowHandler(
        runtime_monitor=object(),
        command_gateway=gateway,
        alert_repository=alerts,
    )

    outcome = await handler.run(
        task=_make_task(retry_count=1),
        plan=_MockPlan(),
        stage_def=StageDef("prepare_recirculation_window_exhausted", "prepare_recirc_window"),
        now=NOW,
    )

    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_check"
    assert outcome.stage_retry_count == 1
    assert len(gateway.calls) == 2
    assert alerts.calls == []


async def test_prepare_recirc_window_fails_and_creates_alert_at_limit():
    gateway = _MockGateway()
    alerts = _MockAlertRepo()
    handler = PrepareRecircWindowHandler(
        runtime_monitor=object(),
        command_gateway=gateway,
        alert_repository=alerts,
    )

    outcome = await handler.run(
        task=_make_task(retry_count=3),
        plan=_MockPlan(),
        stage_def=StageDef("prepare_recirculation_window_exhausted", "prepare_recirc_window"),
        now=NOW,
    )

    assert outcome.kind == "fail"
    assert outcome.error_code == "prepare_recirculation_attempt_limit_reached"
    assert len(gateway.calls) == 1
    assert alerts.calls[0]["code"] == "biz_prepare_recirculation_retry_exhausted"
    assert alerts.calls[0]["details"]["retry_count"] == 3
