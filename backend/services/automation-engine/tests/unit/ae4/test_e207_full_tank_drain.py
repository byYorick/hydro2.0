"""Полный бак + EC выше коридора: слив доли или пауза; failed не ставится."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ae4.application.mutation_decision import decide_mutation
from ae4.domain.planting import LightIntegralCursor
from tests.unit.ae4.conftest_wave3 import make_phase, make_plan, make_telemetry
from tests.unit.ae4.conftest_wave4 import make_dose_plan


def _drain_plans() -> dict[str, Any]:
    base = make_plan().command_plans
    plans = dict(base.get("plans") or base)
    plans["feed_to_drain_start"] = [
        {
            "node_uid": "nd-1",
            "channel": "valve_drain",
            "cmd": "set_relay",
            "params": {"state": True},
        },
        {
            "node_uid": "nd-1",
            "channel": "pump_main",
            "cmd": "run_pump",
            "params": {"duration_ms": 1000},
        },
    ]
    plans["feed_to_drain_stop"] = [
        {
            "node_uid": "nd-1",
            "channel": "pump_main",
            "cmd": "set_relay",
            "params": {"state": False},
        },
        {
            "node_uid": "nd-1",
            "channel": "valve_drain",
            "cmd": "set_relay",
            "params": {"state": False},
        },
    ]
    return {"plans": plans}


def _decide(
    *,
    feed_max: int,
    with_circuit: bool,
    ec_value: float = 2.5,
    ec_clean: float | None = 0.2,
):
    now = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    plan = make_plan(
        dose=make_dose_plan(),
        command_plans=_drain_plans() if with_circuit else make_plan().command_plans,
        ec_clean=ec_clean,
        nutrient_solution_volume_l=50.0,
        pump_main_ml_per_sec=10.0,
    )
    phase = make_phase(
        started_at=now.replace(hour=8),
        ec_target=1.4,
        ec_max=1.8,
        ec_unit="mS/cm",
    )
    telemetry = make_telemetry(
        feed_min=1,
        feed_max=feed_max,
        clean_min=1,
        soil_value=50.0,
        ec_value=ec_value,
        now=now,
        drain_bound=with_circuit,
        drain_min=1,
        drain_max=0,
        ec_drain_value=0.5 if with_circuit else None,
    )
    return decide_mutation(
        plan=plan,
        phase=phase,
        telemetry=telemetry,
        now=now,
        emergency_stop=False,
        last_shot=None,
        last_planned_shot_at=phase.started_at,
        extra_used_in_half_interval=False,
        successful_shots_in_window=0,
        integral=LightIntegralCursor(
            accumulated=0.0,
            last_accounted_ts=phase.started_at,
            unit=None,
            status="ok",
        ),
        new_light_samples=(),
    )


def test_full_tank_ec_high_with_circuit_drains_portion_no_frame_no_failed() -> None:
    decision = _decide(feed_max=1, with_circuit=True)
    assert decision.kind == "feed_to_drain"
    assert decision.failed is False
    assert decision.create_task is True
    assert decision.drain_volume_l is not None and decision.drain_volume_l > 0
    assert decision.drain_duration_ms is not None and decision.drain_duration_ms > 0
    assert decision.reagent is None


def test_full_tank_ec_high_without_circuit_pause_alert_no_failed() -> None:
    decision = _decide(feed_max=1, with_circuit=False)
    assert decision.kind is None
    assert decision.reason_code == "ec_high_tank_full_await_drain"
    assert decision.failed is False
    assert decision.create_alert is True
    assert decision.create_task is False
