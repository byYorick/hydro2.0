"""Unit-тесты для build_pid_output_detail (extracted from CorrectionHandler, B1).

Pure function exercised with hand-crafted DosePlan/pid_state_before inputs.
No handler, no async, no DB. The goal is to lock in the PID term math and
the skip semantics (wrong step / no dose / missing pid_update → None) so
the UI "Логи PID" tab's contract cannot silently drift.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ae3lite.domain.services.correction_planner import DosePlan
from ae3lite.domain.services.pid_output_event import build_pid_output_detail


NOW = datetime(2026, 3, 10, 12, 0, 0)


def _dose_plan_ec(
    *,
    needs_ec: bool = True,
    ec_amount_ml: float = 2.5,
    coeffs: dict | None = None,
    pid_state_updates: dict | None = None,
    ec_pid_zone: str = "far",
) -> DosePlan:
    return DosePlan(
        needs_ec=needs_ec,
        ec_amount_ml=ec_amount_ml,
        ec_pid_zone=ec_pid_zone,
        ec_pid_coeffs=coeffs or {"kp": 10.0, "ki": 0.3, "kd": 0.0},
        pid_state_updates=pid_state_updates or {
            "ec": {
                "prev_error": 0.5,
                "integral": 20.0,
                "prev_derivative": 0.0,
                "current_zone": "far",
            }
        },
    )


def _dose_plan_ph(
    *,
    needs_ph_up: bool = True,
    needs_ph_down: bool = False,
    ph_amount_ml: float = 1.2,
    coeffs: dict | None = None,
    pid_state_updates: dict | None = None,
    ph_pid_zone: str = "close",
) -> DosePlan:
    return DosePlan(
        needs_ph_up=needs_ph_up,
        needs_ph_down=needs_ph_down,
        ph_amount_ml=ph_amount_ml,
        ph_pid_zone=ph_pid_zone,
        ph_pid_coeffs=coeffs or {"kp": 5.0, "ki": 0.1, "kd": 0.0},
        pid_state_updates=pid_state_updates or {
            "ph": {
                "prev_error": 0.3,
                "integral": 10.0,
                "prev_derivative": 0.0,
                "current_zone": "close",
            }
        },
    )


# ── EC branch ───────────────────────────────────────────────────────


def test_build_detail_ec_computes_pid_terms() -> None:
    prior_measurement = NOW - timedelta(seconds=20)
    detail = build_pid_output_detail(
        corr_step="corr_dose_ec",
        dose_plan=_dose_plan_ec(),
        pid_state_before={"ec": {"last_measurement_at": prior_measurement}},
        current_ph=6.0,
        current_ec=1.5,
        target_ph=6.0,
        target_ec=2.0,
        now=NOW,
    )
    assert detail is not None
    assert detail["type"] == "ec"
    assert detail["output"] == pytest.approx(2.5)
    assert detail["error"] == pytest.approx(0.5)
    # proportional = kp * gap = 10 * 0.5 = 5.0
    assert detail["proportional_term"] == pytest.approx(5.0)
    # integral_term = ki * integral = 0.3 * 20.0 = 6.0
    assert detail["integral_term"] == pytest.approx(6.0)
    # derivative_term = kd * derivative = 0 * 0 = 0
    assert detail["derivative_term"] == pytest.approx(0.0)
    assert detail["current"] == 1.5
    assert detail["target"] == 2.0
    # dt_seconds should equal the time gap between prior and now (20s).
    assert detail["dt_seconds"] == pytest.approx(20.0)
    assert detail["zone_state"] == "far"


def test_build_detail_ec_uses_current_zone_when_pid_zone_missing() -> None:
    plan = _dose_plan_ec(
        ec_pid_zone="",
        pid_state_updates={
            "ec": {
                "prev_error": 0.4,
                "integral": 5.0,
                "prev_derivative": 0.0,
                "current_zone": "dead",
            }
        },
    )
    detail = build_pid_output_detail(
        corr_step="corr_dose_ec",
        dose_plan=plan,
        pid_state_before={},
        current_ph=6.0,
        current_ec=1.9,
        target_ph=6.0,
        target_ec=2.0,
        now=NOW,
    )
    assert detail is not None
    assert detail["zone_state"] == "dead"


def test_build_detail_ec_skips_when_needs_ec_false() -> None:
    assert (
        build_pid_output_detail(
            corr_step="corr_dose_ec",
            dose_plan=_dose_plan_ec(needs_ec=False),
            pid_state_before={},
            current_ph=6.0,
            current_ec=2.0,
            target_ph=6.0,
            target_ec=2.0,
            now=NOW,
        )
        is None
    )


def test_build_detail_ec_skips_when_amount_ml_zero() -> None:
    assert (
        build_pid_output_detail(
            corr_step="corr_dose_ec",
            dose_plan=_dose_plan_ec(ec_amount_ml=0.0),
            pid_state_before={},
            current_ph=6.0,
            current_ec=2.0,
            target_ph=6.0,
            target_ec=2.0,
            now=NOW,
        )
        is None
    )


def test_build_detail_ec_skips_when_pid_state_updates_missing() -> None:
    plan = _dose_plan_ec(pid_state_updates={"other": {}})  # no "ec" key
    assert (
        build_pid_output_detail(
            corr_step="corr_dose_ec",
            dose_plan=plan,
            pid_state_before={},
            current_ph=6.0,
            current_ec=1.5,
            target_ph=6.0,
            target_ec=2.0,
            now=NOW,
        )
        is None
    )


# ── pH branch ───────────────────────────────────────────────────────


def test_build_detail_ph_up_computes_terms() -> None:
    detail = build_pid_output_detail(
        corr_step="corr_dose_ph",
        dose_plan=_dose_plan_ph(needs_ph_up=True),
        pid_state_before={
            "ph": {"last_measurement_at": NOW - timedelta(seconds=10)},
        },
        current_ph=5.7,
        current_ec=2.0,
        target_ph=6.0,
        target_ec=2.0,
        now=NOW,
    )
    assert detail is not None
    assert detail["type"] == "ph"
    # proportional = kp * gap = 5 * 0.3 = 1.5
    assert detail["proportional_term"] == pytest.approx(1.5)
    # integral = ki * integral = 0.1 * 10 = 1.0
    assert detail["integral_term"] == pytest.approx(1.0)
    assert detail["output"] == pytest.approx(1.2)
    assert detail["current"] == 5.7
    assert detail["target"] == 6.0
    assert detail["dt_seconds"] == pytest.approx(10.0)


def test_build_detail_ph_down_computes_terms() -> None:
    detail = build_pid_output_detail(
        corr_step="corr_dose_ph",
        dose_plan=_dose_plan_ph(needs_ph_up=False, needs_ph_down=True),
        pid_state_before={},
        current_ph=6.3,
        current_ec=2.0,
        target_ph=6.0,
        target_ec=2.0,
        now=NOW,
    )
    assert detail is not None
    assert detail["type"] == "ph"
    assert detail["current"] == 6.3


def test_build_detail_ph_skips_when_neither_direction_needed() -> None:
    plan = _dose_plan_ph(needs_ph_up=False, needs_ph_down=False)
    assert (
        build_pid_output_detail(
            corr_step="corr_dose_ph",
            dose_plan=plan,
            pid_state_before={},
            current_ph=6.0,
            current_ec=2.0,
            target_ph=6.0,
            target_ec=2.0,
            now=NOW,
        )
        is None
    )


# ── Skip conditions ─────────────────────────────────────────────────


def test_build_detail_skips_for_wrong_step() -> None:
    """corr_check / corr_wait_* / corr_activate etc. must skip silently."""
    for step in ("corr_check", "corr_wait_stable", "corr_activate", "corr_deactivate"):
        assert (
            build_pid_output_detail(
                corr_step=step,
                dose_plan=_dose_plan_ec(),
                pid_state_before={},
                current_ph=6.0,
                current_ec=1.5,
                target_ph=6.0,
                target_ec=2.0,
                now=NOW,
            )
            is None
        ), f"step={step} should skip"


# ── dt_seconds edge cases ───────────────────────────────────────────


def test_dt_seconds_none_when_no_prior_measurement() -> None:
    detail = build_pid_output_detail(
        corr_step="corr_dose_ec",
        dose_plan=_dose_plan_ec(),
        pid_state_before={"ec": {"last_measurement_at": None}},
        current_ph=6.0,
        current_ec=1.5,
        target_ph=6.0,
        target_ec=2.0,
        now=NOW,
    )
    assert detail is not None
    assert detail["dt_seconds"] is None


def test_dt_seconds_handles_tz_aware_prior_measurement() -> None:
    prior = datetime(2026, 3, 10, 11, 59, 40, tzinfo=timezone.utc)  # 20s earlier, tz-aware
    detail = build_pid_output_detail(
        corr_step="corr_dose_ec",
        dose_plan=_dose_plan_ec(),
        pid_state_before={"ec": {"last_measurement_at": prior}},
        current_ph=6.0,
        current_ec=1.5,
        target_ph=6.0,
        target_ec=2.0,
        now=NOW,
    )
    assert detail is not None
    assert detail["dt_seconds"] == pytest.approx(20.0)


def test_dt_seconds_clamps_to_zero_when_prior_is_in_future() -> None:
    """Guard against clock skew: prior > now → dt_sec clamped to 0, not negative."""
    prior = NOW + timedelta(seconds=5)
    detail = build_pid_output_detail(
        corr_step="corr_dose_ec",
        dose_plan=_dose_plan_ec(),
        pid_state_before={"ec": {"last_measurement_at": prior}},
        current_ph=6.0,
        current_ec=1.5,
        target_ph=6.0,
        target_ec=2.0,
        now=NOW,
    )
    assert detail is not None
    assert detail["dt_seconds"] == 0.0
