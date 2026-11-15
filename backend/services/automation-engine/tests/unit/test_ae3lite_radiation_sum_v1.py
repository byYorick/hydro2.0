"""radiation_sum_v1: сумма PAR, окно теплицы, лимиты и отказы конфига."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from _test_support_runtime_plan import make_runtime_plan, make_runtime_plan_dict
from ae3lite.application.handlers.decision_gate import DecisionGateHandler
from ae3lite.application.services.dry_run_guard import guard_pump_start
from ae3lite.config.loader import load_runtime_plan
from ae3lite.config.runtime_plan_irrigation import _build_irrigation_decision
from ae3lite.config.schema.runtime_plan import RadiationSumConfig
from ae3lite.domain.errors import CommandPublishError
from ae3lite.domain.services.irrigation_decision_controller import IrrigationDecisionController
from ae3lite.domain.services.radiation_sum import (
    ALERT_DAILY_CAP,
    ALERT_SENSOR_SILENT,
    REASON_BELOW,
    REASON_CONFIG,
    REASON_DAILY_CAP,
    REASON_FALLBACK,
    REASON_FALLBACK_WAIT,
    REASON_LUX,
    REASON_MAX_INTERVAL,
    REASON_MIN_INTERVAL,
    REASON_NIGHT,
    REASON_THRESHOLD,
    REASON_WINDOW,
)
from ae3lite.hydraulics.failure_report import close_upward_capture, drain_upward_reports, open_upward_capture
from ae3lite.infrastructure.read_models.radiation_sum_ledger import IRRIGATION_PULSE_SQL
from pydantic import ValidationError

TZ = ZoneInfo("Europe/Simferopol")
DAY = datetime(2026, 6, 16, 7, 0, tzinfo=timezone.utc)  # 10:00 по Симферополю


def _local(hour: int, minute: int = 0, second: int = 0, day: int = 16) -> datetime:
    return datetime(2026, 6, day, hour, minute, second, tzinfo=TZ).astimezone(timezone.utc)


def _config(**overrides: object) -> dict:
    payload = {
        "threshold_par_mol_m2": 1.3,
        "crop": "strawberry",
        "max_interval_sec": 5400,
        "fallback_interval_sec": 2700,
        "max_daily_volume_l": 50.0,
        "pulse_ml_per_plant": 35.0,
        "plant_count": 10,
        "min_interval_sec": 1200,
    }
    payload.update(overrides)
    return payload


def _runtime(config: dict | None = None, *, start: str = "08:00", hours: float | None = 12, tz: str = "Europe/Simferopol"):
    payload = make_runtime_plan_dict()
    payload["irrigation_decision"] = {
        "strategy": "radiation_sum_v1",
        "config": _config(**(config or {})),
    }
    payload["day_night_config"] = {
        "enabled": True,
        "lighting": {"day_start_time": start, "day_hours": hours, "timezone": tz},
        "ph": payload["day_night_config"]["ph"],
        "ec": payload["day_night_config"]["ec"],
    }
    return load_runtime_plan(payload)


def _series(start: datetime, end: datetime, ppfd: float, step: int = 60) -> list[dict]:
    points = []
    moment = start
    while moment <= end:
        points.append({"ts": moment, "value": ppfd})
        moment += timedelta(seconds=step)
    if not points or points[-1]["ts"] != end:
        points.append({"ts": end, "value": ppfd})
    return points


class _Monitor:
    def __init__(self, par: list[dict], lux: list[dict] | None = None, pulses: list[dict] | None = None) -> None:
        self.par = par
        self.lux = lux or []
        self.pulses = pulses or []

    async def read_channel_samples(self, *, label: str, **_kwargs):
        if label == "light":
            return {"samples": self.lux}
        return {"samples": self.par}

    async def read_irrigation_pulses(self, *, zone_id: int):
        assert zone_id == 7
        return list(self.pulses)


async def _eval(runtime, monitor, now: datetime):
    return await IrrigationDecisionController().evaluate(
        zone_id=7,
        runtime_monitor=monitor,
        runtime=runtime,
        mode="normal",
        requested_duration_sec=90,
        now=now,
    )


def _pulse(moment: datetime, liters: float = 0.35) -> dict:
    return {"finished_at": moment, "liters": liters}


@pytest.fixture(autouse=True)
def _simferopol_is_utc_plus_3() -> None:
    moment = datetime(2026, 6, 15, 21, 0, tzinfo=timezone.utc).astimezone(TZ)
    assert moment.hour == 0
    assert moment.utcoffset() == timedelta(hours=3)


@pytest.mark.asyncio
async def test_threshold_run_and_min_interval_blocks_even_when_sum_is_enough() -> None:
    now = _local(10, 0)
    start = now - timedelta(minutes=25)
    high = _series(start, now, 2000)
    runtime = _runtime()
    reached = await _eval(runtime, _Monitor(high, pulses=[_pulse(start)]), now)
    assert reached.outcome == "run"
    assert reached.reason_code == REASON_THRESHOLD
    assert reached.details["sum_par_mol_m2"] >= 1.3

    recent = now - timedelta(minutes=10)
    blocked = await _eval(runtime, _Monitor(_series(recent, now, 4000), pulses=[_pulse(recent)]), now)
    assert blocked.outcome == "skip"
    assert blocked.reason_code == REASON_MIN_INTERVAL


@pytest.mark.asyncio
async def test_max_interval_pulses_when_sum_stays_below_threshold() -> None:
    now = _local(12, 0)
    start = now - timedelta(minutes=91)
    low = _series(start, now, 30)
    decision = await _eval(_runtime(), _Monitor(low, pulses=[_pulse(start)]), now)
    assert decision.outcome == "run"
    assert decision.reason_code == REASON_MAX_INTERVAL
    assert decision.details["sum_par_mol_m2"] < 1.3


@pytest.mark.asyncio
async def test_outside_window_is_silent_including_edges_and_simferopol_midnight() -> None:
    runtime = _runtime(start="22:00", hours=4)
    before = _local(21, 59, day=15)
    start_edge = _local(22, 0, day=15)
    midnight = _local(0, 0, day=16)
    before_end = _local(1, 59, 30, day=16)
    end_edge = _local(2, 0, day=16)
    bright_from_open = _series(_local(22, 0, day=15), midnight, 1400)

    night = await _eval(runtime, _Monitor([]), before)
    assert night.outcome == "skip" and night.reason_code == REASON_NIGHT

    opened = await _eval(runtime, _Monitor(bright_from_open), start_edge)
    assert opened.outcome == "skip"
    assert opened.reason_code == REASON_MIN_INTERVAL

    # 21:00 UTC — полночь в Симферополе и всё ещё внутри 22:00–02:00.
    # Тот же час в UTC был бы снаружи окна 22:00–02:00.
    assert midnight.astimezone(timezone.utc).hour == 21
    inside = await _eval(runtime, _Monitor(bright_from_open), midnight)
    assert inside.outcome == "run"
    assert inside.reason_code == REASON_THRESHOLD

    still_inside = await _eval(
        runtime,
        _Monitor(_series(_local(22, 0, day=15), before_end, 1400)),
        before_end,
    )
    assert still_inside.reason_code != REASON_NIGHT

    closed = await _eval(runtime, _Monitor(bright_from_open), end_edge)
    assert closed.outcome == "skip" and closed.reason_code == REASON_NIGHT


@pytest.mark.asyncio
async def test_gap_longer_than_dli_stale_is_not_interpolated() -> None:
    now = _local(12, 0)
    early = _series(now - timedelta(minutes=40), now - timedelta(minutes=30), 2000)
    late = _series(now - timedelta(minutes=5), now, 2000)
    assert (late[0]["ts"] - early[-1]["ts"]).total_seconds() > 600
    decision = await _eval(
        _runtime(),
        _Monitor(early + late, pulses=[_pulse(now - timedelta(minutes=50))]),
        now,
    )
    assert decision.reason_code == REASON_FALLBACK
    assert decision.details["sum_par_mol_m2"] is None
    assert decision.outcome == "degraded_run"


@pytest.mark.asyncio
async def test_daily_pulse_and_liter_caps_survive_a_new_strategy_instance() -> None:
    now = _local(15, 0)
    par = _series(now - timedelta(minutes=30), now, 2000)
    today = [_pulse(now - timedelta(minutes=40 + index), 0.01) for index in range(30)]
    yesterday = _pulse(_local(23, 0, day=15), 5.0)
    monitor = _Monitor(par, pulses=[yesterday, *today])
    first = await _eval(_runtime(), monitor, now)
    second = await _eval(_runtime(), monitor, now)
    assert first.outcome == "skip" and first.reason_code == REASON_DAILY_CAP
    assert second.outcome == "skip" and second.reason_code == REASON_DAILY_CAP
    assert first.details["daily_pulses"] == 30

    under_count = [_pulse(now - timedelta(hours=5), 0.4), _pulse(now - timedelta(hours=4), 0.4)]
    liters = await _eval(_runtime({"max_daily_volume_l": 1.0}), _Monitor(par, pulses=under_count), now)
    assert liters.reason_code == REASON_DAILY_CAP
    assert liters.details["daily_liters"] == pytest.approx(0.8)

    only_yesterday = await _eval(_runtime(), _Monitor(par, pulses=[yesterday]), now)
    assert only_yesterday.reason_code == REASON_THRESHOLD


@pytest.mark.asyncio
async def test_stale_par_zero_par_lux_proxy_and_recovery() -> None:
    now = _local(11, 0)
    last = _pulse(now - timedelta(minutes=50))
    silent = _series(now - timedelta(minutes=70), now - timedelta(minutes=11), 1500)
    decision = await _eval(_runtime(), _Monitor(silent, pulses=[last]), now)
    assert decision.outcome == "degraded_run"
    assert decision.reason_code == REASON_FALLBACK
    assert decision.details["raise_alerts"][0]["code"] == ALERT_SENSOR_SILENT

    zeros = _series(now - timedelta(minutes=50), now, 0)
    zero_decision = await _eval(_runtime(), _Monitor(zeros, pulses=[last]), now)
    assert zero_decision.reason_code == REASON_FALLBACK
    assert zero_decision.details["raise_alerts"][0]["code"] == ALERT_SENSOR_SILENT

    waiting = await _eval(
        _runtime(),
        _Monitor(silent, pulses=[_pulse(now - timedelta(minutes=30))]),
        now,
    )
    assert waiting.reason_code == REASON_FALLBACK_WAIT
    assert waiting.outcome == "skip"

    lux = _series(now - timedelta(minutes=30), now, 80_000)
    proxy = await _eval(
        _runtime(),
        _Monitor(silent, lux=lux, pulses=[_pulse(now - timedelta(minutes=30))]),
        now,
    )
    assert proxy.outcome == "degraded_run"
    assert proxy.reason_code == REASON_LUX
    assert proxy.details["approx"] is True
    assert proxy.details["raise_alerts"][0]["code"] == ALERT_SENSOR_SILENT

    fresh = _series(now - timedelta(minutes=25), now, 100)
    recovered = await _eval(_runtime(), _Monitor(fresh, pulses=[_pulse(now - timedelta(minutes=25))]), now)
    assert recovered.outcome == "skip"
    assert recovered.reason_code == REASON_BELOW
    codes = [item["code"] for item in recovered.details["resolve_alerts"]]
    assert ALERT_SENSOR_SILENT in codes
    assert ALERT_DAILY_CAP in codes


@pytest.mark.asyncio
async def test_missing_window_and_invalid_config_do_not_start_irrigation() -> None:
    payload = make_runtime_plan_dict()
    payload["irrigation_decision"] = {"strategy": "radiation_sum_v1", "config": _config()}
    payload["day_night_config"]["lighting"]["day_start_time"] = None
    payload["day_night_config"]["lighting"]["day_hours"] = None
    payload["day_night_config"]["lighting"]["timezone"] = "Europe/Simferopol"
    runtime = load_runtime_plan(payload)
    decision = await _eval(runtime, _Monitor([]), DAY)
    assert decision.outcome == "fail"
    assert decision.reason_code == REASON_WINDOW

    broken = make_runtime_plan_dict()
    broken["irrigation_decision"] = {
        "strategy": "radiation_sum_v1",
        "config": _config(),
        "config_error": "threshold rejected",
    }
    broken_runtime = load_runtime_plan(broken)
    failed = await _eval(broken_runtime, _Monitor([]), DAY)
    assert failed.outcome == "fail"
    assert failed.reason_code == REASON_CONFIG


def test_config_validation_rejects_without_clamping() -> None:
    with pytest.raises(ValidationError):
        RadiationSumConfig.model_validate(_config(threshold_par_mol_m2=1.0))
    with pytest.raises(ValidationError):
        RadiationSumConfig.model_validate(_config(crop="lettuce", threshold_par_mol_m2=1.3))
    with pytest.raises(ValidationError):
        RadiationSumConfig.model_validate(_config(min_interval_sec=1199))
    with pytest.raises(ValidationError):
        RadiationSumConfig.model_validate(_config(min_interval_sec=5400, max_interval_sec=5400))
    with pytest.raises(ValidationError):
        RadiationSumConfig.model_validate(_config(fallback_interval_sec=2699))
    with pytest.raises(ValidationError):
        RadiationSumConfig.model_validate(_config(fallback_interval_sec=3601))
    for missing in ("threshold_par_mol_m2", "max_interval_sec", "fallback_interval_sec", "max_daily_volume_l"):
        payload = _config()
        payload.pop(missing)
        with pytest.raises(ValidationError):
            RadiationSumConfig.model_validate(payload)
    accepted = RadiationSumConfig.model_validate(_config(crop="lettuce", threshold_par_mol_m2=1.0, max_interval_sec=3600))
    assert accepted.threshold_par_mol_m2 == 1.0
    assert accepted.max_interval_sec == 3600

    snapshot = SimpleNamespace(
        targets={
            "extensions": {
                "subsystems": {
                    "irrigation": {
                        "decision": {
                            "strategy": "radiation_sum_v1",
                            "config": _config(threshold_par_mol_m2=1.0),
                        }
                    }
                }
            }
        }
    )
    built = _build_irrigation_decision(snapshot)
    assert built["config_error"]
    assert built["config"]["threshold_par_mol_m2"] == 1.3
    assert "1.0" not in str(built["config"]["threshold_par_mol_m2"])


def test_pulse_sql_counts_done_commands_for_completed_runs() -> None:
    assert "c.status = 'DONE'" in IRRIGATION_PULSE_SQL or "c.status IS NULL OR c.status = 'DONE'" in IRRIGATION_PULSE_SQL
    assert "ac.terminal_status = 'DONE'" in IRRIGATION_PULSE_SQL
    assert "completed_run" in IRRIGATION_PULSE_SQL
    assert "irrigation_start" in IRRIGATION_PULSE_SQL


@pytest.mark.asyncio
async def test_hot_stop_overrides_radiation_pulse(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr("ae3lite.application.handlers.decision_gate.create_zone_event", _noop)
    now = _local(11, 0)
    par = _series(now - timedelta(minutes=30), now, 2000)
    monitor = _Monitor(par, pulses=[_pulse(now - timedelta(minutes=30))])

    async def read_solution_temp_window(**_kwargs):
        start = now - timedelta(seconds=600)
        return {
            "samples": (
                {"ts": start, "value": 33.0},
                {"ts": start + timedelta(seconds=300), "value": 33.0},
                {"ts": now, "value": 33.0},
            )
        }

    monitor.read_solution_temp_window = read_solution_temp_window  # type: ignore[attr-defined]
    from ae3lite.config.schema.runtime_plan import SolutionHealth

    health = SolutionHealth(required=True, min_c=18.0, max_c=24.0, warn_c=26.0, stop_c=32.0, breach_hold_sec=600)
    runtime = _runtime().model_copy(update={"solution_health": health})

    class _Repo:
        def __init__(self) -> None:
            self.saved: list[dict] = []

        async def list_completed_irrigation_decisions(self, **_kwargs):
            return []

        async def update_irrigation_runtime(self, **kwargs):
            self.saved.append(kwargs)
            return SimpleNamespace(id=11, zone_id=7, current_stage="decision_gate", workflow_phase="ready", topology="two_tank")

    repository = _Repo()
    handler = DecisionGateHandler(
        runtime_monitor=monitor,
        command_gateway=object(),
        task_repository=repository,
        decision_controller=IrrigationDecisionController(),
    )
    outcome = await handler.run(
        task=SimpleNamespace(
            id=11,
            zone_id=7,
            claimed_by="worker",
            irrigation_mode="normal",
            irrigation_requested_duration_sec=90,
            topology="two_tank",
            claim_generation=1,
            current_stage="decision_gate",
            workflow_phase="ready",
        ),
        plan=SimpleNamespace(runtime=runtime),
        stage_def=SimpleNamespace(),
        now=now,
    )
    assert outcome.kind == "transition"
    assert outcome.next_stage == "completed_skip"
    assert repository.saved[0]["irrigation_decision_reason_code"] == "solution_temp_hot_stop"


@pytest.mark.asyncio
async def test_dry_run_blocks_pump_after_radiation_would_run(monkeypatch: pytest.MonkeyPatch) -> None:
    now = _local(11, 0)
    decision = await _eval(
        _runtime(),
        _Monitor(_series(now - timedelta(minutes=30), now, 2000), pulses=[_pulse(now - timedelta(minutes=30))]),
        now,
    )
    assert decision.outcome == "run"

    async def unsafe(*_args, **_kwargs):
        return False, "dry_run"

    monkeypatch.setattr("common.pump_safety.check_dry_run", unsafe)
    with pytest.raises(CommandPublishError):
        await guard_pump_start(
            zone_id=7,
            cmd="run_pump",
            channel="pump_main",
            params={"duration_ms": 1000},
            stage="irrigation_start",
        )


@pytest.mark.asyncio
async def test_gate_raises_cap_alarm_and_resolves_sensor_alarm(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr("ae3lite.application.handlers.decision_gate.create_zone_event", _noop)
    now = _local(15, 0)
    par = _series(now - timedelta(minutes=30), now, 2000)
    pulses = [_pulse(now - timedelta(minutes=40 + index), 0.01) for index in range(30)]

    class _Repo:
        async def update_irrigation_runtime(self, **_kwargs):
            return SimpleNamespace(id=11, zone_id=7, current_stage="decision_gate", workflow_phase="ready", topology="two_tank")

        async def list_completed_irrigation_decisions(self, **_kwargs):
            return []

    handler = DecisionGateHandler(
        runtime_monitor=_Monitor(par, pulses=pulses),
        command_gateway=object(),
        task_repository=_Repo(),
        decision_controller=IrrigationDecisionController(),
    )
    task = SimpleNamespace(
        id=11,
        zone_id=7,
        claimed_by="worker",
        irrigation_mode="normal",
        irrigation_requested_duration_sec=90,
        topology="two_tank",
        claim_generation=1,
        current_stage="decision_gate",
        workflow_phase="ready",
        irrigation_decision_outcome=None,
        irrigation_decision_reason_code=None,
    )
    token = open_upward_capture()
    try:
        outcome = await handler.run(task=task, plan=SimpleNamespace(runtime=_runtime()), stage_def=SimpleNamespace(), now=now)
        reports = drain_upward_reports()
    finally:
        close_upward_capture(token)
    assert outcome.next_stage == "completed_skip"
    assert any(report.code == ALERT_DAILY_CAP and report.status == "ACTIVE" for report in reports)
    assert all(report.code != "biz_irrigation_decision_skip" for report in reports)

    fresh = _series(now - timedelta(minutes=25), now, 100)
    handler._runtime_monitor = _Monitor(fresh, pulses=[_pulse(now - timedelta(minutes=25))])
    token = open_upward_capture()
    try:
        await handler.run(task=task, plan=SimpleNamespace(runtime=_runtime()), stage_def=SimpleNamespace(), now=now)
        recovered = drain_upward_reports()
    finally:
        close_upward_capture(token)
    assert any(report.code == ALERT_SENSOR_SILENT and report.status == "RESOLVED" for report in recovered)
