from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
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


def _irrigation_task(*, outcome: str, reason: str, task_type: str = "irrigation_start"):
    task = _task(
        status="completed",
        current_stage="decision_gate",
        workflow_phase="idle",
        stage_entered_at=NOW - timedelta(seconds=5),
    )
    task.task_type = task_type
    task.irrigation_decision_outcome = outcome
    task.irrigation_decision_reason_code = reason
    return task


def test_moisture_skip_emits_one_irrigation_sensor_blocked():
    task = _irrigation_task(outcome="skip", reason="smart_soil_telemetry_missing_or_stale")
    payload = build_automation_observability(
        zone_id=6,
        task=task,
        workflow_state=None,
        telemetry={},
        telemetry_fetch_ok=True,
        now=NOW,
    )
    blocked = [hint for hint in payload["hang_hints"] if hint["code"] == "irrigation_sensor_blocked"]
    assert len(blocked) == 1
    assert blocked[0]["severity"] == "critical"
    assert blocked[0]["details"]["reason_code"] == "smart_soil_telemetry_missing_or_stale"
    assert blocked[0]["message"] == "Полив пропущен: нет свежего измерения влажности. Насос не запускался."
    assert not any(hint["code"] == "solution_temp_blocked" for hint in payload["hang_hints"])

    target_missing = _irrigation_task(outcome="skip", reason="smart_soil_target_missing")
    target_payload = build_automation_observability(
        zone_id=6,
        task=target_missing,
        workflow_state=None,
        telemetry={},
        telemetry_fetch_ok=True,
        now=NOW,
    )
    target_hints = [hint for hint in target_payload["hang_hints"] if hint["code"] == "irrigation_sensor_blocked"]
    assert len(target_hints) == 1
    assert target_hints[0]["details"]["reason_code"] == "smart_soil_target_missing"


def test_healthy_irrigation_run_does_not_emit_irrigation_sensor_blocked():
    task = _irrigation_task(outcome="run", reason="smart_soil_below_min")
    task.status = "running"
    payload = build_automation_observability(
        zone_id=6,
        task=task,
        workflow_state=None,
        telemetry={},
        telemetry_fetch_ok=True,
        now=NOW,
    )
    codes = {hint["code"] for hint in payload["hang_hints"]}
    assert "irrigation_sensor_blocked" not in codes
    assert "solution_temp_blocked" not in codes


def test_solution_temp_skip_emits_one_solution_temp_blocked():
    task = _irrigation_task(outcome="skip", reason="solution_temp_out_of_band")
    payload = build_automation_observability(
        zone_id=6,
        task=task,
        workflow_state=None,
        telemetry={},
        telemetry_fetch_ok=True,
        now=NOW,
    )
    blocked = [hint for hint in payload["hang_hints"] if hint["code"] == "solution_temp_blocked"]
    assert len(blocked) == 1
    assert blocked[0]["severity"] == "critical"
    assert not any(hint["code"] == "irrigation_sensor_blocked" for hint in payload["hang_hints"])


def test_within_band_skip_and_other_task_type_do_not_emit_irrigation_block():
    within_band = _irrigation_task(outcome="skip", reason="smart_soil_within_band")
    lighting = _irrigation_task(
        outcome="skip",
        reason="smart_soil_telemetry_missing_or_stale",
        task_type="lighting_tick",
    )
    for task in (within_band, lighting):
        payload = build_automation_observability(
            zone_id=6,
            task=task,
            workflow_state=None,
            telemetry={},
            telemetry_fetch_ok=True,
            now=NOW,
        )
        codes = {hint["code"] for hint in payload["hang_hints"]}
        assert "irrigation_sensor_blocked" not in codes
        assert "solution_temp_blocked" not in codes


def test_crop_day_codes_exist_in_error_catalog():
    path = Path("/app/error_codes.json")
    if not path.is_file():
        path = Path(__file__).resolve().parents[1] / "error_codes.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    by_code = {row["code"]: row for row in catalog["codes"]}
    for code in (
        "smart_soil_target_missing",
        "smart_soil_telemetry_missing_or_stale",
        "solution_temp_out_of_band",
        "solution_temp_unavailable",
        "dli_sensor_unavailable",
        "solution_refresh_recommended",
    ):
        row = by_code[code]
        assert any("а" <= ch <= "я" or "А" <= ch <= "Я" for ch in row["title"])
        assert row["message"].strip()
    for code in ("dli_sensor_unavailable", "solution_refresh_recommended"):
        assert any("а" <= ch <= "я" or "А" <= ch <= "Я" for ch in by_code[code]["message"])
