"""Tests for control_mode_snapshot None-check in AutomationTask.from_row.

The fix ensures that an explicit ``None`` value for ``control_mode_snapshot``
correctly falls back to ``control_mode``, while a non-None snapshot (even if
falsy like empty string) is used as-is before the final ``or "auto"`` fallback.

Key line in automation_task.py::

    raw_control_mode = (
        row.get("control_mode_snapshot")
        if row.get("control_mode_snapshot") is not None
        else row.get("control_mode") or "auto"
    )

Then WorkflowState stores: ``control_mode=str(raw_control_mode).strip() or "auto"``
"""

from __future__ import annotations

from datetime import datetime, timezone

from ae3lite.domain.entities.automation_task import AutomationTask


NOW = datetime(2026, 3, 11, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _base_row(**overrides: object) -> dict:
    """Minimal valid row for AutomationTask.from_row, with optional overrides."""
    row: dict = {
        "id": 1,
        "zone_id": 10,
        "task_type": "cycle_start",
        "status": "running",
        "idempotency_key": "k1-valid-key",
        "scheduled_for": NOW,
        "due_at": NOW,
        "claimed_by": None,
        "claimed_at": None,
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
        "current_stage": "startup",
        "workflow_phase": "idle",
        "stage_deadline_at": None,
        "stage_retry_count": 0,
        "stage_entered_at": None,
        "clean_fill_cycle": 0,
        "corr_step": None,
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# control_mode_snapshot priority logic
# ---------------------------------------------------------------------------

class TestControlModeSnapshot:
    def test_snapshot_takes_priority_over_control_mode(self) -> None:
        """A non-None snapshot wins over the control_mode field."""
        task = AutomationTask.from_row(_base_row(
            control_mode_snapshot="manual",
            control_mode="auto",
        ))
        assert task.workflow.control_mode == "manual"

    def test_control_mode_used_when_snapshot_absent_from_row(self) -> None:
        """When control_mode_snapshot key is not in row, control_mode is used."""
        task = AutomationTask.from_row(_base_row(control_mode="manual"))
        assert task.workflow.control_mode == "manual"

    def test_defaults_to_auto_when_both_absent(self) -> None:
        """When neither snapshot nor control_mode present, result is 'auto'."""
        task = AutomationTask.from_row(_base_row())
        assert task.workflow.control_mode == "auto"

    def test_snapshot_none_falls_back_to_control_mode(self) -> None:
        """An explicit None snapshot must NOT be used; control_mode applies instead.

        This was the bug: without the ``is not None`` guard, ``row.get(key)``
        returning None would still enter the snapshot branch and set
        raw_control_mode=None, causing a downstream crash or wrong mode.
        """
        task = AutomationTask.from_row(_base_row(
            control_mode_snapshot=None,
            control_mode="manual",
        ))
        assert task.workflow.control_mode == "manual"

    def test_snapshot_none_no_control_mode_defaults_to_auto(self) -> None:
        """Explicit None snapshot + no control_mode → default 'auto'."""
        task = AutomationTask.from_row(_base_row(control_mode_snapshot=None))
        assert task.workflow.control_mode == "auto"

    def test_snapshot_empty_string_is_not_none_so_snapshot_path_used(self) -> None:
        """An empty string snapshot is not None, so the snapshot branch is taken.

        The snapshot value "" → str("").strip() → "" → falsy → WorkflowState
        applies the final ``or "auto"`` fallback → result is "auto".
        This documents the precise behavior of the is-not-None guard.
        """
        task = AutomationTask.from_row(_base_row(
            control_mode_snapshot="",
            control_mode="manual",
        ))
        # "" is not None → snapshot branch → raw = "" → strip() → "" → or "auto"
        assert task.workflow.control_mode == "auto"

    def test_snapshot_whitespace_normalised_to_auto(self) -> None:
        """A whitespace-only snapshot is not None, but strips to '' → 'auto'."""
        task = AutomationTask.from_row(_base_row(
            control_mode_snapshot="   ",
            control_mode="manual",
        ))
        assert task.workflow.control_mode == "auto"

    def test_snapshot_auto_value_preserved(self) -> None:
        task = AutomationTask.from_row(_base_row(
            control_mode_snapshot="auto",
            control_mode="manual",
        ))
        assert task.workflow.control_mode == "auto"

    def test_snapshot_with_surrounding_whitespace_stripped(self) -> None:
        task = AutomationTask.from_row(_base_row(
            control_mode_snapshot="  manual  ",
            control_mode="auto",
        ))
        assert task.workflow.control_mode == "manual"


# ---------------------------------------------------------------------------
# Verify other WorkflowState fields are unaffected by control_mode changes
# ---------------------------------------------------------------------------

class TestControlModeDoesNotAffectOtherWorkflowFields:
    def test_current_stage_unaffected(self) -> None:
        task = AutomationTask.from_row(_base_row(
            control_mode_snapshot="manual",
            current_stage="clean_fill",
        ))
        assert task.workflow.current_stage == "clean_fill"

    def test_workflow_phase_unaffected(self) -> None:
        task = AutomationTask.from_row(_base_row(
            control_mode_snapshot="manual",
            workflow_phase="irrig_recirc",
        ))
        assert task.workflow.workflow_phase == "irrig_recirc"

    def test_clean_fill_cycle_unaffected(self) -> None:
        task = AutomationTask.from_row(_base_row(
            control_mode_snapshot="manual",
            clean_fill_cycle=3,
        ))
        assert task.workflow.clean_fill_cycle == 3

    def test_pending_manual_step_independent_of_control_mode(self) -> None:
        task = AutomationTask.from_row(_base_row(
            control_mode_snapshot=None,
            control_mode="manual",
            pending_manual_step="confirm_drain",
        ))
        assert task.workflow.control_mode == "manual"
        assert task.workflow.pending_manual_step == "confirm_drain"
