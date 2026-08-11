from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ae3lite.domain.entities import AutomationTask, ZoneLease, ZoneWorkflow
from ae3lite.domain.entities.workflow_state import WorkflowState


def test_automation_task_claimability_is_pending_only() -> None:
    now = datetime.now(timezone.utc)
    wf = WorkflowState(
        current_stage="startup",
        workflow_phase="idle",
        stage_deadline_at=None,
        stage_retry_count=0,
        stage_entered_at=None,
        clean_fill_cycle=0,
    )
    task = AutomationTask(
        id=1,
        zone_id=11,
        task_type="cycle_start",
        status="pending",
        idempotency_key="test-key",
        scheduled_for=now,
        due_at=now,
        claimed_by=None,
        claimed_at=None,
        error_code=None,
        error_message=None,
        created_at=now,
        updated_at=now,
        completed_at=None,
        topology="two_tank",
        intent_source=None,
        intent_trigger=None,
        intent_id=None,
        intent_meta={},
        workflow=wf,
        correction=None,
    )

    assert task.is_active is True
    assert task.can_be_claimed is True
    assert task.current_stage == "startup"
    assert task.workflow_phase == "idle"

    # from_row с v2-колонками
    running_row = {
        "id": 1, "zone_id": 11, "task_type": "cycle_start", "status": "running",
        "idempotency_key": "test-key", "scheduled_for": now, "due_at": now,
        "claimed_by": "w1", "claimed_at": now, "error_code": None, "error_message": None,
        "created_at": now, "updated_at": now, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "startup", "workflow_phase": "idle",
        "stage_deadline_at": None, "stage_retry_count": 0,
        "stage_entered_at": None, "clean_fill_cycle": 0,
        "corr_step": None,
    }
    assert AutomationTask.from_row(running_row).can_be_claimed is False
    assert AutomationTask.from_row({**running_row, "status": "completed"}).is_active is False


def test_zone_lease_can_be_claimed_only_by_owner_or_after_expiry() -> None:
    now = datetime.now(timezone.utc)
    lease = ZoneLease(
        zone_id=21,
        owner="worker-a",
        leased_until=now + timedelta(seconds=30),
        updated_at=now,
    )

    assert lease.can_be_claimed_by(owner="worker-a", now=now) is True
    assert lease.can_be_claimed_by(owner="worker-b", now=now) is False
    assert lease.can_be_claimed_by(owner="worker-b", now=now + timedelta(seconds=31)) is True


def test_zone_workflow_normalizes_row_payload_and_phase() -> None:
    now = datetime.now(timezone.utc)
    workflow = ZoneWorkflow.from_row(
        {
            "zone_id": 7,
            "workflow_phase": "TANK_RECIRC",
            "version": 3,
            "scheduler_task_id": "task-7",
            "started_at": now - timedelta(minutes=5),
            "updated_at": now,
            "payload": {"ae3_cycle_start_stage": "prepare_recirculation_check"},
        }
    )

    assert workflow.zone_id == 7
    assert workflow.workflow_phase == "tank_recirc"
    assert workflow.version == 3
    assert workflow.scheduler_task_id == "task-7"
    assert workflow.payload["ae3_cycle_start_stage"] == "prepare_recirculation_check"
    assert workflow.is_idle is False
