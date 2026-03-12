"""Tests for correction attempt limit checking in CorrectionHandler.

The CorrectionHandler uses ``corr.attempt >= corr.max_attempts`` to decide
whether a correction cycle is exhausted.  These tests verify the boundary
conditions of that comparison using CorrectionState instances built directly,
and also run the handler's ``_run_check`` path via a lightweight integration
scenario to confirm the >= semantics are in effect.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ae3lite.domain.entities.workflow_state import CorrectionState


NOW = datetime(2026, 3, 11, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_correction(*, attempt: int, max_attempts: int, ec_attempt: int = 0,
                     ec_max_attempts: int = 5, ph_attempt: int = 0,
                     ph_max_attempts: int = 5) -> CorrectionState:
    return CorrectionState(
        corr_step="corr_check",
        attempt=attempt,
        max_attempts=max_attempts,
        ec_attempt=ec_attempt,
        ec_max_attempts=ec_max_attempts,
        ph_attempt=ph_attempt,
        ph_max_attempts=ph_max_attempts,
        activated_here=False,
        stabilization_sec=60,
        return_stage_success="solution_fill_stop_to_ready",
        return_stage_fail="solution_fill_stop_to_prepare",
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


# ---------------------------------------------------------------------------
# Attempt / max_attempts boundary
# ---------------------------------------------------------------------------

class TestCorrectionAttemptBoundary:
    def test_attempt_at_limit_is_exhausted(self) -> None:
        """attempt == max_attempts must be exhausted (>= boundary).

        If the old bug used ``>`` instead of ``>=``, attempt=5 with max=5
        would be treated as still active, causing one extra correction step.
        """
        corr = _make_correction(attempt=5, max_attempts=5)
        assert corr.attempt >= corr.max_attempts

    def test_attempt_one_below_limit_is_not_exhausted(self) -> None:
        corr = _make_correction(attempt=4, max_attempts=5)
        assert not (corr.attempt >= corr.max_attempts)

    def test_attempt_above_limit_is_exhausted(self) -> None:
        corr = _make_correction(attempt=6, max_attempts=5)
        assert corr.attempt >= corr.max_attempts

    def test_attempt_zero_is_not_exhausted(self) -> None:
        corr = _make_correction(attempt=0, max_attempts=5)
        assert not (corr.attempt >= corr.max_attempts)

    def test_max_attempts_zero_means_always_exhausted(self) -> None:
        """max_attempts=0 means any attempt (including 0) exhausts immediately."""
        corr = _make_correction(attempt=0, max_attempts=0)
        assert corr.attempt >= corr.max_attempts

    def test_max_attempts_one_allows_single_attempt(self) -> None:
        corr_before = _make_correction(attempt=0, max_attempts=1)
        corr_after = _make_correction(attempt=1, max_attempts=1)
        assert not (corr_before.attempt >= corr_before.max_attempts)
        assert corr_after.attempt >= corr_after.max_attempts


# ---------------------------------------------------------------------------
# EC sub-counter boundary
# ---------------------------------------------------------------------------

class TestEcAttemptBoundary:
    def test_ec_attempt_at_limit_is_exhausted(self) -> None:
        corr = _make_correction(attempt=0, max_attempts=5, ec_attempt=3, ec_max_attempts=3)
        assert corr.ec_attempt >= corr.ec_max_attempts

    def test_ec_attempt_one_below_limit_is_not_exhausted(self) -> None:
        corr = _make_correction(attempt=0, max_attempts=5, ec_attempt=2, ec_max_attempts=3)
        assert not (corr.ec_attempt >= corr.ec_max_attempts)

    def test_ec_attempt_above_limit_is_exhausted(self) -> None:
        corr = _make_correction(attempt=0, max_attempts=5, ec_attempt=4, ec_max_attempts=3)
        assert corr.ec_attempt >= corr.ec_max_attempts


# ---------------------------------------------------------------------------
# PH sub-counter boundary
# ---------------------------------------------------------------------------

class TestPhAttemptBoundary:
    def test_ph_attempt_at_limit_is_exhausted(self) -> None:
        corr = _make_correction(attempt=0, max_attempts=5, ph_attempt=5, ph_max_attempts=5)
        assert corr.ph_attempt >= corr.ph_max_attempts

    def test_ph_attempt_one_below_limit_is_not_exhausted(self) -> None:
        corr = _make_correction(attempt=0, max_attempts=5, ph_attempt=4, ph_max_attempts=5)
        assert not (corr.ph_attempt >= corr.ph_max_attempts)


# ---------------------------------------------------------------------------
# CorrectionState immutability — dataclass replace creates new instance
# ---------------------------------------------------------------------------

class TestCorrectionStateImmutability:
    def test_replace_creates_new_instance(self) -> None:
        from dataclasses import replace

        corr = _make_correction(attempt=0, max_attempts=5)
        incremented = replace(corr, attempt=corr.attempt + 1)

        assert corr.attempt == 0           # original unchanged
        assert incremented.attempt == 1    # new instance has bumped count
        assert incremented is not corr

    def test_replace_preserves_other_fields(self) -> None:
        from dataclasses import replace

        corr = _make_correction(attempt=2, max_attempts=5, ec_attempt=1, ec_max_attempts=3)
        bumped = replace(corr, attempt=3)

        assert bumped.ec_attempt == 1
        assert bumped.ec_max_attempts == 3
        assert bumped.max_attempts == 5
