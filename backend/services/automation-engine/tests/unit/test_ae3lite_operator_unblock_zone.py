from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from ae3lite.application.use_cases.operator_unblock_zone import OperatorUnblockZoneUseCase
from ae3lite.domain.errors import ErrorCodes

NOW = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


class _WorkflowRepo:
    def __init__(self, workflow: object | None) -> None:
        self.workflow = workflow
        self.upserts: list[dict[str, object]] = []

    async def get(self, *, zone_id: int):
        return self.workflow

    async def upsert_phase(self, *, zone_id, workflow_phase, payload, scheduler_task_id, now):
        self.upserts.append(
            {
                "zone_id": zone_id,
                "workflow_phase": workflow_phase,
                "payload": dict(payload),
                "scheduler_task_id": scheduler_task_id,
                "now": now,
            }
        )
        return SimpleNamespace(workflow_phase=workflow_phase)


class _TaskRepo:
    def __init__(self, active: object | None) -> None:
        self._active = active
        self.fail_calls: list[dict[str, object]] = []

    async def get_active_for_zone(self, *, zone_id: int):
        return self._active

    async def fail_for_recovery(self, *, task_id, error_code, error_message, now):
        self.fail_calls.append(
            {"task_id": task_id, "error_code": error_code, "error_message": error_message, "now": now}
        )
        return self._active


async def test_operator_unblock_idle_zone_resets_workflow(monkeypatch) -> None:
    monkeypatch.setattr(
        "ae3lite.application.use_cases.operator_unblock_zone.create_zone_event",
        AsyncMock(return_value=None),
    )
    workflow = SimpleNamespace(workflow_phase="tank_recirc", payload={"ae3_cycle_start_stage": "prepare_recirculation_check"}, scheduler_task_id=None)
    wf_repo = _WorkflowRepo(workflow)
    result = await OperatorUnblockZoneUseCase(
        task_repository=_TaskRepo(None),
        workflow_repository=wf_repo,
        fetch_fn=AsyncMock(return_value=[]),
    ).run(zone_id=9, now=NOW, reason="stuck recirc", user_id=3)

    assert result["workflow_phase"] == "idle"
    assert result["failed_task_id"] is None
    assert wf_repo.upserts[0]["workflow_phase"] == "idle"
    assert wf_repo.upserts[0]["payload"]["ae3_cycle_start_stage"] == "startup"


async def test_operator_unblock_fails_active_task_after_fail_safe(monkeypatch) -> None:
    published: list[object] = []

    async def run_publish_only_batch(*, task, commands, now):
        published.append(task.id)
        return {"success": True}

    monkeypatch.setattr(
        "ae3lite.application.use_cases.operator_unblock_zone.create_zone_event",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.load_irrig_fail_safe_actuators",
        AsyncMock(
            return_value=(
                {"node_uid": "irrig-1", "node_type": "irrig", "channel": "pump_main"},
            )
        ),
    )

    active = SimpleNamespace(
        id=77,
        zone_id=9,
        topology="two_tank",
        claimed_by="ae3-worker",
        intent_id=15,
        current_stage="irrigation_check",
    )
    task_repo = _TaskRepo(active)
    lease = SimpleNamespace(release_if_owner_or_expired=AsyncMock(return_value=True))
    intents = SimpleNamespace(mark_terminal=AsyncMock(return_value=None))
    pid = SimpleNamespace(reset_no_effect_counts=AsyncMock(return_value=None))
    wf_repo = _WorkflowRepo(SimpleNamespace(workflow_phase="irrigating", payload={}, scheduler_task_id=None))

    result = await OperatorUnblockZoneUseCase(
        task_repository=task_repo,
        workflow_repository=wf_repo,
        lease_repository=lease,
        zone_intent_repository=intents,
        command_gateway=SimpleNamespace(run_publish_only_batch=run_publish_only_batch),
        pid_state_repository=pid,
        fetch_fn=AsyncMock(return_value=[{"id": 15}, {"id": 22}]),
    ).run(zone_id=9, now=NOW, reason="hung irrig")

    assert result["failed_task_id"] == 77
    assert published == [77]
    assert task_repo.fail_calls[0]["error_code"] == ErrorCodes.OPERATOR_UNBLOCKED
    lease.release_if_owner_or_expired.assert_awaited()
    assert intents.mark_terminal.await_count == 2
    pid.reset_no_effect_counts.assert_awaited()
