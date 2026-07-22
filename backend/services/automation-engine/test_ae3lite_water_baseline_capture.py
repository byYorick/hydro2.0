"""Unit tests: water baseline capture + budget math."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ae3lite.application.handlers.solution_fill import SolutionFillCheckHandler
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services.nutrient_pipeline import (
    PIPELINE_PHASE_FILL_CA,
    compute_component_targets,
    normalize_ec_ratios,
)


def test_compute_component_targets_cumulative() -> None:
    targets = compute_component_targets(
        water_ec=0.4,
        water_ph=7.0,
        target_ec=2.0,
        ratios={"calcium": 0.25, "magnesium": 0.15, "npk": 0.45, "micro": 0.15},
    )
    assert targets.nutrient_budget == pytest.approx(1.6)
    assert targets.T_ca == pytest.approx(0.4 + 1.6 * 0.25, abs=1e-3)
    assert targets.T_ca_mg == pytest.approx(0.4 + 1.6 * 0.40, abs=1e-3)
    assert targets.T_ca_mg_npk == pytest.approx(0.4 + 1.6 * 0.85, abs=1e-3)
    assert targets.T_full == pytest.approx(2.0, abs=1e-3)


def test_water_ec_ge_target_fail_closed() -> None:
    with pytest.raises(PlannerConfigurationError):
        compute_component_targets(
            water_ec=2.0,
            water_ph=7.0,
            target_ec=1.5,
            ratios={"calcium": 1.0},
        )


def test_normalize_ratios_empty_fail_closed() -> None:
    with pytest.raises(PlannerConfigurationError):
        normalize_ec_ratios({})


def test_component_targets_json_roundtrip() -> None:
    targets = compute_component_targets(
        water_ec=0.5,
        water_ph=6.8,
        target_ec=1.8,
        ratios={"calcium": 1, "magnesium": 1, "npk": 1, "micro": 1},
    )
    restored = type(targets).from_json(targets.to_json())
    assert restored is not None
    assert restored.T_ca == targets.T_ca
    assert restored.nutrient_budget == targets.nutrient_budget


@pytest.mark.asyncio
async def test_fill_reenter_does_not_overwrite_water_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-enter after Ca doses must reuse water_ec/budget (no second capture/insert)."""
    now = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)
    targets = compute_component_targets(
        water_ec=0.35,
        water_ph=7.1,
        target_ec=2.0,
        ratios={"calcium": 0.25, "magnesium": 0.15, "npk": 0.45, "micro": 0.15},
    )
    existing_corr = replace(
        CorrectionState.build_default(
            corr_step="corr_check",
            max_attempts=10,
            ec_max_attempts=10,
            ph_max_attempts=0,
            activated_here=False,
            stabilization_sec=10,
            return_stage_success="solution_fill_check",
            return_stage_fail="solution_fill_check",
        ),
        pipeline_phase=PIPELINE_PHASE_FILL_CA,
        active_component="calcium",
        water_ec=targets.water_ec,
        water_ph=targets.water_ph,
        nutrient_budget=targets.nutrient_budget,
        component_targets_json=targets.to_json(),
        baseline_id=42,
    )
    task = SimpleNamespace(
        id=7,
        zone_id=70,
        correction=existing_corr,
        workflow=SimpleNamespace(stage_retry_count=0),
    )
    runtime = SimpleNamespace(
        telemetry_max_age_sec=60,
        target_ec=2.0,
        target_ec_prepare=0.8,
        npk_ec_share=0.25,
        ec_component_ratios={"calcium": 0.25, "magnesium": 0.15, "npk": 0.45, "micro": 0.15},
        grow_cycle_id=None,
        correction={
            "max_ec_correction_attempts": 10,
            "max_ph_correction_attempts": 3,
            "stabilization_sec": 10,
        },
        process_calibrations={},
    )
    insert_mock = AsyncMock(return_value=99)
    event_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "ae3lite.infrastructure.repositories.prepare_baseline_repository"
        ".PgPrepareBaselineRepository.insert_baseline",
        insert_mock,
    )
    monkeypatch.setattr(
        "ae3lite.infrastructure.repositories.prepare_baseline_repository"
        ".PgPrepareBaselineRepository.fetch_latest_baseline",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr("common.db.create_zone_event", event_mock)

    handler = SolutionFillCheckHandler(runtime_monitor=SimpleNamespace(), command_gateway=SimpleNamespace())
    # If re-enter wrongly re-captured, elevated post-Ca EC would shrink budget.
    handler._read_target_metric_window = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"ready": True, "value": 7.0},
            {"ready": True, "value": 0.9},  # post-Ca EC — must NOT become new water_ec
        ]
    )
    handler._correction_config_for_task = lambda **_kw: runtime.correction  # type: ignore[method-assign]
    handler._process_cfg_for_task = lambda **_kw: {}  # type: ignore[method-assign]
    handler._observation_config = lambda **_kw: {}  # type: ignore[method-assign]
    handler._irrigation_ec_target = lambda **_kw: 2.0  # type: ignore[method-assign]
    handler._probe_snapshot_correction_fields = lambda **_kw: {}  # type: ignore[method-assign]

    corr = await handler._enter_fill_calcium_correction(
        task=task,
        plan=SimpleNamespace(runtime=runtime),
        runtime=runtime,
        now=now,
        return_stage_success="solution_fill_check",
        return_stage_fail="solution_fill_check",
    )

    assert corr.water_ec == pytest.approx(0.35)
    assert corr.nutrient_budget == pytest.approx(targets.nutrient_budget)
    assert corr.baseline_id == 42
    insert_mock.assert_not_awaited()
    event_mock.assert_not_awaited()
