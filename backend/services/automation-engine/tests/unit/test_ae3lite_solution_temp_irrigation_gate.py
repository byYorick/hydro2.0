"""G4: температура раствора блокирует только новый полив успешным skip."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from _test_support_runtime_plan import make_runtime_plan
from ae3lite.application.handlers.decision_gate import DecisionGateHandler
from ae3lite.config.loader import load_runtime_plan
from ae3lite.config.runtime_plan_builder import resolve_two_tank_runtime
from ae3lite.domain.services.irrigation_decision_controller import (
    IrrigationDecision,
    IrrigationDecisionController,
)
from ae3lite.domain.services.solution_temp_irrigation_guard import (
    DEFAULT_SOLUTION_TEMP_STALE_SEC,
    REASON_SOLUTION_TEMP_OUT_OF_BAND,
    REASON_SOLUTION_TEMP_UNAVAILABLE,
    evaluate_solution_temp_hold,
)
from ae3lite.hydraulics.failure_report import close_upward_capture, drain_upward_reports, open_upward_capture
from ae3lite.infrastructure.read_models.zone_snapshot_read_model import PgZoneSnapshotReadModel
from test_ae3lite_runtime_plan_builder import _snapshot


NOW = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
HOLD_SEC = 600
MIN_C = 18.0
MAX_C = 24.0


def _hot_series() -> tuple[dict, ...]:
    start = NOW - timedelta(seconds=HOLD_SEC)
    return (
        {"ts": start, "value": 30.0},
        {"ts": start + timedelta(seconds=HOLD_SEC // 2), "value": 30.0},
        {"ts": NOW, "value": 30.0},
    )


def _reading(*, samples: tuple[dict, ...] | None, last: dict | None = None) -> dict:
    return {
        "has_sensor": samples is not None or last is not None,
        "telemetry_last": last,
        "samples": samples or (),
    }


class _Monitor:
    def __init__(self, reading: dict | None = None, *, forbid: bool = False, boom: bool = False) -> None:
        self.reading = reading
        self.forbid = forbid
        self.boom = boom
        self.calls: list[dict] = []

    async def read_solution_temp_window(self, **kwargs):
        self.calls.append(kwargs)
        if self.forbid:
            raise AssertionError("temperature gate must not read telemetry")
        if self.boom:
            raise RuntimeError("telemetry read failed")
        return self.reading


class _Repository:
    def __init__(self) -> None:
        self.saved: list[dict] = []
        self.mark_failed_called = False

    async def update_irrigation_runtime(self, **kwargs):
        self.saved.append(kwargs)
        return SimpleNamespace(
            id=11,
            zone_id=7,
            current_stage="decision_gate",
            workflow_phase="ready",
            topology="two_tank",
            irrigation_decision_strategy=kwargs.get("irrigation_decision_strategy"),
            irrigation_bundle_revision=None,
        )

    async def mark_failed(self, **_kwargs):
        self.mark_failed_called = True
        raise AssertionError("mark_failed must not run for a solution temp skip")


class _FixedController:
    def __init__(self, decision: IrrigationDecision) -> None:
        self._decision = decision

    async def evaluate(self, **_kwargs):
        return self._decision


def _task() -> SimpleNamespace:
    return SimpleNamespace(
        id=11,
        zone_id=7,
        claimed_by="worker",
        irrigation_mode="normal",
        irrigation_requested_duration_sec=120,
        topology="two_tank",
        claim_generation=1,
        current_stage="decision_gate",
        workflow_phase="ready",
    )


def _plan(**health: object):
    payload = {
        "required": True,
        "min_c": MIN_C,
        "max_c": MAX_C,
        "breach_hold_sec": HOLD_SEC,
    }
    payload.update(health)
    return SimpleNamespace(
        runtime=make_runtime_plan(
            irrigation_decision={"strategy": "task"},
            solution_health=payload,
        )
    )


@pytest.fixture(autouse=True)
def _silent_zone_event(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "ae3lite.application.handlers.decision_gate.create_zone_event",
        _noop,
    )


async def _run(monitor: _Monitor, *, controller: object | None = None, plan: object | None = None):
    repository = _Repository()
    handler = DecisionGateHandler(
        runtime_monitor=monitor,
        command_gateway=object(),
        task_repository=repository,
        decision_controller=controller or IrrigationDecisionController(),
    )
    token = open_upward_capture()
    try:
        outcome = await handler.run(
            task=_task(),
            plan=plan or _plan(),
            stage_def=SimpleNamespace(),
            now=NOW,
        )
        reports = drain_upward_reports()
    finally:
        close_upward_capture(token)
    return outcome, reports, repository, monitor


def _assert_not_failed(outcome, repository: _Repository) -> None:
    assert outcome.kind != "fail"
    assert repository.mark_failed_called is False
    assert len(repository.saved) == 1
    assert repository.saved[0]["irrigation_decision_outcome"] != "fail"


@pytest.mark.asyncio
async def test_full_hold_above_max_skips_without_fail_or_temp_alert() -> None:
    outcome, reports, repository, monitor = await _run(
        _Monitor(_reading(samples=_hot_series(), last={"ts": NOW, "value": 30.0})),
    )

    _assert_not_failed(outcome, repository)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "completed_skip"
    assert outcome.next_stage != "irrigation_start"
    assert repository.saved[0]["irrigation_decision_reason_code"] == REASON_SOLUTION_TEMP_OUT_OF_BAND
    assert monitor.calls[0]["since_ts"] == NOW - timedelta(seconds=HOLD_SEC)
    assert monitor.calls[0]["until_ts"] == NOW
    assert [report.code for report in reports] == []
    assert not any(str(report.code).startswith("biz_solution_temp") for report in reports)


@pytest.mark.asyncio
async def test_single_sample_and_telemetry_last_do_not_block() -> None:
    outcome, reports, repository, monitor = await _run(
        _Monitor(
            _reading(
                samples=({"ts": NOW, "value": 30.0},),
                last={"ts": NOW, "value": 30.0},
            )
        ),
    )

    _assert_not_failed(outcome, repository)
    assert outcome.next_stage == "irrigation_start"
    assert repository.saved[0]["irrigation_decision_reason_code"] == "irrigation_task_strategy_run"
    assert repository.saved[0]["irrigation_decision_reason_code"] != REASON_SOLUTION_TEMP_OUT_OF_BAND
    assert len(monitor.calls) == 1
    assert [report.code for report in reports] == []


@pytest.mark.asyncio
async def test_required_without_telemetry_skips_unavailable() -> None:
    outcome, _reports, repository, monitor = await _run(
        _Monitor(_reading(samples=())),
    )

    _assert_not_failed(outcome, repository)
    assert outcome.next_stage == "completed_skip"
    assert repository.saved[0]["irrigation_decision_reason_code"] == REASON_SOLUTION_TEMP_UNAVAILABLE
    assert len(monitor.calls) == 1


@pytest.mark.asyncio
async def test_required_false_keeps_g1_path_without_reading_temperature() -> None:
    outcome, _reports, repository, monitor = await _run(
        _Monitor(forbid=True),
        plan=_plan(required=False),
    )

    _assert_not_failed(outcome, repository)
    assert outcome.next_stage == "irrigation_start"
    assert repository.saved[0]["irrigation_decision_reason_code"] == "irrigation_task_strategy_run"
    assert monitor.calls == []


@pytest.mark.asyncio
async def test_missing_limit_does_not_read_temperature() -> None:
    outcome, _reports, repository, monitor = await _run(
        _Monitor(forbid=True),
        plan=_plan(max_c=None),
    )

    _assert_not_failed(outcome, repository)
    assert outcome.next_stage == "irrigation_start"
    assert monitor.calls == []


@pytest.mark.asyncio
async def test_g1_skip_is_replaced_by_one_temperature_outcome() -> None:
    controller = _FixedController(
        IrrigationDecision(outcome="skip", reason_code="smart_soil_target_missing", degraded=False)
    )
    outcome, reports, repository, _monitor = await _run(
        _Monitor(_reading(samples=_hot_series())),
        controller=controller,
    )

    _assert_not_failed(outcome, repository)
    assert outcome.next_stage == "completed_skip"
    assert repository.saved[0]["irrigation_decision_reason_code"] == REASON_SOLUTION_TEMP_OUT_OF_BAND
    assert [report.code for report in reports] == []


@pytest.mark.asyncio
async def test_g1_skip_stays_when_temperature_does_not_block() -> None:
    controller = _FixedController(
        IrrigationDecision(
            outcome="skip",
            reason_code="smart_soil_telemetry_missing_or_stale",
            degraded=False,
        )
    )
    outcome, reports, repository, _monitor = await _run(
        _Monitor(_reading(samples=({"ts": NOW, "value": 30.0},))),
        controller=controller,
    )

    _assert_not_failed(outcome, repository)
    assert outcome.next_stage == "completed_skip"
    assert repository.saved[0]["irrigation_decision_reason_code"] == "smart_soil_telemetry_missing_or_stale"
    assert [report.code for report in reports] == []


def test_in_band_sample_or_gap_does_not_block() -> None:
    start = NOW - timedelta(seconds=HOLD_SEC)
    in_band = _hot_series()[:1] + ({"ts": start + timedelta(seconds=300), "value": 20.0},) + _hot_series()[2:]
    assert (
        evaluate_solution_temp_hold(
            min_c=MIN_C,
            max_c=MAX_C,
            hold_sec=HOLD_SEC,
            stale_sec=DEFAULT_SOLUTION_TEMP_STALE_SEC,
            now=NOW,
            reading=_reading(samples=in_band),
        )
        is None
    )

    gapped = (
        {"ts": start, "value": 30.0},
        {"ts": start + timedelta(seconds=250), "value": 30.0},
        {"ts": NOW, "value": 30.0},
    )
    assert (
        evaluate_solution_temp_hold(
            min_c=MIN_C,
            max_c=MAX_C,
            hold_sec=HOLD_SEC,
            stale_sec=200,
            now=NOW,
            reading=_reading(samples=gapped, last={"ts": NOW, "value": 30.0}),
        )
        is None
    )

    on_max = tuple({**sample, "value": MAX_C} for sample in _hot_series())
    assert (
        evaluate_solution_temp_hold(
            min_c=MIN_C,
            max_c=MAX_C,
            hold_sec=HOLD_SEC,
            stale_sec=DEFAULT_SOLUTION_TEMP_STALE_SEC,
            now=NOW,
            reading=_reading(samples=on_max),
        )
        is None
    )


def test_telemetry_last_alone_does_not_prove_hold() -> None:
    verdict = evaluate_solution_temp_hold(
        min_c=MIN_C,
        max_c=MAX_C,
        hold_sec=HOLD_SEC,
        stale_sec=DEFAULT_SOLUTION_TEMP_STALE_SEC,
        now=NOW,
        reading=_reading(samples=(), last={"ts": NOW, "value": 30.0}),
    )
    assert verdict is None


def test_builder_takes_limits_from_phase_columns_and_required_from_extensions() -> None:
    phase_targets = PgZoneSnapshotReadModel()._build_phase_targets(
        zone_row={
            "ph_target": 5.8,
            "ec_target": 2.2,
            "solution_temp_target": Decimal("21.00"),
            "solution_temp_min": Decimal("18.00"),
            "solution_temp_max": Decimal("24.00"),
            "phase_extensions": {
                "solution_health": {"required": True, "breach_hold_sec": 900},
                "targets": {"solution_temp": {"min": 90.0, "max": 100.0}},
            },
        }
    )
    assert phase_targets["solution_temp"]["min"] == 18.0
    assert phase_targets["solution_temp"]["max"] == 24.0
    assert phase_targets["solution_temp"]["target"] == 21.0

    snap = _snapshot(correction={})
    snap.phase_targets = {
        **dict(snap.phase_targets),
        "solution_temp": phase_targets["solution_temp"],
        "extensions": phase_targets["extensions"],
    }
    runtime = resolve_two_tank_runtime(snap)
    plan = load_runtime_plan(runtime, zone_id=1)

    assert runtime["solution_health"] == {
        "required": True,
        "min_c": 18.0,
        "max_c": 24.0,
        "breach_hold_sec": 900,
    }
    assert plan.solution_health.required is True
    assert plan.solution_health.min_c == 18.0
    assert plan.solution_health.max_c == 24.0
    assert plan.solution_health.breach_hold_sec == 900


def test_builder_defaults_when_extension_and_limits_absent() -> None:
    runtime = resolve_two_tank_runtime(_snapshot(correction={}))
    assert runtime["solution_health"] == {
        "required": False,
        "min_c": None,
        "max_c": None,
        "breach_hold_sec": 600,
    }


def test_target_column_does_not_fill_empty_limits() -> None:
    phase_targets = PgZoneSnapshotReadModel()._build_phase_targets(
        zone_row={
            "solution_temp_target": 20,
            "solution_temp_min": 18,
            "phase_extensions": {"solution_health": {"required": True}},
        }
    )
    assert phase_targets["solution_temp"] == {"target": 20.0, "min": 18.0}
    assert "max" not in phase_targets["solution_temp"]

    snap = _snapshot(correction={})
    snap.phase_targets = {
        **dict(snap.phase_targets),
        "solution_temp": phase_targets["solution_temp"],
        "extensions": phase_targets["extensions"],
    }
    health = resolve_two_tank_runtime(snap)["solution_health"]
    assert health["required"] is True
    assert health["min_c"] == 18.0
    assert health["max_c"] is None
    assert health["breach_hold_sec"] == 600
