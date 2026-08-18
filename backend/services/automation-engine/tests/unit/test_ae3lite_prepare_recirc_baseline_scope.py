"""prepare_recirc: baseline только текущего task (не zone-wide)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ae3lite.application.handlers.prepare_recirc import PrepareRecircCheckHandler
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import ErrorCodes, TaskExecutionError
from ae3lite.domain.services.nutrient_pipeline import compute_component_targets


def _runtime() -> SimpleNamespace:
    return SimpleNamespace(
        correction={
            "max_ec_correction_attempts": 10,
            "max_ph_correction_attempts": 3,
            "stabilization_sec": 10,
            "prepare_recirculation_max_correction_attempts": 20,
        },
        process_calibrations={},
    )


def _handler() -> PrepareRecircCheckHandler:
    handler = PrepareRecircCheckHandler(
        runtime_monitor=SimpleNamespace(),
        command_gateway=SimpleNamespace(),
    )
    handler._correction_config_for_task = lambda **_kw: _runtime().correction  # type: ignore[method-assign]
    handler._probe_snapshot_correction_fields = lambda **_kw: {}  # type: ignore[method-assign]
    return handler


@pytest.mark.asyncio
async def test_prepare_reuses_same_task_corr_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    targets = compute_component_targets(
        water_ec=0.4,
        water_ph=7.0,
        target_ec=1.4,
        ratios={"calcium": 0.36, "magnesium": 0.17, "npk": 0.44, "micro": 0.03},
    )
    existing = replace_corr_with_targets(targets, baseline_id=11)
    task = SimpleNamespace(id=5, zone_id=1, correction=existing)
    fetch_mock = AsyncMock(return_value={"id": 99, "water_ec": 0.1, "target_ec": 9.0})
    monkeypatch.setattr(
        "ae3lite.infrastructure.repositories.prepare_baseline_repository"
        ".PgPrepareBaselineRepository.fetch_latest_baseline",
        fetch_mock,
    )

    corr = await _handler()._enter_recirc_pipeline_correction(
        task=task,
        runtime=_runtime(),
        return_stage_success="prepare_recirculation_stop_to_ready",
        return_stage_fail="prepare_recirculation_window_exhausted",
    )

    assert corr.water_ec == pytest.approx(0.4)
    assert corr.baseline_id == 11
    fetch_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_loads_baseline_only_for_current_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    targets = compute_component_targets(
        water_ec=0.45,
        water_ph=7.0,
        target_ec=1.4,
        ratios={"calcium": 0.36, "magnesium": 0.17, "npk": 0.44, "micro": 0.03},
    )
    task = SimpleNamespace(
        id=88,
        zone_id=1,
        correction=CorrectionState.build_default(
            corr_step="corr_check",
            max_attempts=10,
            ec_max_attempts=10,
            ph_max_attempts=3,
            activated_here=False,
            stabilization_sec=10,
            return_stage_success="prepare_recirculation_stop_to_ready",
            return_stage_fail="prepare_recirculation_window_exhausted",
        ),
    )
    stale_zone_row = {
        "id": 1,
        "water_ec": 0.4385,
        "water_ph": 7.0,
        "target_ec": 1.4,
        "ratios_json": {"calcium": 0.36, "magnesium": 0.17, "npk": 0.44, "micro": 0.03},
        "component_targets_json": None,
        "ae_task_id": 1,
    }
    own_row = {
        "id": 7,
        "water_ec": targets.water_ec,
        "water_ph": targets.water_ph,
        "target_ec": targets.target_ec,
        "ratios_json": {"calcium": 0.36, "magnesium": 0.17, "npk": 0.44, "micro": 0.03},
        "component_targets_json": targets.to_json(),
        "ae_task_id": 88,
    }

    async def _fetch(*, zone_id, ae_task_id=None, conn=None):  # noqa: ANN001
        if ae_task_id is None:
            return stale_zone_row
        if ae_task_id == 88:
            return own_row
        return None

    fetch_mock = AsyncMock(side_effect=_fetch)
    monkeypatch.setattr(
        "ae3lite.infrastructure.repositories.prepare_baseline_repository"
        ".PgPrepareBaselineRepository.fetch_latest_baseline",
        fetch_mock,
    )

    corr = await _handler()._enter_recirc_pipeline_correction(
        task=task,
        runtime=_runtime(),
        return_stage_success="prepare_recirculation_stop_to_ready",
        return_stage_fail="prepare_recirculation_window_exhausted",
    )

    assert corr.water_ec == pytest.approx(0.45)
    assert corr.baseline_id == 7
    assert all(call.kwargs.get("ae_task_id") == 88 for call in fetch_mock.await_args_list)
    assert not any(call.kwargs.get("ae_task_id") is None for call in fetch_mock.await_args_list)


@pytest.mark.asyncio
async def test_prepare_fails_closed_when_no_task_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stale zone-wide baseline must NOT be used → ae3_water_baseline_invalid."""
    task = SimpleNamespace(
        id=3,
        zone_id=1,
        correction=CorrectionState.build_default(
            corr_step="corr_check",
            max_attempts=10,
            ec_max_attempts=10,
            ph_max_attempts=3,
            activated_here=False,
            stabilization_sec=10,
            return_stage_success="prepare_recirculation_stop_to_ready",
            return_stage_fail="prepare_recirculation_window_exhausted",
        ),
    )
    stale = {
        "id": 1,
        "water_ec": 0.4385,
        "water_ph": 7.0,
        "target_ec": 1.4,
        "ratios_json": {"calcium": 0.36},
        "component_targets_json": None,
        "ae_task_id": 1,
    }

    async def _fetch(*, zone_id, ae_task_id=None, conn=None):  # noqa: ANN001
        if ae_task_id is None:
            return stale
        return None

    monkeypatch.setattr(
        "ae3lite.infrastructure.repositories.prepare_baseline_repository"
        ".PgPrepareBaselineRepository.fetch_latest_baseline",
        AsyncMock(side_effect=_fetch),
    )

    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler()._enter_recirc_pipeline_correction(
            task=task,
            runtime=_runtime(),
            return_stage_success="prepare_recirculation_stop_to_ready",
            return_stage_fail="prepare_recirculation_window_exhausted",
        )

    assert exc_info.value.code == ErrorCodes.AE3_WATER_BASELINE_INVALID


def replace_corr_with_targets(targets, *, baseline_id: int) -> CorrectionState:
    from dataclasses import replace

    base = CorrectionState.build_default(
        corr_step="corr_check",
        max_attempts=10,
        ec_max_attempts=10,
        ph_max_attempts=3,
        activated_here=False,
        stabilization_sec=10,
        return_stage_success="prepare_recirculation_stop_to_ready",
        return_stage_fail="prepare_recirculation_window_exhausted",
    )
    return replace(
        base,
        water_ec=targets.water_ec,
        water_ph=targets.water_ph,
        nutrient_budget=targets.nutrient_budget,
        component_targets_json=targets.to_json(),
        baseline_id=baseline_id,
    )
