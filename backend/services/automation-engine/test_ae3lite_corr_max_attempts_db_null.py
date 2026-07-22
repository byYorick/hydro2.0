"""Domain 0-axis max_attempts must persist as NULL (DB CHECK >= 1 OR NULL)."""

from __future__ import annotations

from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.infrastructure.repositories.automation_task_repository import (
    CORRECTION_OPTIONAL_FIELDS,
    PgAutomationTaskRepository,
)


def test_db_axis_max_attempts_maps_zero_to_null() -> None:
    assert PgAutomationTaskRepository._db_axis_max_attempts(0) is None
    assert PgAutomationTaskRepository._db_axis_max_attempts(-1) is None
    assert PgAutomationTaskRepository._db_axis_max_attempts(None) is None
    assert PgAutomationTaskRepository._db_axis_max_attempts(1) == 1
    assert PgAutomationTaskRepository._db_axis_max_attempts(6) == 6


def test_correction_values_nulls_disabled_axes() -> None:
    repo = PgAutomationTaskRepository()
    corr = CorrectionState.build_default(
        corr_step="corr_check",
        max_attempts=6,
        ec_max_attempts=0,  # irrigation pH-only
        ph_max_attempts=6,
        activated_here=False,
        stabilization_sec=20,
        return_stage_success="irrigation_check",
        return_stage_fail="irrigation_check",
    )
    values = repo._correction_values(corr)
    # trailing limit_policy_logged bool
    assert values[-1] is False
    payload = dict(zip(CORRECTION_OPTIONAL_FIELDS, values[:-1], strict=True))
    assert payload["ec_max_attempts"] is None
    assert payload["ph_max_attempts"] == 6

    fill = CorrectionState.build_default(
        corr_step="corr_check",
        max_attempts=6,
        ec_max_attempts=6,
        ph_max_attempts=0,  # fill Ca-only
        activated_here=True,
        stabilization_sec=20,
        return_stage_success="solution_fill_check",
        return_stage_fail="solution_fill_check",
    )
    fill_payload = dict(zip(CORRECTION_OPTIONAL_FIELDS, repo._correction_values(fill)[:-1], strict=True))
    assert fill_payload["ec_max_attempts"] == 6
    assert fill_payload["ph_max_attempts"] is None
