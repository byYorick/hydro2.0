"""Unit-тесты для CorrectionTransitionPolicy (extracted from CorrectionHandler, B1).

Pure decision policy — no I/O, no mocks, no handler. Every test is a single
call returning either a StageOutcome or None. Handler end-to-end tests remain
the regression net for the orchestration path; this file locks the pure
transition table in place so it can't silently drift.
"""

from __future__ import annotations

import pytest

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.services.correction_transition_policy import (
    CorrectionTransitionPolicy,
)


def _corr(
    *,
    corr_step: str = "corr_check",
    activated_here: bool = True,
    return_stage_success: str = "parent_success",
    return_stage_fail: str = "parent_fail",
) -> CorrectionState:
    return CorrectionState(
        corr_step=corr_step,
        attempt=0,
        max_attempts=3,
        ec_attempt=0,
        ec_max_attempts=3,
        ph_attempt=0,
        ph_max_attempts=3,
        activated_here=activated_here,
        stabilization_sec=30,
        return_stage_success=return_stage_success,
        return_stage_fail=return_stage_fail,
        outcome_success=None,
        needs_ec=False,
        ec_node_uid=None,
        ec_channel=None,
        ec_duration_ms=None,
        needs_ph_up=False,
        needs_ph_down=False,
        ph_node_uid=None,
        ph_channel=None,
        ph_duration_ms=None,
        wait_until=None,
    )


@pytest.fixture
def policy() -> CorrectionTransitionPolicy:
    return CorrectionTransitionPolicy()


# ── transition_to_deactivate_or_return ──────────────────────────────


def test_deactivate_or_return_enters_deactivate_when_activated_here(
    policy: CorrectionTransitionPolicy,
) -> None:
    outcome = policy.transition_to_deactivate_or_return(
        corr=_corr(activated_here=True), success=True,
    )
    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None
    assert outcome.correction.corr_step == "corr_deactivate"
    assert outcome.correction.outcome_success is True


def test_deactivate_or_return_exits_directly_when_sensors_not_owned(
    policy: CorrectionTransitionPolicy,
) -> None:
    outcome = policy.transition_to_deactivate_or_return(
        corr=_corr(activated_here=False), success=False,
    )
    assert outcome.kind == "exit_correction"
    assert outcome.next_stage == "parent_fail"
    assert outcome.correction is not None
    assert outcome.correction.outcome_success is False


def test_deactivate_or_return_picks_success_stage_when_successful(
    policy: CorrectionTransitionPolicy,
) -> None:
    outcome = policy.transition_to_deactivate_or_return(
        corr=_corr(activated_here=False), success=True,
    )
    assert outcome.next_stage == "parent_success"


# ── decide_exhausted_transition ─────────────────────────────────────


def test_exhausted_irrigation_check_re_enters_same_stage(
    policy: CorrectionTransitionPolicy,
) -> None:
    outcome = policy.decide_exhausted_transition(
        current_stage="irrigation_check",
        stage_retry_count=2,
        level_poll_interval_sec=10,
    )
    assert isinstance(outcome, StageOutcome)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "irrigation_check"
    assert outcome.stage_retry_count == 3
    assert outcome.due_delay_sec == 10


def test_exhausted_prepare_recirc_goes_to_window_exhausted(
    policy: CorrectionTransitionPolicy,
) -> None:
    outcome = policy.decide_exhausted_transition(
        current_stage="prepare_recirculation_check",
        stage_retry_count=0,
        level_poll_interval_sec=10,
    )
    assert outcome.next_stage == "prepare_recirculation_window_exhausted"
    assert outcome.stage_retry_count == 1


def test_exhausted_solution_fill_check_reenters_same_stage(
    policy: CorrectionTransitionPolicy,
) -> None:
    outcome = policy.decide_exhausted_transition(
        current_stage="solution_fill_check",
        stage_retry_count=5,
        level_poll_interval_sec=15,
    )
    assert outcome.next_stage == "solution_fill_check"
    assert outcome.stage_retry_count == 6
    assert outcome.due_delay_sec == 15


