"""Аудит: свежесть, окно кадров, курсор, уровень стока, сбой света."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from ae4.application.mutation_decision import decide_mutation
from ae4.application.water_procedures import _await_fill
from ae4.domain import light_policy as light_policy_mod
from ae4.domain.light_policy import apply_light_policy
from ae4.domain.planting import LightIntegralCursor, TelemetrySample
from ae4.domain.water_demand import (
    _fresh,
    advance_light_integral,
    count_successful_shots_in_active_span,
)
from ae4.infrastructure.shot_events import (
    load_light_integral_cursor,
    save_light_integral_cursor,
)
from common.db import fetch
from tests.unit.ae4.conftest_wave3 import level, make_phase, make_plan, make_telemetry


def test_fresh_accepts_aware_now_and_naive_sample_ts() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    sample = TelemetrySample(
        metric_type="SOIL_MOISTURE",
        channel="soil_moisture",
        value=30.0,
        ts=datetime(2026, 6, 1, 11, 59),
        unit="%",
    )
    assert _fresh(sample=sample, now=now, telemetry_max_age_sec=120) is True


def test_shots_from_previous_local_day_do_not_fill_ceiling() -> None:
    phase = make_phase(
        started_at=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
        on_time=None,
        off_time=None,
        lighting_start_time=None,
        lighting_photoperiod_hours=None,
    )
    now = datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc)
    count = count_successful_shots_in_active_span(
        shot_times=[
            datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
            datetime(2026, 6, 2, 9, 0, tzinfo=timezone.utc),
        ],
        phase=phase,
        now=now,
        timezone_name="UTC",
    )
    assert count == 1


def test_second_advance_with_same_sample_does_not_double_integral() -> None:
    started = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
    sample_ts = started + timedelta(seconds=30)
    now = started + timedelta(seconds=40)
    sample = TelemetrySample(
        metric_type="LIGHT_INTENSITY",
        channel="light",
        value=10.0,
        ts=sample_ts,
        unit="lx",
    )
    phase = make_phase(started_at=started, light_integral_unit="lx")
    cursor = LightIntegralCursor(
        accumulated=0.0,
        last_accounted_ts=started,
        unit="lx",
        status="ok",
        last_value=2.0,
    )
    first = advance_light_integral(
        cursor=cursor,
        samples=(sample,),
        now=now,
        telemetry_max_age_sec=300,
        target_unit="lx",
        phase_started_at=phase.started_at,
    )
    second = advance_light_integral(
        cursor=first,
        samples=(sample,),
        now=now,
        telemetry_max_age_sec=300,
        target_unit="lx",
        phase_started_at=phase.started_at,
    )
    assert second.accumulated == first.accumulated
    assert first.accumulated == pytest.approx(2.0 * 30)


@pytest.mark.asyncio
async def test_light_integral_cursor_roundtrip_keeps_phase_sum() -> None:
    rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, 'audit', 'UTC', $2, NOW(), NOW())
        RETURNING id
        """,
        f"gh-audit-{datetime.now(timezone.utc).timestamp()}",
        f"pt-audit-{datetime.now(timezone.utc).timestamp()}",
    )
    zone_rows = await fetch(
        """
        INSERT INTO zones (
            greenhouse_id, name, uid, status, automation_runtime, created_at, updated_at
        )
        VALUES ($1, 'audit-zone', $2, 'online', 'ae4', NOW(), NOW())
        RETURNING id
        """,
        int(rows[0]["id"]),
        f"zn-audit-{datetime.now(timezone.utc).timestamp()}",
    )
    zone_id = int(zone_rows[0]["id"])
    started = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
    cursor = LightIntegralCursor(
        accumulated=12.5,
        last_accounted_ts=started,
        unit="lx",
        status="ok",
        last_value=3.0,
    )
    await save_light_integral_cursor(zone_id=zone_id, phase_id=7, cursor=cursor)
    await save_light_integral_cursor(
        zone_id=zone_id,
        phase_id=7,
        cursor=LightIntegralCursor(
            accumulated=20.0,
            last_accounted_ts=started,
            unit="lx",
            status="ok",
            last_value=4.0,
        ),
    )
    loaded = await load_light_integral_cursor(
        zone_id=zone_id,
        phase_id=7,
        phase_started_at=started,
        unit="lx",
    )
    assert loaded.accumulated == pytest.approx(20.0)
    assert loaded.last_value == pytest.approx(4.0)
    other_phase = await load_light_integral_cursor(
        zone_id=zone_id,
        phase_id=8,
        phase_started_at=started,
        unit="lx",
    )
    assert other_phase.accumulated == 0.0


