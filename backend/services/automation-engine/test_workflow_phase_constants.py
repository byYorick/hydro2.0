"""Tests for consistency between workflow phase constant sets."""

from __future__ import annotations

from executor.workflow_phase_policy import (
    WORKFLOW_PHASE_VALUES as POLICY_PHASE_VALUES,
    WORKFLOW_PHASE_BY_DIAGNOSTICS_WORKFLOW,
    WORKFLOW_PHASE_BLOCKING_FAILURE_REASONS,
    WORKFLOW_PHASE_ACTIVE_MODES,
    WORKFLOW_PHASE_IRRIGATING_MODES,
    WORKFLOW_PHASE_READY_MODES,
)
from services.zone_automation_constants import (
    WORKFLOW_PHASE_VALUES,
    WORKFLOW_CORRECTION_OPEN_PHASES,
    WORKFLOW_EC_COMPONENTS_BY_PHASE,
    WORKFLOW_SENSOR_MODE_EXTERNAL_PHASES,
)
from infrastructure.workflow_state_store import WORKFLOW_PHASE_VALUES as STORE_PHASE_VALUES


def test_ec_components_phases_subset_of_correction_open():
    """All phases in WORKFLOW_EC_COMPONENTS_BY_PHASE must be in WORKFLOW_CORRECTION_OPEN_PHASES."""
    for phase in WORKFLOW_EC_COMPONENTS_BY_PHASE:
        assert phase in WORKFLOW_CORRECTION_OPEN_PHASES, (
            f"Phase '{phase}' is in WORKFLOW_EC_COMPONENTS_BY_PHASE "
            f"but not in WORKFLOW_CORRECTION_OPEN_PHASES"
        )


def test_correction_open_phases_subset_of_phase_values():
    """WORKFLOW_CORRECTION_OPEN_PHASES must be a subset of WORKFLOW_PHASE_VALUES."""
    for phase in WORKFLOW_CORRECTION_OPEN_PHASES:
        assert phase in WORKFLOW_PHASE_VALUES, (
            f"Phase '{phase}' is in WORKFLOW_CORRECTION_OPEN_PHASES "
            f"but not in WORKFLOW_PHASE_VALUES"
        )


def test_sensor_mode_external_phases_subset_of_phase_values():
    """WORKFLOW_SENSOR_MODE_EXTERNAL_PHASES must be a subset of WORKFLOW_PHASE_VALUES."""
    for phase in WORKFLOW_SENSOR_MODE_EXTERNAL_PHASES:
        assert phase in WORKFLOW_PHASE_VALUES, (
            f"Phase '{phase}' is in WORKFLOW_SENSOR_MODE_EXTERNAL_PHASES "
            f"but not in WORKFLOW_PHASE_VALUES"
        )


def test_phase_policy_values_consistent_with_constants():
    """WORKFLOW_PHASE_VALUES in policy, constants, and store must be identical."""
    assert POLICY_PHASE_VALUES == WORKFLOW_PHASE_VALUES, (
        f"WORKFLOW_PHASE_VALUES mismatch between policy and constants: "
        f"policy={POLICY_PHASE_VALUES - WORKFLOW_PHASE_VALUES}, "
        f"constants={WORKFLOW_PHASE_VALUES - POLICY_PHASE_VALUES}"
    )
    assert STORE_PHASE_VALUES == WORKFLOW_PHASE_VALUES, (
        f"WORKFLOW_PHASE_VALUES mismatch between store and constants: "
        f"store={STORE_PHASE_VALUES - WORKFLOW_PHASE_VALUES}, "
        f"constants={WORKFLOW_PHASE_VALUES - STORE_PHASE_VALUES}"
    )


def test_diagnostics_workflow_phase_values_in_phase_values():
    """All phases in WORKFLOW_PHASE_BY_DIAGNOSTICS_WORKFLOW must be in WORKFLOW_PHASE_VALUES."""
    for workflow, phase in WORKFLOW_PHASE_BY_DIAGNOSTICS_WORKFLOW.items():
        assert phase in WORKFLOW_PHASE_VALUES, (
            f"Workflow '{workflow}' maps to phase '{phase}' "
            f"which is not in WORKFLOW_PHASE_VALUES"
        )


def test_active_modes_phase_values_in_phase_values():
    """All phases in WORKFLOW_PHASE_ACTIVE_MODES must be in WORKFLOW_PHASE_VALUES."""
    for mode, phase in WORKFLOW_PHASE_ACTIVE_MODES.items():
        assert phase in WORKFLOW_PHASE_VALUES, (
            f"Mode '{mode}' maps to phase '{phase}' "
            f"which is not in WORKFLOW_PHASE_VALUES"
        )


def test_blocking_failure_reasons_non_empty():
    """WORKFLOW_PHASE_BLOCKING_FAILURE_REASONS must be a non-empty set of strings."""
    assert isinstance(WORKFLOW_PHASE_BLOCKING_FAILURE_REASONS, (set, frozenset))
    assert len(WORKFLOW_PHASE_BLOCKING_FAILURE_REASONS) > 0
    for reason in WORKFLOW_PHASE_BLOCKING_FAILURE_REASONS:
        assert isinstance(reason, str) and reason, f"Reason must be a non-empty string, got {reason!r}"