def test_exhausted_unknown_stage_returns_none(
    policy: CorrectionTransitionPolicy,
) -> None:
    assert policy.decide_exhausted_transition(
        current_stage="diagnostics_tick",
        stage_retry_count=0,
        level_poll_interval_sec=10,
    ) is None


# ── decide_no_effect_transition ─────────────────────────────────────


def test_no_effect_prepare_recirc_goes_to_window_exhausted(
    policy: CorrectionTransitionPolicy,
) -> None:
    outcome = policy.decide_no_effect_transition(
        current_stage="prepare_recirculation_check",
        stage_retry_count=3,
    )
    assert outcome is not None
    assert outcome.next_stage == "prepare_recirculation_window_exhausted"
    assert outcome.stage_retry_count == 4


def test_no_effect_solution_fill_goes_to_timeout_stop(
    policy: CorrectionTransitionPolicy,
) -> None:
    outcome = policy.decide_no_effect_transition(
        current_stage="solution_fill_check",
        stage_retry_count=0,
    )
    assert outcome is not None
    assert outcome.next_stage == "solution_fill_timeout_stop"


def test_no_effect_unknown_stage_returns_none(
    policy: CorrectionTransitionPolicy,
) -> None:
    assert policy.decide_no_effect_transition(
        current_stage="irrigation_check",
        stage_retry_count=0,
    ) is None


# ── decide_stage_deadline_transition ────────────────────────────────


def test_stage_deadline_declines_when_deadline_not_reached(
    policy: CorrectionTransitionPolicy,
) -> None:
    assert policy.decide_stage_deadline_transition(
        corr=_corr(),
        current_stage="solution_fill_check",
        stage_retry_count=0,
        deadline_reached=False,
        targets_reached=None,
    ) is None


def test_stage_deadline_declines_on_terminal_correction_steps(
    policy: CorrectionTransitionPolicy,
) -> None:
    for step in ("corr_deactivate", "corr_done"):
        assert policy.decide_stage_deadline_transition(
            corr=_corr(corr_step=step),
            current_stage="solution_fill_check",
            stage_retry_count=0,
            deadline_reached=True,
            targets_reached=None,
        ) is None


def test_stage_deadline_irrigation_targets_reached_goes_to_ready(
    policy: CorrectionTransitionPolicy,
) -> None:
    outcome = policy.decide_stage_deadline_transition(
        corr=_corr(),
        current_stage="irrigation_check",
        stage_retry_count=0,
        deadline_reached=True,
        targets_reached=True,
    )
    assert outcome is not None
    assert outcome.next_stage == "irrigation_stop_to_ready"


def test_stage_deadline_irrigation_targets_not_reached_goes_to_recovery(
    policy: CorrectionTransitionPolicy,
) -> None:
    outcome = policy.decide_stage_deadline_transition(
        corr=_corr(),
        current_stage="irrigation_check",
        stage_retry_count=0,
        deadline_reached=True,
        targets_reached=False,
    )
    assert outcome is not None
    assert outcome.next_stage == "irrigation_stop_to_recovery"


def test_stage_deadline_solution_fill_goes_to_timeout_stop(
    policy: CorrectionTransitionPolicy,
) -> None:
    outcome = policy.decide_stage_deadline_transition(
        corr=_corr(),
        current_stage="solution_fill_check",
        stage_retry_count=0,
        deadline_reached=True,
        targets_reached=None,
    )
    assert outcome.next_stage == "solution_fill_timeout_stop"


def test_stage_deadline_prepare_recirc_increments_retry(
    policy: CorrectionTransitionPolicy,
) -> None:
    outcome = policy.decide_stage_deadline_transition(
        corr=_corr(),
        current_stage="prepare_recirculation_check",
        stage_retry_count=4,
        deadline_reached=True,
        targets_reached=None,
    )
    assert outcome.next_stage == "prepare_recirculation_window_exhausted"
    assert outcome.stage_retry_count == 5


# ── decide_imminent_flow_probe_transition ───────────────────────────


def test_imminent_probe_declines_when_no_flow_path(
    policy: CorrectionTransitionPolicy,
) -> None:
    assert policy.decide_imminent_flow_probe_transition(
        current_stage="solution_fill_check",
        stage_retry_count=0,
        expects_flow_path=False,
        deadline_too_close=True,
    ) is None


