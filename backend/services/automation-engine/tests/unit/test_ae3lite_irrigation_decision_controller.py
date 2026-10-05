from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from _test_support_runtime_plan import make_runtime_plan
from ae3lite.application.handlers.decision_gate import DecisionGateHandler
from ae3lite.domain.services.irrigation_decision_controller import IrrigationDecisionController
from ae3lite.hydraulics.failure_report import close_upward_capture, drain_upward_reports, open_upward_capture


NOW = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)


class _RuntimeMonitor:
    def __init__(self, sensor_windows: tuple[dict, ...], *, is_stale: bool = False) -> None:
        self.sensor_windows = sensor_windows
        self.is_stale = is_stale

    async def read_metric_windows(self, **_kwargs):
        return {
            "has_sensors": bool(self.sensor_windows),
            "sensor_windows": self.sensor_windows,
            "latest_sample_ts": NOW,
            "sample_age_sec": 0.0,
            "is_stale": self.is_stale,
        }


@pytest.mark.asyncio
async def test_smart_soil_runs_when_below_target_band() -> None:
    controller = IrrigationDecisionController()
    runtime = make_runtime_plan(
        irrigation_decision={
            "strategy": "smart_soil_v1",
            "config": {"lookback_sec": 1800, "min_samples": 3, "stale_after_sec": 600, "hysteresis_pct": 2.0},
        },
        soil_moisture_target={"min": 38.0, "max": 48.0, "target": 43.0},
    )
    monitor = _RuntimeMonitor((
        {"sensor_label": "soil-1", "samples": ({"value": 30.0}, {"value": 31.0})},
        {"sensor_label": "soil-2", "samples": ({"value": 32.0}, {"value": 33.0})},
    ))

    result = await controller.evaluate(
        zone_id=7,
        runtime_monitor=monitor,
        runtime=runtime,
        mode="normal",
        requested_duration_sec=120,
        now=NOW,
    )

    assert result.outcome == "run"
    assert result.reason_code == "smart_soil_below_min"


@pytest.mark.asyncio
async def test_smart_soil_skips_inside_target_band() -> None:
    controller = IrrigationDecisionController()
    runtime = make_runtime_plan(
        irrigation_decision={
            "strategy": "smart_soil_v1",
            "config": {"lookback_sec": 1800, "min_samples": 2, "stale_after_sec": 600, "hysteresis_pct": 0.0},
        },
        soil_moisture_target={"min": 38.0, "max": 48.0, "target": 43.0},
    )
    monitor = _RuntimeMonitor((
        {"sensor_label": "soil-1", "samples": ({"value": 41.0}, {"value": 42.0})},
    ))

    result = await controller.evaluate(
        zone_id=7,
        runtime_monitor=monitor,
        runtime=runtime,
        mode="normal",
        requested_duration_sec=120,
        now=NOW,
    )

    assert result.outcome == "skip"
    assert result.reason_code == "smart_soil_within_band"


@pytest.mark.asyncio
async def test_smart_soil_returns_degraded_run_when_samples_missing() -> None:
    controller = IrrigationDecisionController()
    runtime = make_runtime_plan(
        irrigation_decision={
            "strategy": "smart_soil_v1",
            "config": {"lookback_sec": 1800, "min_samples": 3, "stale_after_sec": 600},
        },
        soil_moisture_target={"min": 38.0, "max": 48.0, "target": 43.0},
    )
    monitor = _RuntimeMonitor((
        {"sensor_label": "soil-1", "samples": ({"value": 34.0},)},
    ), is_stale=True)

    result = await controller.evaluate(
        zone_id=7,
        runtime_monitor=monitor,
        runtime=runtime,
        mode="normal",
        requested_duration_sec=120,
        now=NOW,
    )

    assert result.outcome == "skip"
    assert result.outcome != "fail"
    assert result.degraded is False
    assert result.reason_code == "smart_soil_telemetry_missing_or_stale"


