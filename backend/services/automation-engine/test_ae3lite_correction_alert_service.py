"""Unit-тесты для CorrectionAlertService (extracted from CorrectionHandler, B1).

Pure functional test of each alert emitter against a fake sink — no real
biz_alerts transport, no handler, no database. Each test verifies:

  * alert code / alert_type / severity / zone_id
  * details payload shape (task_id, stage, component, counters)
  * scope_parts routing tags
  * silent error swallowing on sink failure
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ae3lite.application.services.correction_alert_service import (
    CorrectionAlertService,
)
from ae3lite.domain.entities.workflow_state import CorrectionState


class _FakeSink:
    """Records every alert payload so tests can assert on them."""

    def __init__(self, *, raise_on_call: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self._raise = raise_on_call

    async def __call__(self, **kwargs: Any) -> None:
        if self._raise:
            raise RuntimeError("alert transport down")
        self.calls.append(kwargs)


def _task(
    *,
    task_id: int = 42,
    zone_id: int = 447,
    current_stage: str = "solution_fill_check",
    topology: str = "two_tank",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=task_id,
        zone_id=zone_id,
        current_stage=current_stage,
        topology=topology,
    )


def _corr(*, attempt: int = 3, ec_attempt: int = 2, ph_attempt: int = 1) -> CorrectionState:
    return CorrectionState(
        corr_step="corr_check",
        attempt=attempt,
        max_attempts=5,
        ec_attempt=ec_attempt,
        ec_max_attempts=4,
        ph_attempt=ph_attempt,
        ph_max_attempts=4,
        activated_here=True,
        stabilization_sec=30,
        return_stage_success="next",
        return_stage_fail="fail",
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


def _make_service(*, raise_on_call: bool = False) -> tuple[CorrectionAlertService, _FakeSink]:
    sink = _FakeSink(raise_on_call=raise_on_call)
    return CorrectionAlertService(alert_sink_fn=sink), sink


# ── emit_correction_exhausted ────────────────────────────────────────


@pytest.mark.asyncio
async def test_emit_correction_exhausted_sends_generic_alert() -> None:
    service, sink = _make_service()
    await service.emit_correction_exhausted(
        task=_task(task_id=7, zone_id=100),
        corr=_corr(attempt=5, ec_attempt=3, ph_attempt=2),
    )
    assert len(sink.calls) == 1
    call = sink.calls[0]
    assert call["code"] == "biz_correction_exhausted"
    assert call["alert_type"] == "AE3 Correction Exhausted"
    assert call["severity"] == "error"
    assert call["zone_id"] == 100
    details = call["details"]
    assert details["task_id"] == 7
    assert details["stage"] == "solution_fill_check"
    assert details["topology"] == "two_tank"
    assert details["component"] == "correction:solution_fill_check"
    assert details["attempt"] == 5
    assert details["ec_attempt"] == 3
    assert details["ph_attempt"] == 2
    assert "pH/EC" in details["message"]
    assert call["scope_parts"] == ("stage:solution_fill_check", "topology:two_tank")


@pytest.mark.asyncio
async def test_emit_correction_exhausted_swallows_sink_errors() -> None:
    """A broken alert transport must not propagate — cycle must keep running."""
    service, _ = _make_service(raise_on_call=True)
    # Should not raise despite sink RuntimeError.
    await service.emit_correction_exhausted(
        task=_task(),
        corr=_corr(),
    )


# ── emit_irrigation_correction_exhausted ────────────────────────────


@pytest.mark.asyncio
async def test_emit_irrigation_correction_exhausted_uses_distinct_code() -> None:
    """Irrigation branch fires a separate alert code so ops can route it differently."""
    service, sink = _make_service()
    await service.emit_irrigation_correction_exhausted(
        task=_task(task_id=8, zone_id=200, current_stage="irrigation_check"),
        corr=_corr(attempt=4),
    )
    assert len(sink.calls) == 1
    call = sink.calls[0]
    assert call["code"] == "biz_irrigation_correction_exhausted"
    assert call["alert_type"] == "AE3 Irrigation Correction Exhausted"
    assert call["severity"] == "error"
    assert call["zone_id"] == 200
    details = call["details"]
    assert details["task_id"] == 8
    assert details["stage"] == "irrigation_check"
    assert details["component"] == "correction:irrigation_check"
    assert details["attempt"] == 4
    assert "полив продолжится" in details["message"]
    assert call["scope_parts"] == ("stage:irrigation_check", "topology:two_tank")


@pytest.mark.asyncio
async def test_emit_irrigation_correction_exhausted_swallows_sink_errors() -> None:
    service, _ = _make_service(raise_on_call=True)
    await service.emit_irrigation_correction_exhausted(
        task=_task(current_stage="irrigation_check"),
        corr=_corr(),
    )


# ── emit_no_effect ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_emit_no_effect_embeds_pid_type_in_alert_code() -> None:
    """Different pid_type → different alert code so ops subscriptions differentiate."""
    service, sink = _make_service()
    await service.emit_no_effect(
        task=_task(zone_id=300, current_stage="solution_fill_check"),
        pid_type="ec",
        baseline_value=1.0,
        observed_value=1.05,
        expected_effect=0.4,
        actual_effect=0.05,
        no_effect_limit=3,
    )
    assert len(sink.calls) == 1
    call = sink.calls[0]
    assert call["code"] == "biz_ec_correction_no_effect"
    assert call["alert_type"] == "AE3 Correction No Effect"
    assert call["severity"] == "error"
    assert call["zone_id"] == 300
    details = call["details"]
    assert details["pid_type"] == "ec"
    assert details["baseline_value"] == 1.0
    assert details["observed_value"] == 1.05
    assert details["expected_effect"] == 0.4
    assert details["actual_effect"] == 0.05
    assert details["no_effect_limit"] == 3
    assert details["component"] == "correction:solution_fill_check"
    assert call["scope_parts"] == ("pid_type:ec", "stage:solution_fill_check")
    assert "EC" in call["message"]
    assert "3 раз" in call["message"]


@pytest.mark.asyncio
async def test_emit_no_effect_for_ph_uses_ph_code() -> None:
    service, sink = _make_service()
    await service.emit_no_effect(
        task=_task(),
        pid_type="ph",
        baseline_value=6.0,
        observed_value=6.02,
        expected_effect=0.5,
        actual_effect=0.02,
        no_effect_limit=3,
    )
    assert sink.calls[0]["code"] == "biz_ph_correction_no_effect"
    assert sink.calls[0]["scope_parts"] == ("pid_type:ph", "stage:solution_fill_check")
    assert "PH" in sink.calls[0]["message"]


@pytest.mark.asyncio
async def test_emit_no_effect_swallows_sink_errors() -> None:
    service, _ = _make_service(raise_on_call=True)
    await service.emit_no_effect(
        task=_task(),
        pid_type="ec",
        baseline_value=1.0,
        observed_value=1.0,
        expected_effect=0.4,
        actual_effect=0.0,
        no_effect_limit=3,
    )


# ── Details dict immutability ───────────────────────────────────────


@pytest.mark.asyncio
async def test_details_dict_is_copy_not_reference() -> None:
    """Service must hand the sink an owned dict so upstream mutation is safe."""
    service, sink = _make_service()
    await service.emit_correction_exhausted(task=_task(), corr=_corr())
    details = sink.calls[0]["details"]
    # Mutating the received dict must not affect a subsequent emit.
    details["task_id"] = -1
    await service.emit_correction_exhausted(task=_task(task_id=99), corr=_corr())
    assert sink.calls[1]["details"]["task_id"] == 99