def test_imminent_probe_declines_when_deadline_not_close(
    policy: CorrectionTransitionPolicy,
) -> None:
    assert policy.decide_imminent_flow_probe_transition(
        current_stage="solution_fill_check",
        stage_retry_count=0,
        expects_flow_path=True,
        deadline_too_close=False,
    ) is None


def test_imminent_probe_prepare_recirc_increments_retry(
    policy: CorrectionTransitionPolicy,
) -> None:
    outcome = policy.decide_imminent_flow_probe_transition(
        current_stage="prepare_recirculation_check",
        stage_retry_count=1,
        expects_flow_path=True,
        deadline_too_close=True,
    )
    assert outcome is not None
    assert outcome.next_stage == "prepare_recirculation_window_exhausted"
    assert outcome.stage_retry_count == 2


def test_imminent_probe_solution_fill_does_not_increment_retry(
    policy: CorrectionTransitionPolicy,
) -> None:
    outcome = policy.decide_imminent_flow_probe_transition(
        current_stage="solution_fill_check",
        stage_retry_count=3,
        expects_flow_path=True,
        deadline_too_close=True,
    )
    assert outcome is not None
    assert outcome.next_stage == "solution_fill_timeout_stop"
    # Solution fill timeout does not burn a retry — matches legacy behavior.
    assert outcome.stage_retry_count is None


# ── decide_imminent_retry_then_probe_transition ─────────────────────


def test_imminent_retry_declines_when_no_flow_path(
    policy: CorrectionTransitionPolicy,
) -> None:
    assert policy.decide_imminent_retry_then_probe_transition(
        current_stage="irrigation_check",
        stage_retry_count=0,
        expects_flow_path=False,
        remaining_sec=1.0,
        required_budget_sec=5.0,
    ) is None


def test_imminent_retry_declines_when_remaining_unknown(
    policy: CorrectionTransitionPolicy,
) -> None:
    assert policy.decide_imminent_retry_then_probe_transition(
        current_stage="prepare_recirculation_check",
        stage_retry_count=0,
        expects_flow_path=True,
        remaining_sec=None,
        required_budget_sec=5.0,
    ) is None


def test_imminent_retry_declines_when_remaining_exceeds_budget(
    policy: CorrectionTransitionPolicy,
) -> None:
    assert policy.decide_imminent_retry_then_probe_transition(
        current_stage="prepare_recirculation_check",
        stage_retry_count=0,
        expects_flow_path=True,
        remaining_sec=60.0,
        required_budget_sec=30.0,
    ) is None


def test_imminent_retry_prepare_recirc_increments_retry(
    policy: CorrectionTransitionPolicy,
) -> None:
    outcome = policy.decide_imminent_retry_then_probe_transition(
        current_stage="prepare_recirculation_check",
        stage_retry_count=2,
        expects_flow_path=True,
        remaining_sec=5.0,
        required_budget_sec=30.0,
    )
    assert outcome is not None
    assert outcome.next_stage == "prepare_recirculation_window_exhausted"
    assert outcome.stage_retry_count == 3


def test_imminent_retry_solution_fill_does_not_increment_retry(
    policy: CorrectionTransitionPolicy,
) -> None:
    outcome = policy.decide_imminent_retry_then_probe_transition(
        current_stage="solution_fill_check",
        stage_retry_count=9,
        expects_flow_path=True,
        remaining_sec=5.0,
        required_budget_sec=30.0,
    )
    assert outcome is not None
    assert outcome.next_stage == "solution_fill_timeout_stop"
    assert outcome.stage_retry_count is None


def test_imminent_retry_propagates_task_override(
    policy: CorrectionTransitionPolicy,
) -> None:
    """task_override must thread through the outcome unchanged."""
    fake_task = object()
    outcome = policy.decide_imminent_retry_then_probe_transition(
        current_stage="solution_fill_check",
        stage_retry_count=0,
        expects_flow_path=True,
        remaining_sec=1.0,
        required_budget_sec=30.0,
        task_override=fake_task,
    )
    assert outcome is not None
    assert outcome.task_override is fake_task
