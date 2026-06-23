from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from ae3lite.application.services.automation_observability import build_automation_observability


NOW = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)


def _task(
    *,
    status: str = "running",
    current_stage: str = "clean_fill_check",
    workflow_phase: str = "tank_filling",
    stage_entered_at: datetime | None = None,
    stage_deadline_at: datetime | None = None,
    correction_step: str | None = None,
):
    wf = SimpleNamespace(
        current_stage=current_stage,
        workflow_phase=workflow_phase,
        stage_entered_at=stage_entered_at or (NOW - timedelta(minutes=10)),
        stage_deadline_at=stage_deadline_at,
        pending_manual_step=None,
    )
    correction = None
    if correction_step is not None:
        correction = SimpleNamespace(corr_step=correction_step)
    return SimpleNamespace(
        id=42,
        status=status,
        topology="two_tank",
        workflow=wf,
        correction=correction,
    )


def test_waiting_command_emits_warning_hint():
    task = _task(status="waiting_command", current_stage="solution_fill_start", stage_entered_at=NOW - timedelta(minutes=3))
    payload = build_automation_observability(
        zone_id=1,
        task=task,
        workflow_state=None,
        telemetry={},
        telemetry_fetch_ok=True,
        now=NOW,
    )
    codes = {hint["code"] for hint in payload["hang_hints"]}
    assert "waiting_command_stuck" in codes


def test_stage_deadline_exceeded_is_critical():
    task = _task(
        stage_deadline_at=NOW - timedelta(seconds=30),
        stage_entered_at=NOW - timedelta(minutes=20),
    )
    payload = build_automation_observability(
        zone_id=1,
        task=task,
        workflow_state=None,
        telemetry={},
        telemetry_fetch_ok=True,
        now=NOW,
    )
    assert any(hint["code"] == "stage_deadline_exceeded" and hint["severity"] == "critical" for hint in payload["hang_hints"])


def test_offline_required_node_adds_hint():
    task = _task()
    payload = build_automation_observability(
        zone_id=1,
        task=task,
        workflow_state=None,
        telemetry={},
        telemetry_fetch_ok=True,
        now=NOW,
        node_rows=[
            {"node_uid": "irr-1", "node_type": "irrig", "status": "offline", "last_seen_age_sec": 900},
        ],
    )
    assert any(hint["code"] == "nodes_offline" for hint in payload["hang_hints"])


def test_no_active_task_during_workflow_phase():
    workflow = SimpleNamespace(workflow_phase="tank_filling", updated_at=NOW - timedelta(minutes=5))
    payload = build_automation_observability(
        zone_id=1,
        task=None,
        workflow_state=workflow,
        telemetry={},
        telemetry_fetch_ok=True,
        now=NOW,
    )
    assert any(hint["code"] == "no_active_task_during_workflow" for hint in payload["hang_hints"])


def test_task_dispatch_stuck_for_claimed_task():
    task = _task(
        status="claimed",
        current_stage="startup",
        stage_entered_at=NOW - timedelta(minutes=5),
    )
    task.updated_at = NOW - timedelta(minutes=5)
    payload = build_automation_observability(
        zone_id=1,
        task=task,
        workflow_state=None,
        telemetry={},
        telemetry_fetch_ok=True,
        now=NOW,
    )
    assert any(hint["code"] == "task_dispatch_stuck" for hint in payload["hang_hints"])
