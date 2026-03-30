from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ae3lite.application.handlers.decision_gate import DecisionGateHandler
from ae3lite.application.handlers.irrigation_check import IrrigationCheckHandler
from ae3lite.infrastructure.repositories import PgAutomationTaskRepository
from common.db import execute, fetch
from test_ae3lite_create_task_from_intent_integration import _cleanup, _insert_zone


class _DecisionControllerStub:
    async def evaluate(self, **_kwargs):
        return SimpleNamespace(
            outcome="degraded_run",
            reason_code="smart_soil_telemetry_missing_or_stale",
            degraded=True,
        )


class _RuntimeMonitorStub:
    def __init__(self, *, level_triggered: bool) -> None:
        self._level_triggered = level_triggered

    async def read_level_switch(self, **_kwargs):
        return {
            "has_level": True,
            "is_stale": False,
            "is_triggered": self._level_triggered,
        }


class _CommandGatewayStub:
    async def run_batch(self, **_kwargs):
        return {"success": True, "command_statuses": []}


async def _create_claimed_irrigation_task(
    *,
    prefix: str,
    current_stage: str,
    now: datetime,
) -> tuple[int, PgAutomationTaskRepository]:
    task_repository = PgAutomationTaskRepository()
    zone_id = await _insert_zone(prefix)
    created_task = await task_repository.create_pending(
        zone_id=zone_id,
        idempotency_key=f"{prefix}-idem",
        task_type="irrigation_start",
        topology="two_tank",
        current_stage=current_stage,
        workflow_phase="ready",
        intent_source="zone_ui",
        intent_trigger="irrigation",
        intent_id=501,
        intent_meta={"intent_type": "irrigation"},
        scheduled_for=now,
        due_at=now,
        now=now,
        irrigation_mode="normal",
        irrigation_requested_duration_sec=180,
    )
    assert created_task is not None

    await execute(
        """
        UPDATE ae_tasks
        SET status = 'claimed',
            claimed_by = 'worker-irrigation',
            claimed_at = $2,
            updated_at = $2
        WHERE id = $1
        """,
        int(created_task.id),
        now,
    )

    return zone_id, task_repository


@pytest.mark.asyncio
async def test_decision_gate_persists_irrigation_decision_columns() -> None:
    prefix = f"ae3-irrigation-decision-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        zone_id, task_repository = await _create_claimed_irrigation_task(
            prefix=prefix,
            current_stage="decision_gate",
            now=now,
        )
        task = await task_repository.get_active_for_zone(zone_id=zone_id)
        assert task is not None

        handler = DecisionGateHandler(
            runtime_monitor=_RuntimeMonitorStub(level_triggered=False),
            command_gateway=_CommandGatewayStub(),
            task_repository=task_repository,
            decision_controller=_DecisionControllerStub(),
        )

        outcome = await handler.run(
            task=task,
            plan=SimpleNamespace(runtime={"irrigation_decision": {"strategy": "smart_soil_v1"}}),
            stage_def=SimpleNamespace(),
            now=now,
        )

        assert outcome.kind == "transition"
        assert outcome.next_stage == "irrigation_start"

        rows = await fetch(
            """
            SELECT
                irrigation_decision_strategy,
                irrigation_decision_outcome,
                irrigation_decision_reason_code,
                irrigation_decision_degraded
            FROM ae_tasks
            WHERE id = $1
            """,
            int(task.id),
        )

        assert len(rows) == 1
        row = rows[0]
        assert row["irrigation_decision_strategy"] == "smart_soil_v1"
        assert row["irrigation_decision_outcome"] == "degraded_run"
        assert row["irrigation_decision_reason_code"] == "smart_soil_telemetry_missing_or_stale"
        assert row["irrigation_decision_degraded"] is True
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_irrigation_check_persists_replay_count_when_solution_min_is_triggered() -> None:
    prefix = f"ae3-irrigation-replay-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        zone_id, task_repository = await _create_claimed_irrigation_task(
            prefix=prefix,
            current_stage="irrigation_check",
            now=now,
        )
        task = await task_repository.get_active_for_zone(zone_id=zone_id)
        assert task is not None

        handler = IrrigationCheckHandler(
            runtime_monitor=_RuntimeMonitorStub(level_triggered=True),
            command_gateway=_CommandGatewayStub(),
            task_repository=task_repository,
        )

        outcome = await handler.run(
            task=task,
            plan=SimpleNamespace(
                runtime={
                    "irrigation_safety": {"stop_on_solution_min": True},
                    "irrigation_recovery": {"max_setup_replays": 1},
                    "solution_min_sensor_labels": ["level_solution_min"],
                    "level_switch_on_threshold": 0.5,
                    "telemetry_max_age_sec": 60,
                },
                named_plans={},
            ),
            stage_def=SimpleNamespace(),
            now=now,
        )

        assert outcome.kind == "transition"
        assert outcome.next_stage == "irrigation_stop_to_setup"

        rows = await fetch(
            """
            SELECT irrigation_replay_count
            FROM ae_tasks
            WHERE id = $1
            """,
            int(task.id),
        )

        assert len(rows) == 1
        assert int(rows[0]["irrigation_replay_count"] or 0) == 1
    finally:
        await _cleanup(prefix)