@pytest.mark.asyncio
async def test_smart_soil_accepts_day_night_curve_target() -> None:
    controller = IrrigationDecisionController()
    runtime = make_runtime_plan(
        irrigation_decision={
            "strategy": "smart_soil_v1",
            "config": {"lookback_sec": 1800, "min_samples": 3, "stale_after_sec": 600, "hysteresis_pct": 0.0},
        },
        soil_moisture_target={"day": 40.0, "night": 55.0, "day_start_time": "06:00:00", "day_hours": 16},
    )
    monitor = _RuntimeMonitor((
        {"sensor_label": "soil-1", "samples": ({"value": 30.0}, {"value": 31.0})},
        {"sensor_label": "soil-2", "samples": ({"value": 32.0}, {"value": 33.0})},
    ))

    result = await controller.evaluate(
        zone_id=7,
        runtime_monitor=monitor,
        runtime=runtime,
        mode="normal",
        requested_duration_sec=120,
        now=NOW,
    )

    assert result.outcome == "run"
    assert result.reason_code in ("smart_soil_below_min", "smart_soil_degraded_below_min")


@pytest.mark.asyncio
async def test_smart_soil_works_with_single_sensor_and_low_sample_count() -> None:
    controller = IrrigationDecisionController()
    runtime = make_runtime_plan(
        irrigation_decision={
            "strategy": "smart_soil_v1",
            "config": {"lookback_sec": 1800, "min_samples": 3, "stale_after_sec": 600, "hysteresis_pct": 0.0},
        },
        soil_moisture_target={"min": 40.0, "max": 50.0, "target": 45.0},
    )
    monitor = _RuntimeMonitor((
        {"sensor_label": "soil-1", "samples": ({"value": 30.0},)},
    ))

    result = await controller.evaluate(
        zone_id=7,
        runtime_monitor=monitor,
        runtime=runtime,
        mode="normal",
        requested_duration_sec=120,
        now=NOW,
    )

    assert result.outcome == "run"
    assert result.degraded is True
    assert result.reason_code == "smart_soil_degraded_below_min"


@pytest.mark.asyncio
async def test_force_mode_bypasses_decision_strategy() -> None:
    controller = IrrigationDecisionController()

    result = await controller.evaluate(
        zone_id=7,
        runtime_monitor=_RuntimeMonitor(()),
        runtime=make_runtime_plan(),
        mode="force",
        requested_duration_sec=120,
        now=NOW,
    )

    assert result.outcome == "run"
    assert result.reason_code == "irrigation_force_mode"


@pytest.mark.asyncio
async def test_unknown_strategy_fails_closed() -> None:
    controller = IrrigationDecisionController()

    result = await controller.evaluate(
        zone_id=7,
        runtime_monitor=_RuntimeMonitor(()),
        runtime=make_runtime_plan(irrigation_decision={"strategy": "smart_soil_v9"}),
        mode="normal",
        requested_duration_sec=120,
        now=NOW,
    )

    assert result.outcome == "fail"
    assert result.reason_code == "irrigation_decision_strategy_unknown"
    assert result.details == {"strategy": "smart_soil_v9"}


@pytest.mark.asyncio
async def test_smart_soil_marks_invalid_day_schedule_as_degraded() -> None:
    controller = IrrigationDecisionController()
    runtime = make_runtime_plan(
        irrigation_decision={
            "strategy": "smart_soil_v1",
            "config": {"lookback_sec": 1800, "min_samples": 1, "stale_after_sec": 600, "hysteresis_pct": 0.0},
        },
        soil_moisture_target={"day": 40.0, "night": 55.0, "day_start_time": "bad", "day_hours": 16},
    )
    monitor = _RuntimeMonitor((
        {"sensor_label": "soil-1", "samples": ({"value": 30.0},)},
    ))

    result = await controller.evaluate(
        zone_id=7,
        runtime_monitor=monitor,
        runtime=runtime,
        mode="normal",
        requested_duration_sec=120,
        now=NOW,
    )

    assert result.outcome == "run"
    assert result.degraded is True
    assert result.details is not None
    assert result.details["schedule_invalid"] is True


@pytest.mark.asyncio
async def test_smart_soil_skips_when_target_missing() -> None:
    controller = IrrigationDecisionController()
    runtime = make_runtime_plan(
        irrigation_decision={
            "strategy": "smart_soil_v1",
            "config": {"lookback_sec": 1800, "min_samples": 1, "stale_after_sec": 600},
        },
        soil_moisture_target=None,
    )

    result = await controller.evaluate(
        zone_id=7,
        runtime_monitor=_RuntimeMonitor(()),
        runtime=runtime,
        mode="normal",
        requested_duration_sec=120,
        now=NOW,
    )

    assert result.outcome == "skip"
    assert result.outcome != "fail"
    assert result.reason_code == "smart_soil_target_missing"


