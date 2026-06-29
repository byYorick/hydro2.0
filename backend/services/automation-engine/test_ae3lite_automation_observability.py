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
    correction_wait_until: datetime | None = None,
    correction_stabilization_sec: int | None = None,
    task_updated_at: datetime | None = None,
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
        correction = SimpleNamespace(
            corr_step=correction_step,
            wait_until=correction_wait_until,
            stabilization_sec=correction_stabilization_sec or 0,
        )
    task = SimpleNamespace(
        id=42,
        status=status,
        topology="two_tank",
        workflow=wf,
        correction=correction,
    )
    if task_updated_at is not None:
        task.updated_at = task_updated_at
    return task


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


def test_irrigation_check_within_stage_deadline_skips_stage_elapsed_long():
    task = _task(
        current_stage="irrigation_check",
        workflow_phase="irrigating",
        stage_entered_at=NOW - timedelta(seconds=362),
        stage_deadline_at=NOW + timedelta(seconds=628),
    )
    payload = build_automation_observability(
        zone_id=6,
        task=task,
        workflow_state=None,
        telemetry={},
        telemetry_fetch_ok=True,
        now=NOW,
    )
    codes = {hint["code"] for hint in payload["hang_hints"]}
    assert "stage_elapsed_long" not in codes


def test_irrigation_check_past_stage_deadline_still_reports_deadline_exceeded():
    task = _task(
        current_stage="irrigation_check",
        workflow_phase="irrigating",
        stage_entered_at=NOW - timedelta(seconds=1200),
        stage_deadline_at=NOW - timedelta(seconds=30),
    )
    payload = build_automation_observability(
        zone_id=6,
        task=task,
        workflow_state=None,
        telemetry={},
        telemetry_fetch_ok=True,
        now=NOW,
    )
    codes = {hint["code"] for hint in payload["hang_hints"]}
    assert "stage_deadline_exceeded" in codes


def test_corr_wait_ec_within_wait_until_skips_correction_substep_stalled():
    task = _task(
        status="pending",
        current_stage="irrigation_check",
        workflow_phase="irrigating",
        stage_entered_at=NOW - timedelta(minutes=12),
        correction_step="corr_wait_ec",
        correction_wait_until=NOW + timedelta(minutes=4),
    )
    payload = build_automation_observability(
        zone_id=6,
        task=task,
        workflow_state=None,
        telemetry={},
        telemetry_fetch_ok=True,
        now=NOW,
    )
    codes = {hint["code"] for hint in payload["hang_hints"]}
    assert "correction_substep_stalled" not in codes


def test_corr_wait_ec_after_wait_until_uses_substep_elapsed_not_stage_elapsed():
    task = _task(
        status="pending",
        current_stage="irrigation_check",
        workflow_phase="irrigating",
        stage_entered_at=NOW - timedelta(minutes=12),
        correction_step="corr_wait_ec",
        correction_wait_until=NOW - timedelta(seconds=30),
        task_updated_at=NOW - timedelta(minutes=4),
    )
    payload = build_automation_observability(
        zone_id=6,
        task=task,
        workflow_state=None,
        telemetry={},
        telemetry_fetch_ok=True,
        now=NOW,
    )
    codes = {hint["code"] for hint in payload["hang_hints"]}
    assert "correction_substep_stalled" in codes


def test_ready_workflow_after_failure_rollback_reports_complete_ready_stage():
    workflow = SimpleNamespace(
        workflow_phase="ready",
        updated_at=NOW - timedelta(minutes=3),
        payload={
            "ae3_cycle_start_stage": "irrigation_check",
            "ae3_failure_rollback": True,
            "ae3_failed_task_id": 6,
        },
    )
    payload = build_automation_observability(
        zone_id=6,
        task=None,
        workflow_state=workflow,
        telemetry={},
        telemetry_fetch_ok=True,
        now=NOW,
    )
    assert payload["runtime"]["workflow_phase"] == "ready"
    assert payload["runtime"]["current_stage"] == "complete_ready"
    assert payload["runtime"]["task_is_active"] is False
