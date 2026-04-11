"""CorrectionTransitionPolicy — pure decisions about stage/FSM transitions.

Extracted from ``CorrectionHandler`` as part of the God-Object decomposition
(audit finding B1). This module contains **only decision logic** — it does
not log events, does not send bizalerts, does not call runtime_monitor, and
does not read the database. I/O orchestration stays in the handler.

The split follows the canonical "Policy" pattern: the handler feeds current
state (stage name, retry counts, remaining stage time) to the policy and
receives a ``StageOutcome | None`` back. ``None`` means "no transition — fall
through to the caller's default branch" (typically ``transition_to_deactivate_or_return``).

Why pure decisions, not an orchestrator:
  * log_correction_event/biz_alert are async I/O that depend on handler
    infra (zone_event repository, alert gateway). Passing them as callables
    into a policy class would yield a brittle "mini-handler", not an
    improvement.
  * Pure decisions are trivially unit-testable — feed a stage name and
    counter state, assert the outcome shape.
  * Existing handler tests remain the end-to-end regression net.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.domain.entities.workflow_state import CorrectionState


# Stages the correction handler can interrupt and the stage they fall through
# to. Declared once so adding a new stage only needs one table update.
_IMMINENT_PROBE_TRANSITIONS: dict[str, str] = {
    "prepare_recirculation_check": "prepare_recirculation_window_exhausted",
    "solution_fill_check": "solution_fill_timeout_stop",
}


class CorrectionTransitionPolicy:
    """Pure decisions about correction-cycle transitions and interrupts."""

    # ── Deactivate / return ─────────────────────────────────────────

    @staticmethod
    def transition_to_deactivate_or_return(
        *, corr: CorrectionState, success: bool,
    ) -> StageOutcome:
        """Close the correction sub-FSM.

        If sensors were activated by the correction handler itself, go through
        ``corr_deactivate`` first; otherwise exit directly to the parent stage.
        """
        next_corr = replace(corr, outcome_success=success)
        if corr.activated_here:
            next_corr = replace(next_corr, corr_step="corr_deactivate")
            return StageOutcome(kind="enter_correction", correction=next_corr)
        next_stage = corr.return_stage_success if success else corr.return_stage_fail
        return StageOutcome(
            kind="exit_correction", next_stage=next_stage, correction=next_corr,
        )

    # ── "Exhausted attempts" stage transition ────────────────────────

    @staticmethod
    def decide_exhausted_transition(
        *,
        current_stage: str,
        stage_retry_count: int,
        level_poll_interval_sec: int,
    ) -> Optional[StageOutcome]:
        """Decide the stage transition when the attempt counter is burnt out.

        Returns ``None`` for stages that should fall back to
        ``transition_to_deactivate_or_return(success=False)``.
        """
        stage = (current_stage or "").strip().lower()
        if stage == "irrigation_check":
            return StageOutcome(
                kind="transition",
                next_stage="irrigation_check",
                stage_retry_count=stage_retry_count + 1,
                due_delay_sec=int(level_poll_interval_sec),
            )
        if stage == "prepare_recirculation_check":
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_window_exhausted",
                stage_retry_count=stage_retry_count + 1,
            )
        if stage == "solution_fill_check":
            return StageOutcome(
                kind="transition",
                next_stage="solution_fill_check",
                stage_retry_count=stage_retry_count + 1,
                due_delay_sec=int(level_poll_interval_sec),
            )
        return None

    # ── "No-effect limit reached" stage transition ───────────────────

    @staticmethod
    def decide_no_effect_transition(
        *,
        current_stage: str,
        stage_retry_count: int,
    ) -> Optional[StageOutcome]:
        """Decide the stage transition when N consecutive no-effect observations fire.

        Returns ``None`` for stages that should fall back to
        ``transition_to_deactivate_or_return(success=False)``.
        """
        stage = (current_stage or "").strip().lower()
        if stage == "prepare_recirculation_check":
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_window_exhausted",
                stage_retry_count=stage_retry_count + 1,
            )
        if stage == "solution_fill_check":
            return StageOutcome(
                kind="transition",
                next_stage="solution_fill_timeout_stop",
            )
        return None

    # ── Stage-deadline interrupt ─────────────────────────────────────

    @staticmethod
    def decide_stage_deadline_transition(
        *,
        corr: CorrectionState,
        current_stage: str,
        stage_retry_count: int,
        deadline_reached: bool,
        targets_reached: Optional[bool],
    ) -> Optional[StageOutcome]:
        """Decide what to do when the stage deadline fires inside correction.

        ``targets_reached`` is only consulted for irrigation_check; pass
        ``None`` when it's not applicable. For terminal correction steps we
        decline so the FSM can finish its own deactivation.
        """
        if corr.corr_step in {"corr_deactivate", "corr_done"}:
            return None
        if not deadline_reached:
            return None

        stage = (current_stage or "").strip().lower()
        if stage == "prepare_recirculation_check":
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_window_exhausted",
                stage_retry_count=stage_retry_count + 1,
            )
        if stage == "solution_fill_check":
            return StageOutcome(
                kind="transition",
                next_stage="solution_fill_timeout_stop",
            )
        if stage == "irrigation_check":
            if targets_reached:
                return StageOutcome(
                    kind="transition",
                    next_stage="irrigation_stop_to_ready",
                )
            return StageOutcome(
                kind="transition",
                next_stage="irrigation_stop_to_recovery",
            )
        return None

    # ── Imminent-probe-deadline interrupts (flow-path protection) ────

    @staticmethod
    def decide_imminent_flow_probe_transition(
        *,
        current_stage: str,
        stage_retry_count: int,
        expects_flow_path: bool,
        deadline_too_close: bool,
    ) -> Optional[StageOutcome]:
        """Decide whether to bail out of correction before the next flow-path probe.

        ``expects_flow_path`` matches the handler's ``_expected_flow_path_state``
        predicate; ``deadline_too_close`` matches ``_deadline_too_close_for_irr_probe``.
        The policy itself does not know about probe timing — that calculation
        stays in BaseStageHandler because it's shared across handlers.
        """
        if not expects_flow_path:
            return None
        if not deadline_too_close:
            return None

        stage = (current_stage or "").strip().lower()
        next_stage = _IMMINENT_PROBE_TRANSITIONS.get(stage)
        if next_stage is None:
            return None
        return StageOutcome(
            kind="transition",
            next_stage=next_stage,
            stage_retry_count=(
                stage_retry_count + 1
                if stage == "prepare_recirculation_check"
                else None
            ),
        )

    @staticmethod
    def decide_imminent_retry_then_probe_transition(
        *,
        current_stage: str,
        stage_retry_count: int,
        expects_flow_path: bool,
        remaining_sec: Optional[float],
        required_budget_sec: float,
        task_override: object | None = None,
    ) -> Optional[StageOutcome]:
        """Decide whether to bail when retry delay would overrun the probe budget.

        Returns ``None`` when there is still enough time for another retry
        before the next flow-path probe deadline.
        """
        if not expects_flow_path:
            return None
        if remaining_sec is None:
            return None
        if remaining_sec > required_budget_sec:
            return None

        stage = (current_stage or "").strip().lower()
        if stage == "prepare_recirculation_check":
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_window_exhausted",
                stage_retry_count=stage_retry_count + 1,
                task_override=task_override,
            )
        if stage == "solution_fill_check":
            return StageOutcome(
                kind="transition",
                next_stage="solution_fill_timeout_stop",
                task_override=task_override,
            )
        return None
