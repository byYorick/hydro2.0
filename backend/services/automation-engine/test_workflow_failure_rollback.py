"""Unit-тесты отката workflow после failure."""

from __future__ import annotations

from types import SimpleNamespace

from ae3lite.domain.services.workflow_failure_rollback import (
    resolve_workflow_phase_after_task_failure,
    resolve_workflow_rollback_phase_for_stale_state,
)


def test_irrigation_start_failure_rolls_back_to_ready() -> None:
    task = SimpleNamespace(
        task_type="irrigation_start",
        workflow_phase="irrigating",
        current_stage="irrigation_run",
    )
    assert resolve_workflow_phase_after_task_failure(task) == "ready"


def test_cycle_start_tank_failure_rolls_back_to_idle() -> None:
    task = SimpleNamespace(
        task_type="cycle_start",
        workflow_phase="tank_filling",
        current_stage="solution_fill_start",
    )
    assert resolve_workflow_phase_after_task_failure(task) == "idle"


def test_stale_irrigating_workflow_watchdog_rolls_back_to_ready() -> None:
    assert resolve_workflow_rollback_phase_for_stale_state(workflow_phase="irrigating") == "ready"


def test_stale_tank_filling_watchdog_rolls_back_to_idle() -> None:
    assert resolve_workflow_rollback_phase_for_stale_state(workflow_phase="tank_filling") == "idle"