def test_stale_drain_level_blocks_shot() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    telemetry = replace(
        make_telemetry(
            now=now,
            drain_bound=True,
            drain_min=0,
            drain_max=0,
            ec_drain_value=1.0,
            soil_value=50.0,
        ),
        level_drain_max=level(
            channel="level_drain_max",
            value=None,
            bound=True,
            fresh=False,
            ts=now,
        ),
    )
    decision = decide_mutation(
        plan=_drain_plan(),
        phase=make_phase(started_at=now - timedelta(hours=4)),
        telemetry=telemetry,
        now=now,
        emergency_stop=False,
        last_shot=None,
        last_planned_shot_at=None,
        extra_used_in_half_interval=False,
        successful_shots_in_window=0,
        integral=LightIntegralCursor(0.0, now, None, "ok"),
        new_light_samples=(),
    )
    assert decision.kind is None
    assert decision.reason_code == "drain_room_level_unseen"
    assert decision.failed is False
    assert decision.create_alert is True


def test_unseen_drain_volume_still_allows_shot_when_level_not_max() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    telemetry = make_telemetry(
        now=now,
        drain_bound=True,
        drain_min=0,
        drain_max=0,
        ec_drain_value=1.0,
        soil_value=50.0,
    )
    decision = decide_mutation(
        plan=_drain_plan(pump_ml_per_sec=None),
        phase=make_phase(
            started_at=now - timedelta(hours=4),
            volume_ml=None,
        ),
        telemetry=telemetry,
        now=now,
        emergency_stop=False,
        last_shot=None,
        last_planned_shot_at=None,
        extra_used_in_half_interval=False,
        successful_shots_in_window=0,
        integral=LightIntegralCursor(0.0, now, None, "ok"),
        new_light_samples=(),
    )
    assert decision.kind == "feed_to_plants"


@pytest.mark.asyncio
async def test_fill_freshness_uses_wall_clock_not_start_time(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, datetime] = {}
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)

    async def fake_load(*, zone_id: int, now: datetime, telemetry_max_age_sec: int):
        seen["now"] = now
        snap = make_telemetry(now=datetime.now(timezone.utc), feed_max=1, feed_min=1)
        return snap

    monkeypatch.setattr(
        "ae4.application.water_procedures.load_zone_telemetry",
        fake_load,
    )
    await _await_fill(
        zone_id=1,
        plan=make_plan(),
        now=start,
        timeout_sec=30,
        min_name="level_solution_min",
        max_name="level_solution_max",
        level_reader=None,
        sleep_fn=None,
        monotonic_fn=lambda: 0.0,
    )
    assert seen["now"] > start


@pytest.mark.asyncio
async def test_light_same_action_is_not_republished(monkeypatch: pytest.MonkeyPatch) -> None:
    light_policy_mod._last_published_light_action.clear()
    calls: list[str] = []

    class Gateway:
        async def publish_and_await_done(self, **kwargs):
            calls.append(str(kwargs.get("cmd")))

            class Result:
                cmd_id = "ae4-light"
                status = "DONE"

            return Result()

    async def steps(*, plan, zone_id: int):
        step = ({"node_uid": "nd-light", "channel": "white_light", "cmd": "set_relay", "params": {"state": True}},)
        return step, step, None

    monkeypatch.setattr(light_policy_mod, "_resolve_light_steps", steps)
    plan = make_plan()
    phase = make_phase(on_time="00:00:00", off_time="23:59:00")
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    await apply_light_policy(
        plan=plan,
        phase=phase,
        gateway=Gateway(),
        task_id=1,
        zone_id=plan.zone_id,
        now=now,
        mutation_busy=False,
    )
    await apply_light_policy(
        plan=plan,
        phase=phase,
        gateway=Gateway(),
        task_id=1,
        zone_id=plan.zone_id,
        now=now,
        mutation_busy=False,
    )
    assert len(calls) == 1


def _drain_plan(pump_ml_per_sec: float | None = 10.0):
    base = make_plan().command_plans
    plans = dict(base.get("plans") or {})
    step = {
        "node_uid": "nd-1",
        "channel": "pump_main",
        "cmd": "run_pump",
        "params": {"duration_ms": 1000},
    }
    plans["feed_to_drain_start"] = [step]
    plans["feed_to_drain_stop"] = [dict(step, cmd="set_relay", params={"state": False})]
    return make_plan(command_plans={"plans": plans}, pump_main_ml_per_sec=pump_ml_per_sec)
