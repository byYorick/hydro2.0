"""Unit-тесты для CorrectionEventLogger (extracted from CorrectionHandler, B1).

Exercises the enrichment pipeline with a fake ``create_event_fn`` so we can
observe the exact payloads that would be written to ``zone_events``. No real
DB, no handler, no runtime_monitor.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from ae3lite.application.services.correction_event_logger import CorrectionEventLogger
from ae3lite.domain.entities.workflow_state import CorrectionState


class _FakeEventSink:
    """Recording stand-in for ``common.db.create_zone_event``."""

    def __init__(self, *, raise_on_call: bool = False) -> None:
        self.calls: list[tuple[int, str, dict]] = []
        self._raise = raise_on_call

    async def __call__(
        self, zone_id: int, event_type: str, payload: Mapping[str, Any]
    ) -> None:
        if self._raise:
            raise RuntimeError("event sink down")
        self.calls.append((zone_id, event_type, dict(payload)))


def _task(
    *,
    task_id: int = 42,
    current_stage: str = "solution_fill_check",
    workflow_phase: str = "tank_filling",
    topology: str = "two_tank",
    stage_entered_at: datetime | None = None,
) -> SimpleNamespace:
    workflow = SimpleNamespace(
        workflow_phase=workflow_phase,
        stage_entered_at=stage_entered_at,
    )
    return SimpleNamespace(
        id=task_id,
        current_stage=current_stage,
        workflow=workflow,
        topology=topology,
    )


def _corr(
    *,
    corr_step: str = "corr_check",
    attempt: int = 1,
    ec_attempt: int = 2,
    ph_attempt: int = 3,
    snapshot_event_id: int | None = None,
    snapshot_created_at: datetime | None = None,
    snapshot_cmd_id: str | None = None,
    snapshot_source_event_type: str | None = None,
) -> CorrectionState:
    return CorrectionState(
        corr_step=corr_step,
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
        snapshot_event_id=snapshot_event_id,
        snapshot_created_at=snapshot_created_at,
        snapshot_cmd_id=snapshot_cmd_id,
        snapshot_source_event_type=snapshot_source_event_type,
    )


def _logger(
    *,
    sink: _FakeEventSink | None = None,
    probe_ctx: Mapping[str, Any] | None = None,
) -> tuple[CorrectionEventLogger, _FakeEventSink]:
    sink = sink or _FakeEventSink()
    probe_fn = lambda *, task: probe_ctx  # noqa: E731
    return (
        CorrectionEventLogger(create_event_fn=sink, probe_snapshot_context_fn=probe_fn),
        sink,
    )


# ── correction_window_id ────────────────────────────────────────────


def test_correction_window_id_returns_none_for_none_task() -> None:
    assert CorrectionEventLogger.correction_window_id(task=None) is None


def test_correction_window_id_returns_none_when_stage_missing() -> None:
    task = SimpleNamespace(
        id=1,
        current_stage="",
        workflow=SimpleNamespace(workflow_phase="tank_filling"),
    )
    assert CorrectionEventLogger.correction_window_id(task=task) is None


def test_correction_window_id_returns_none_when_phase_missing() -> None:
    task = SimpleNamespace(
        id=1,
        current_stage="solution_fill_check",
        workflow=SimpleNamespace(workflow_phase=""),
    )
    assert CorrectionEventLogger.correction_window_id(task=task) is None


def test_correction_window_id_canonical_form() -> None:
    task = _task(task_id=42, current_stage="solution_fill_check", workflow_phase="tank_filling")
    assert (
        CorrectionEventLogger.correction_window_id(task=task)
        == "task:42:tank_filling:solution_fill_check"
    )


# ── observe_seq ─────────────────────────────────────────────────────


def test_observe_seq_uses_ec_attempt_for_ec() -> None:
    corr = _corr(ec_attempt=2, ph_attempt=7)
    assert CorrectionEventLogger.observe_seq(corr=corr, pid_type="ec") == 2


def test_observe_seq_uses_ph_attempt_for_ph() -> None:
    corr = _corr(ec_attempt=2, ph_attempt=7)
    assert CorrectionEventLogger.observe_seq(corr=corr, pid_type="ph") == 7


def test_observe_seq_adds_one_after_dose() -> None:
    corr = _corr(ec_attempt=2)
    assert (
        CorrectionEventLogger.observe_seq(corr=corr, pid_type="ec", after_dose=True) == 3
    )


def test_observe_seq_returns_none_for_zero_attempt() -> None:
    corr = _corr(ec_attempt=0)
    assert CorrectionEventLogger.observe_seq(corr=corr, pid_type="ec") is None


# ── serialize_metric_ts ─────────────────────────────────────────────


def test_serialize_metric_ts_none() -> None:
    assert CorrectionEventLogger.serialize_metric_ts(None) is None


def test_serialize_metric_ts_tz_aware_passes_through() -> None:
    ts = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    assert CorrectionEventLogger.serialize_metric_ts(ts) == "2026-03-10T12:00:00+00:00"


def test_serialize_metric_ts_naive_is_promoted_to_utc() -> None:
    ts = datetime(2026, 3, 10, 12, 0, 0)
    assert CorrectionEventLogger.serialize_metric_ts(ts) == "2026-03-10T12:00:00+00:00"


# ── log() enrichment ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_enriches_with_task_fields() -> None:
    logger, sink = _logger()
    task = _task(task_id=7, current_stage="solution_fill_check", workflow_phase="tank_filling")
    await logger.log(
        zone_id=447,
        event_type="CORRECTION_DECISION_MADE",
        task=task,
        corr=_corr(),
        payload={"selected_action": "ec"},
    )
    assert len(sink.calls) == 1
    zone_id, event_type, payload = sink.calls[0]
    assert zone_id == 447
    assert event_type == "CORRECTION_DECISION_MADE"
    assert payload["task_id"] == 7
    assert payload["stage"] == "solution_fill_check"
    assert payload["current_stage"] == "solution_fill_check"
    assert payload["workflow_phase"] == "tank_filling"
    assert payload["topology"] == "two_tank"
    assert payload["correction_window_id"] == "task:7:tank_filling:solution_fill_check"
    # Original payload preserved.
    assert payload["selected_action"] == "ec"


@pytest.mark.asyncio
async def test_log_enriches_with_correction_attempt_counters() -> None:
    logger, sink = _logger()
    await logger.log(
        zone_id=1,
        event_type="CORRECTION_CHECK",
        task=_task(),
        corr=_corr(attempt=3, ec_attempt=1, ph_attempt=2),
        payload={},
    )
    payload = sink.calls[0][2]
    assert payload["attempt"] == 3
    assert payload["ec_attempt"] == 1
    assert payload["ph_attempt"] == 2
    assert payload["ec_max_attempts"] == 4
    assert payload["ph_max_attempts"] == 4
    assert payload["corr_step"] == "corr_check"


@pytest.mark.asyncio
async def test_log_prefers_probe_snapshot_over_corr_state() -> None:
    probe = {"snapshot_event_id": 999, "snapshot_cmd_id": "cmd-probe"}
    logger, sink = _logger(probe_ctx=probe)
    await logger.log(
        zone_id=1,
        event_type="CORRECTION_OBSERVATION_EVALUATED",
        task=_task(),
        corr=_corr(
            snapshot_event_id=111,  # should be shadowed by probe
            snapshot_cmd_id="cmd-corr",
        ),
        payload={},
    )
    payload = sink.calls[0][2]
    assert payload["snapshot_event_id"] == 999
    assert payload["snapshot_cmd_id"] == "cmd-probe"
    assert payload["caused_by_event_id"] == 999


@pytest.mark.asyncio
async def test_log_falls_back_to_corr_snapshot_when_probe_unavailable() -> None:
    logger, sink = _logger(probe_ctx=None)
    await logger.log(
        zone_id=1,
        event_type="CORRECTION_DECISION_MADE",
        task=_task(),
        corr=_corr(
            snapshot_event_id=42,
            snapshot_created_at=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            snapshot_cmd_id="cmd-corr",
            snapshot_source_event_type="irr_state",
        ),
        payload={},
    )
    payload = sink.calls[0][2]
    assert payload["snapshot_event_id"] == 42
    assert payload["caused_by_event_id"] == 42
    assert payload["snapshot_cmd_id"] == "cmd-corr"
    assert payload["snapshot_source_event_type"] == "irr_state"
    assert "2026-03-10T12:00:00+00:00" in payload["snapshot_created_at"]


@pytest.mark.asyncio
async def test_log_skips_snapshot_context_when_both_sources_empty() -> None:
    logger, sink = _logger(probe_ctx=None)
    await logger.log(
        zone_id=1,
        event_type="CORRECTION_CHECK",
        task=_task(),
        corr=_corr(),  # no snapshot fields set
        payload={},
    )
    payload = sink.calls[0][2]
    assert "snapshot_event_id" not in payload
    assert "caused_by_event_id" not in payload


@pytest.mark.asyncio
async def test_log_does_not_overwrite_existing_payload_keys() -> None:
    """setdefault preserves caller-supplied values — critical for override semantics."""
    logger, sink = _logger()
    await logger.log(
        zone_id=1,
        event_type="CORRECTION_CHECK",
        task=_task(task_id=7),
        corr=_corr(attempt=9),
        payload={"task_id": 999, "attempt": 0},  # intentional overrides
    )
    payload = sink.calls[0][2]
    assert payload["task_id"] == 999  # not overwritten by enrichment
    assert payload["attempt"] == 0


@pytest.mark.asyncio
async def test_log_swallows_sink_exceptions_silently() -> None:
    """A failing event sink must not break correction cycle progress."""
    sink = _FakeEventSink(raise_on_call=True)
    logger, _ = _logger(sink=sink)
    # Should not raise.
    await logger.log(
        zone_id=1,
        event_type="CORRECTION_CHECK",
        task=_task(),
        corr=_corr(),
        payload={},
    )


@pytest.mark.asyncio
async def test_log_without_task_or_corr_still_writes_payload() -> None:
    logger, sink = _logger()
    await logger.log(
        zone_id=1,
        event_type="CORRECTION_STANDALONE",
        payload={"note": "no task no corr"},
    )
    assert len(sink.calls) == 1
    payload = sink.calls[0][2]
    assert payload["note"] == "no task no corr"
    # Task/correction fields must not be invented from thin air.
    assert "task_id" not in payload
    assert "attempt" not in payload
