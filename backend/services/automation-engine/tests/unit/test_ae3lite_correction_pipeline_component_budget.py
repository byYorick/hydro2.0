from __future__ import annotations

import json
from dataclasses import replace

from ae3lite.application.services.correction_pipeline import irrigation_component_budget_guard
from ae3lite.domain.entities.workflow_state import CorrectionState


def _corr(*, phase: str, targets: dict | None) -> CorrectionState:
    base = CorrectionState.build_default(
        corr_step="corr_check",
        max_attempts=3,
        ec_max_attempts=3,
        ph_max_attempts=3,
        activated_here=False,
        stabilization_sec=30,
        return_stage_success="irrigation_check",
        return_stage_fail="irrigation_check",
    )
    return replace(
        base,
        pipeline_phase=phase,
        active_component="calcium" if phase == "irrigation_calcium" else "npk",
        component_targets_json=json.dumps(targets) if targets is not None else None,
    )


def _targets() -> dict:
    return {
        "water_ec": 0.4,
        "water_ph": 7.0,
        "target_ec": 1.4,
        "nutrient_budget": 1.0,
        "ratios": {"calcium": 0.2, "magnesium": 0.1, "npk": 0.6, "micro": 0.1},
        "T_ca": 0.6,
        "T_ca_mg": 0.7,
        "T_ca_mg_npk": 1.3,
        "T_full": 1.4,
    }


def test_calcium_top_up_is_blocked_without_authority_baseline() -> None:
    result = irrigation_component_budget_guard(
        corr=_corr(phase="irrigation_calcium", targets=None),
        current_ec=0.5,
        full_target_ec=1.4,
        ec_deadband=0.06,
    )

    assert result["allowed"] is False
    assert result["reason"] == "component_budget_unavailable"


def test_calcium_top_up_is_blocked_above_component_ceiling() -> None:
    result = irrigation_component_budget_guard(
        corr=_corr(phase="irrigation_calcium", targets=_targets()),
        current_ec=0.67,
        full_target_ec=1.4,
        ec_deadband=0.06,
    )

    assert result["allowed"] is False
    assert result["reason"] == "component_budget_exhausted"
    assert result["component_target_ec"] == 0.6


def test_npk_top_up_remains_allowed_below_component_ceiling() -> None:
    result = irrigation_component_budget_guard(
        corr=_corr(phase="irrigation_npk", targets=_targets()),
        current_ec=1.2,
        full_target_ec=1.4,
        ec_deadband=0.06,
    )

    assert result["allowed"] is True
    assert result["component_target_ec"] == 1.3
    assert result["effective_target_ec"] == 1.3


def test_component_top_up_is_blocked_for_stale_recipe_target() -> None:
    result = irrigation_component_budget_guard(
        corr=_corr(phase="irrigation_npk", targets=_targets()),
        current_ec=1.0,
        full_target_ec=1.8,
        ec_deadband=0.06,
    )

    assert result["allowed"] is False
    assert result["reason"] == "component_budget_stale_target"