@pytest.mark.asyncio
async def test_smart_soil_skips_when_sample_window_empty() -> None:
    controller = IrrigationDecisionController()
    runtime = make_runtime_plan(
        irrigation_decision={
            "strategy": "smart_soil_v1",
            "config": {"lookback_sec": 1800, "min_samples": 1, "stale_after_sec": 600},
        },
        soil_moisture_target={"min": 38.0, "max": 48.0, "target": 43.0},
    )

    result = await controller.evaluate(
        zone_id=7,
        runtime_monitor=_RuntimeMonitor(()),
        runtime=runtime,
        mode="normal",
        requested_duration_sec=120,
        now=NOW,
    )

    assert result.outcome == "skip"
    assert result.outcome != "fail"
    assert result.reason_code == "smart_soil_telemetry_missing_or_stale"


@pytest.mark.asyncio
async def test_task_strategy_runs_without_sensor() -> None:
    controller = IrrigationDecisionController()
    runtime = make_runtime_plan(irrigation_decision={"strategy": "task"})

    result = await controller.evaluate(
        zone_id=7,
        runtime_monitor=_RuntimeMonitor(()),
        runtime=runtime,
        mode="normal",
        requested_duration_sec=120,
        now=NOW,
    )

    assert result.outcome == "run"
    assert result.reason_code == "irrigation_task_strategy_run"


class _GateDecision:
    def __init__(self, *, outcome: str, reason_code: str, degraded: bool = False) -> None:
        self.outcome = outcome
        self.reason_code = reason_code
        self.degraded = degraded
        self.details = None


class _GateController:
    def __init__(self, decision: _GateDecision) -> None:
        self._decision = decision

    async def evaluate(self, **_kwargs):
        return self._decision


class _GateRepository:
    def __init__(self) -> None:
        self.saved: dict | None = None
        self.mark_failed_called = False

    async def update_irrigation_runtime(self, **kwargs):
        self.saved = kwargs
        return SimpleNamespace(
            id=11,
            zone_id=7,
            current_stage="decision_gate",
            workflow_phase="ready",
            topology="two_tank",
            irrigation_decision_strategy="smart_soil_v1",
            irrigation_bundle_revision=None,
        )

    async def mark_failed(self, **_kwargs):
        self.mark_failed_called = True
        raise AssertionError("mark_failed must not run for an irrigation decision skip")


def _gate_task() -> SimpleNamespace:
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


async def _run_gate(decision: _GateDecision, monkeypatch: pytest.MonkeyPatch):
    async def _noop_event(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "ae3lite.application.handlers.decision_gate.create_zone_event",
        _noop_event,
    )
    repository = _GateRepository()
    handler = DecisionGateHandler(
        runtime_monitor=object(),
        command_gateway=object(),
        task_repository=repository,
        decision_controller=_GateController(decision),
    )
    token = open_upward_capture()
    try:
        outcome = await handler.run(
            task=_gate_task(),
            plan=SimpleNamespace(runtime=make_runtime_plan(
                irrigation_decision={"strategy": "smart_soil_v1"},
            )),
            stage_def=SimpleNamespace(),
            now=NOW,
        )
        reports = drain_upward_reports()
    finally:
        close_upward_capture(token)
    return outcome, reports, repository


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason_code",
    ("smart_soil_target_missing", "smart_soil_telemetry_missing_or_stale"),
)
async def test_decision_gate_quiet_skip_completes_without_fail(
    reason_code: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome, reports, repository = await _run_gate(
        _GateDecision(outcome="skip", reason_code=reason_code),
        monkeypatch,
    )

    assert outcome.kind == "transition"
    assert outcome.kind != "fail"
    assert outcome.next_stage == "completed_skip"
    assert outcome.next_stage != "irrigation_start"
    assert repository.mark_failed_called is False
    assert repository.saved is not None
    assert repository.saved["irrigation_decision_outcome"] == "skip"
    assert repository.saved["irrigation_decision_reason_code"] == reason_code
    assert [report.code for report in reports] == []


@pytest.mark.asyncio
async def test_decision_gate_within_band_skip_keeps_info_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    outcome, reports, repository = await _run_gate(
        _GateDecision(outcome="skip", reason_code="smart_soil_within_band"),
        monkeypatch,
    )

    assert outcome.kind == "transition"
    assert outcome.next_stage == "completed_skip"
    assert repository.mark_failed_called is False
    assert [report.code for report in reports] == ["biz_irrigation_decision_skip"]
