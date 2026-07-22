"""Unit tests: dilute-on-overshoot helpers."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from ae3lite.application.services.correction_pipeline import should_dilute
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.services.nutrient_pipeline import ec_overshoot_requires_dilute


def test_overshoot_threshold() -> None:
    assert ec_overshoot_requires_dilute(current_ec=1.2, t_step=1.0, overshoot_pct=15) is True
    assert ec_overshoot_requires_dilute(current_ec=1.1, t_step=1.0, overshoot_pct=15) is False


def test_should_dilute_only_on_recirc_ec_step() -> None:
    base = CorrectionState.build_default(
        corr_step="corr_check",
        max_attempts=10,
        ec_max_attempts=10,
        ph_max_attempts=10,
        activated_here=False,
        stabilization_sec=10,
        return_stage_success="x",
        return_stage_fail="y",
    )
    corr = replace(base, pipeline_phase="recirc_ca", active_component="calcium", dilute_attempts=0)
    runtime = SimpleNamespace(
        recirc=SimpleNamespace(
            ec_overshoot_dilute_pct=15,
            dilute_max_attempts=3,
        )
    )
    assert should_dilute(
        corr=corr,
        runtime=runtime,
        current_ec=2.0,
        t_step=1.0,
        current_stage="prepare_recirculation_check",
    )
    # pH gate — no dilute
    corr_ph = replace(corr, pipeline_phase="recirc_ph_after_ca", active_component=None)
    assert not should_dilute(
        corr=corr_ph,
        runtime=runtime,
        current_ec=2.0,
        t_step=1.0,
        current_stage="prepare_recirculation_check",
    )
    # max attempts
    corr_max = replace(corr, dilute_attempts=3)
    assert not should_dilute(
        corr=corr_max,
        runtime=runtime,
        current_ec=2.0,
        t_step=1.0,
        current_stage="prepare_recirculation_check",
    )
