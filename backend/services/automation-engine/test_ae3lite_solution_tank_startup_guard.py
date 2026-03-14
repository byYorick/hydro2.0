from __future__ import annotations

from datetime import datetime, timezone

from ae3lite.application.use_cases.guard_solution_tank_startup_reset import GuardSolutionTankStartupResetUseCase
from ae3lite.domain.entities.zone_workflow import ZoneWorkflow


NOW = datetime(2026, 3, 14, 9, 0, 0, tzinfo=timezone.utc)


class _WorkflowRepo:
    def __init__(self, workflow: ZoneWorkflow | None):
        self.workflow = workflow
        self.upsert_calls: list[dict] = []

    async def get(self, *, zone_id: int):
        return self.workflow

    async def upsert_phase(self, *, zone_id, workflow_phase, payload, scheduler_task_id, now):
        self.upsert_calls.append({
            "zone_id": zone_id,
            "workflow_phase": workflow_phase,
            "payload": payload,
            "scheduler_task_id": scheduler_task_id,
            "now": now,
        })
        self.workflow = ZoneWorkflow(
            zone_id=zone_id,
            workflow_phase=workflow_phase,
            version=2,
            scheduler_task_id=scheduler_task_id,
            started_at=now,
            updated_at=now,
            payload=payload,
        )
        return self.workflow


class _RuntimeMonitor:
    def __init__(self, level: dict):
        self.level = level
        self.calls: list[dict] = []

    async def read_level_switch(self, *, zone_id, sensor_labels, threshold, telemetry_max_age_sec):
        self.calls.append({
            "zone_id": zone_id,
            "sensor_labels": tuple(sensor_labels),
            "threshold": threshold,
            "telemetry_max_age_sec": telemetry_max_age_sec,
        })
        return dict(self.level)


def _workflow(*, phase: str = "ready", stage: str = "complete_ready") -> ZoneWorkflow:
    now = NOW.replace(tzinfo=None)
    return ZoneWorkflow(
        zone_id=7,
        workflow_phase=phase,
        version=1,
        scheduler_task_id="42",
        started_at=now,
        updated_at=now,
        payload={"ae3_cycle_start_stage": stage},
    )


async def test_guard_resets_ready_zone_to_startup_when_solution_min_is_triggered():
    repo = _WorkflowRepo(_workflow())
    monitor = _RuntimeMonitor(
        {
            "has_level": True,
            "is_stale": False,
            "is_triggered": True,
            "sensor_label": "level_solution_min",
            "sample_ts": NOW,
        }
    )

    async def fetch_fn(_query, _zone_id):
        return []

    use_case = GuardSolutionTankStartupResetUseCase(
        runtime_monitor=monitor,
        workflow_repository=repo,
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=7, now=NOW.replace(tzinfo=None))

    assert result["reset"] is True
    assert repo.upsert_calls[0]["workflow_phase"] == "idle"
    assert repo.upsert_calls[0]["payload"]["ae3_cycle_start_stage"] == "startup"
    assert repo.upsert_calls[0]["payload"]["guard_reason"] == "solution_tank_depleted"


async def test_guard_ignores_non_ready_zone():
    repo = _WorkflowRepo(_workflow(phase="tank_filling", stage="solution_fill_check"))
    monitor = _RuntimeMonitor({"has_level": True, "is_stale": False, "is_triggered": True})

    async def fetch_fn(_query, _zone_id):
        return []

    use_case = GuardSolutionTankStartupResetUseCase(
        runtime_monitor=monitor,
        workflow_repository=repo,
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=7, now=NOW.replace(tzinfo=None))

    assert result["reset"] is False
    assert result["reason"] == "workflow_not_ready"
    assert repo.upsert_calls == []
    assert monitor.calls == []


async def test_guard_handles_non_mapping_payload_without_crashing():
    repo = _WorkflowRepo(_workflow())
    repo.workflow = type(
        "WorkflowStub",
        (),
        {
            "workflow_phase": "ready",
            "payload": None,
            "scheduler_task_id": "42",
        },
    )()
    monitor = _RuntimeMonitor({"has_level": True, "is_stale": False, "is_triggered": False})

    async def fetch_fn(_query, _zone_id):
        return []

    use_case = GuardSolutionTankStartupResetUseCase(
        runtime_monitor=monitor,
        workflow_repository=repo,
        fetch_fn=fetch_fn,
    )

    result = await use_case.run(zone_id=7, now=NOW.replace(tzinfo=None))

    assert result["reset"] is False
    assert result["reason"] == "solution_tank_has_solution"
    assert len(monitor.calls) == 1
