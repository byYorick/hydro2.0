"""Исполнитель не пускает чужой handler на стадию системы."""

import pytest

from ae3lite.application.services.workflow_topology import StageDef
from ae3lite.domain.errors import ErrorCodes, TaskExecutionError
from ae3lite.hydraulics.dispatch import assert_stage_dispatch


def test_solution_stage_accepts_its_handler() -> None:
    stage = StageDef("solution_fill_check", "solution_fill", system="solution")
    assert_stage_dispatch(stage, correction_active=False)


def test_shared_command_handler_is_allowed_on_solution_stage() -> None:
    stage = StageDef("clean_fill_start", "command", system="solution")
    assert_stage_dispatch(stage, correction_active=False)


def test_irrigation_handler_on_solution_stage_is_rejected() -> None:
    stage = StageDef("solution_fill_check", "irrigation_check", system="solution")
    with pytest.raises(TaskExecutionError) as caught:
        assert_stage_dispatch(stage, correction_active=False)
    assert caught.value.code == ErrorCodes.AE3_STAGE_SYSTEM_MISMATCH


def test_correction_only_on_host_stage() -> None:
    host = StageDef("irrigation_check", "irrigation_check", system="irrigation")
    assert_stage_dispatch(host, correction_active=True)
    other = StageDef("clean_fill_check", "clean_fill", system="solution")
    with pytest.raises(TaskExecutionError) as caught:
        assert_stage_dispatch(other, correction_active=True)
    assert caught.value.code == ErrorCodes.AE3_STAGE_SYSTEM_MISMATCH
