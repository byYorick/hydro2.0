"""Исполнение кадра полива, импульса коррекции, смены фазы и срывов без зависания."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from ae4.application.dose_pulse import run_dose_pulse
from ae4.application.mutation_decision import decide_mutation
from ae4.application.water_procedures import run_feed_to_plants, run_supply_to_clean
from ae4.domain.planting import LightIntegralCursor, apply_phase_change
from ae4.infrastructure.zone_telemetry import LevelReading
from common.history_logger_gateway import (
    CommandNotDoneError,
    GatewayPublishResult,
    HistoryLoggerGateway,
)
from tests.unit.ae4.conftest_wave3 import level, make_phase, make_plan, make_planting, make_telemetry
from tests.unit.ae4.conftest_wave4 import make_dose_plan


class _Commands:
    def __init__(self) -> None:
        self.step = 0

    async def get_next_step_no(self, *, task_id: int) -> int:
        self.step += 1
        return self.step

    async def create_pending(self, **kwargs: Any) -> int:
        return int(kwargs["step_no"])

    async def mark_accepted(self, **kwargs: Any) -> None:
        return None

    async def mark_terminal(self, **kwargs: Any) -> None:
        return None


class _Gateway(HistoryLoggerGateway):
    def __init__(self, *, fail: tuple[str, str] | None = None) -> None:
        super().__init__(metrics_prefix="ae4_exec_fault_test")
        self.calls: list[dict[str, Any]] = []
        self.fail = fail
        self.fail_status = "ERROR"

    async def publish_and_await_done(self, **kwargs: Any) -> GatewayPublishResult:
        self.calls.append(dict(kwargs))
        if self.fail == (str(kwargs["channel"]), str(kwargs["cmd"])):
            raise CommandNotDoneError(
                cmd_id=str(kwargs["cmd_id"]),
                status=self.fail_status,
                message=f"terminal {self.fail_status}",
            )
        return GatewayPublishResult(
            cmd_id=str(kwargs["cmd_id"]),
            legacy_command_id=f"legacy-{kwargs['cmd_id']}",
            status="DONE",
        )


def _now() -> datetime:
    return datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _channels(gateway: _Gateway) -> list[tuple[str, str]]:
    return [(str(call["channel"]), str(call["cmd"])) for call in gateway.calls]


async def _no_shot(**kwargs: Any) -> None:
    return None


async def _no_dose_mark(**kwargs: Any) -> None:
    return None


@pytest.mark.asyncio
async def test_irrigation_frame_opens_valves_then_pump_then_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[dict[str, Any]] = []

    async def _capture(**kwargs: Any) -> None:
        recorded.append(kwargs)

    monkeypatch.setattr(
        "ae4.application.water_procedures.record_successful_shot",
        _capture,
    )
    gateway = _Gateway()
    plan = make_plan()
    await run_feed_to_plants(
        plan=plan,
        gateway=gateway,
        command_repository=_Commands(),  # type: ignore[arg-type]
        task_id=7,
        zone_id=1,
        now=_now(),
        duration_sec=2,
        shot_kind="planned",
        reason_code="planned_interval",
        grow_cycle_id=10,
        phase_id=1,
    )
    assert _channels(gateway) == [
        ("valve_solution_supply", "set_relay"),
        ("valve_irrigation", "set_relay"),
        ("pump_main", "run_pump"),
        ("pump_main", "set_relay"),
        ("valve_irrigation", "set_relay"),
        ("valve_solution_supply", "set_relay"),
    ]
    pump = gateway.calls[2]
    assert pump["params"]["duration_ms"] == 2000
    assert recorded[0]["kind"] == "planned"
    assert recorded[0]["duration_sec"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["ERROR", "TIMEOUT", "BUSY"])
async def test_irrigation_not_done_still_closes_valves(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    monkeypatch.setattr(
        "ae4.application.water_procedures.record_successful_shot",
        _no_shot,
    )
    gateway = _Gateway(fail=("pump_main", "run_pump"))
    gateway.fail_status = status
    with pytest.raises(CommandNotDoneError):
        await run_feed_to_plants(
            plan=make_plan(),
            gateway=gateway,
            command_repository=_Commands(),  # type: ignore[arg-type]
            task_id=8,
            zone_id=1,
            now=_now(),
            duration_sec=2,
            shot_kind="planned",
            reason_code="planned_interval",
            grow_cycle_id=10,
            phase_id=1,
        )
    assert ("pump_main", "set_relay") in _channels(gateway)
    assert ("valve_irrigation", "set_relay") in _channels(gateway)
    assert ("valve_solution_supply", "set_relay") in _channels(gateway)


@pytest.mark.asyncio
async def test_correction_pulse_is_sensor_mode_then_dose_ml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ae4.application.dose_pulse.mark_dose_done", _no_dose_mark)
    plans = dict(make_plan().command_plans["plans"])
    plans["sensor_mode_activate"] = [
        {
            "node_uid": "nd-ec",
            "channel": "system",
            "cmd": "activate_sensor_mode",
            "params": {},
        }
    ]
    plans["sensor_mode_deactivate"] = [
        {
            "node_uid": "nd-ec",
            "channel": "system",
            "cmd": "deactivate_sensor_mode",
            "params": {},
        }
    ]
    plan = make_plan(command_plans={"plans": plans}, dose=make_dose_plan())
    gateway = _Gateway()
    await run_dose_pulse(
        plan=plan,
        gateway=gateway,
        command_repository=_Commands(),  # type: ignore[arg-type]
        task_id=9,
        zone_id=1,
        now=_now(),
        reagent="nutrition",
        dose_ml=1.5,
        baseline_value=1.2,
    )
    assert _channels(gateway) == [
        ("system", "activate_sensor_mode"),
        ("pump_a", "dose"),
        ("system", "deactivate_sensor_mode"),
    ]
    assert gateway.calls[1]["params"] == {"ml": 1.5}
    assert "duration_ms" not in gateway.calls[1]["params"]


@pytest.mark.asyncio
async def test_correction_dose_error_does_not_count_as_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marked = {"n": 0}

    async def _mark(**kwargs: Any) -> None:
        marked["n"] += 1

    monkeypatch.setattr("ae4.application.dose_pulse.mark_dose_done", _mark)
    plans = dict(make_plan().command_plans["plans"])
    plans["sensor_mode_activate"] = [
        {
            "node_uid": "nd-ec",
            "channel": "system",
            "cmd": "activate_sensor_mode",
            "params": {},
        }
    ]
    plans["sensor_mode_deactivate"] = [
        {
            "node_uid": "nd-ec",
            "channel": "system",
            "cmd": "deactivate_sensor_mode",
            "params": {},
        }
    ]
    plan = make_plan(command_plans={"plans": plans}, dose=make_dose_plan())
    gateway = _Gateway(fail=("pump_a", "dose"))
    with pytest.raises(CommandNotDoneError):
        await run_dose_pulse(
            plan=plan,
            gateway=gateway,
            command_repository=_Commands(),  # type: ignore[arg-type]
            task_id=10,
            zone_id=1,
            now=_now(),
            reagent="nutrition",
            dose_ml=1.5,
            baseline_value=1.2,
        )
    assert marked["n"] == 0
    assert ("system", "deactivate_sensor_mode") in _channels(gateway)


def test_phase_change_next_shot_uses_new_interval_and_duration() -> None:
    now = _now()
    state = make_planting(
        started_at=now - timedelta(hours=5),
        interval_sec=100_000,
        duration_sec=90,
    )
    new_phase = make_phase(
        phase_id=2,
        started_at=now - timedelta(hours=1),
        interval_sec=60,
        duration_sec=12,
    )
    new_state, integral = apply_phase_change(
        state=state,
        new_phase=new_phase,
        integral=LightIntegralCursor(
            accumulated=400.0,
            last_accounted_ts=state.phase.started_at,
            unit=None,
            status="ok",
        ),
    )
    decision = decide_mutation(
        plan=make_plan(),
        phase=new_state.phase,
        telemetry=make_telemetry(feed_min=1, clean_min=1, soil_value=50.0, now=now),
        now=now,
        emergency_stop=False,
        last_shot=None,
        last_planned_shot_at=now - timedelta(seconds=120),
        extra_used_in_half_interval=False,
        successful_shots_in_window=0,
        integral=integral,
        new_light_samples=(),
    )
    assert decision.kind == "feed_to_plants"
    assert decision.duration_sec == 12
    assert new_state.phase.interval_sec == 60
    assert integral.accumulated == 0.0


def _reading(*, value: int, fresh: bool = True) -> LevelReading:
    return level(
        channel="level",
        value=value,
        bound=True,
        fresh=fresh,
        ts=_now(),
    )


@pytest.mark.asyncio
async def test_clean_fill_timeout_stops_valve_without_spinning() -> None:
    clock = {"t": 0.0}
    sleeps: list[float] = []

    def monotonic() -> float:
        return clock["t"]

    async def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        clock["t"] += seconds

    async def reader() -> tuple[LevelReading, LevelReading]:
        return _reading(value=1), _reading(value=0)

    gateway = _Gateway()
    plan = make_plan(clean_fill_timeout_sec=2)
    await run_supply_to_clean(
        plan=plan,
        gateway=gateway,
        command_repository=_Commands(),  # type: ignore[arg-type]
        task_id=11,
        zone_id=1,
        now=_now(),
        level_reader=reader,
        sleep_fn=sleeper,
        monotonic_fn=monotonic,
    )
    assert len(sleeps) <= 8
    assert _channels(gateway)[0] == ("valve_clean_fill", "set_relay")
    assert gateway.calls[0]["params"]["state"] is True
    assert _channels(gateway)[-1] == ("valve_clean_fill", "set_relay")
    assert gateway.calls[-1]["params"]["state"] is False


@pytest.mark.asyncio
async def test_clean_fill_leak_stops_valve_and_raises() -> None:
    samples = [
        (_reading(value=1), _reading(value=0)),
        (_reading(value=0), _reading(value=0)),
    ]

    async def reader() -> tuple[LevelReading, LevelReading]:
        return samples.pop(0)

    async def sleeper(seconds: float) -> None:
        return None

    gateway = _Gateway()
    with pytest.raises(RuntimeError, match="Утечка"):
        await run_supply_to_clean(
            plan=make_plan(clean_fill_timeout_sec=30),
            gateway=gateway,
            command_repository=_Commands(),  # type: ignore[arg-type]
            task_id=12,
            zone_id=1,
            now=_now(),
            level_reader=reader,
            sleep_fn=sleeper,
            monotonic_fn=lambda: 0.0,
        )
    assert gateway.calls[-1]["params"]["state"] is False


@pytest.mark.asyncio
async def test_clean_fill_stale_level_stops_valve_and_raises() -> None:
    async def reader() -> tuple[LevelReading, LevelReading]:
        return _reading(value=1, fresh=False), _reading(value=0)

    gateway = _Gateway()
    with pytest.raises(RuntimeError, match="протухла"):
        await run_supply_to_clean(
            plan=make_plan(clean_fill_timeout_sec=30),
            gateway=gateway,
            command_repository=_Commands(),  # type: ignore[arg-type]
            task_id=13,
            zone_id=1,
            now=_now(),
            level_reader=reader,
            sleep_fn=lambda _seconds: _async_none(),
            monotonic_fn=lambda: 0.0,
        )
    assert gateway.calls[-1]["channel"] == "valve_clean_fill"
    assert gateway.calls[-1]["params"]["state"] is False


async def _async_none() -> None:
    return None
