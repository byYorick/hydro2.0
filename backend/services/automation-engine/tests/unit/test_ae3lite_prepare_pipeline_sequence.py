"""Unit tests: prepare pipeline sequence Ca→pH→Mg→…"""

from __future__ import annotations

from dataclasses import replace

from ae3lite.application.services.correction_pipeline import maybe_advance_pipeline, pipeline_dose_flags
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.services.nutrient_pipeline import (
    RECIRC_PIPELINE_STEPS,
    pipeline_phase_for_index,
)


def _corr(phase: str) -> CorrectionState:
    base = CorrectionState.build_default(
        corr_step="corr_check",
        max_attempts=50,
        ec_max_attempts=50,
        ph_max_attempts=50,
        activated_here=False,
        stabilization_sec=10,
        return_stage_success="prepare_recirculation_stop_to_ready",
        return_stage_fail="prepare_recirculation_window_exhausted",
    )
    from ae3lite.domain.services.nutrient_pipeline import component_for_phase

    return replace(
        base,
        pipeline_phase=phase,
        active_component=component_for_phase(phase),
        ec_pid_frozen=("ph" in phase),
    )


def test_recirc_pipeline_step_count() -> None:
    assert len(RECIRC_PIPELINE_STEPS) == 8


def test_advance_full_sequence() -> None:
    phase = pipeline_phase_for_index(0)
    expected = [
        "recirc_ca",
        "recirc_ph_after_ca",
        "recirc_mg",
        "recirc_ph_after_mg",
        "recirc_npk",
        "recirc_ph_after_npk",
        "recirc_micro",
        "recirc_ph_final",
    ]
    assert phase == expected[0]
    for i, name in enumerate(expected):
        corr = _corr(name)
        flags = pipeline_dose_flags(corr)
        kind, component, _ = RECIRC_PIPELINE_STEPS[i]
        if kind == "ec":
            assert flags["allow_ec"] is True
            assert flags["allow_ph"] is False
            assert flags["active_component"] == component
        else:
            assert flags["allow_ec"] is False
            assert flags["allow_ph"] is True
            assert flags["freeze_ec_pid"] is True

        next_corr, finished, payload = maybe_advance_pipeline(
            corr=corr,
            current_stage="prepare_recirculation_check",
        )
        if i == len(expected) - 1:
            assert finished is True
        else:
            assert finished is False
            assert next_corr.pipeline_phase == expected[i + 1]
            assert payload is not None
            assert payload["to_phase"] == expected[i + 1]
