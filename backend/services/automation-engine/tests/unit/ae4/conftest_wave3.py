"""Общие фикстуры тика волны 3 AE4."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ae4.config.zone_plan import ZonePlan
from ae4.domain.planting import PhaseTargets, PlantingState
from ae4.infrastructure.zone_telemetry import LevelReading, ZoneTelemetrySnapshot


def make_plan(**kwargs: Any) -> ZonePlan:
    plans = kwargs.pop(
        "command_plans",
        {
            "plans": {
                "irrigation_start": [
                    {
                        "node_uid": "nd-1",
                        "channel": "valve_solution_supply",
                        "cmd": "set_relay",
                        "params": {"state": True},
                    },
                    {
                        "node_uid": "nd-1",
                        "channel": "valve_irrigation",
                        "cmd": "set_relay",
                        "params": {"state": True},
                    },
                    {
                        "node_uid": "nd-1",
                        "channel": "pump_main",
                        "cmd": "run_pump",
                        "params": {"duration_ms": 60000},
                    },
                ],
                "irrigation_stop": [
                    {
                        "node_uid": "nd-1",
                        "channel": "pump_main",
                        "cmd": "set_relay",
                        "params": {"state": False},
                    },
                    {
                        "node_uid": "nd-1",
                        "channel": "valve_irrigation",
                        "cmd": "set_relay",
                        "params": {"state": False},
                    },
                    {
                        "node_uid": "nd-1",
                        "channel": "valve_solution_supply",
                        "cmd": "set_relay",
                        "params": {"state": False},
                    },
                ],
                "clean_fill_start": [
                    {
                        "node_uid": "nd-1",
                        "channel": "valve_clean_fill",
                        "cmd": "set_relay",
                        "params": {"state": True},
                    }
                ],
                "clean_fill_stop": [
                    {
                        "node_uid": "nd-1",
                        "channel": "valve_clean_fill",
                        "cmd": "set_relay",
                        "params": {"state": False},
                    }
                ],
                "solution_fill_start": [
                    {
                        "node_uid": "nd-1",
                        "channel": "valve_clean_supply",
                        "cmd": "set_relay",
                        "params": {"state": True},
                    },
                    {
                        "node_uid": "nd-1",
                        "channel": "valve_solution_fill",
                        "cmd": "set_relay",
                        "params": {"state": True},
                    },
                    {
                        "node_uid": "nd-1",
                        "channel": "pump_main",
                        "cmd": "set_relay",
                        "params": {"state": True},
                    },
                ],
                "solution_fill_stop": [
                    {
                        "node_uid": "nd-1",
                        "channel": "pump_main",
                        "cmd": "set_relay",
                        "params": {"state": False},
                    },
                    {
                        "node_uid": "nd-1",
                        "channel": "valve_solution_fill",
                        "cmd": "set_relay",
                        "params": {"state": False},
                    },
                    {
                        "node_uid": "nd-1",
                        "channel": "valve_clean_supply",
                        "cmd": "set_relay",
                        "params": {"state": False},
                    },
                ],
            }
        },
    )
    defaults: dict[str, Any] = {
        "zone_id": 1,
        "grow_cycle_id": 10,
        "greenhouse_id": 2,
        "greenhouse_uid": "gh-test",
        "timezone": "Europe/Moscow",
        "control_mode": "auto",
        "telemetry_max_age_sec": 300,
        "clean_fill_timeout_sec": 120,
        "solution_topup_timeout_sec": 120,
        "nutrient_solution_volume_l": 50.0,
        "command_plans": plans,
        "ec_clean": None,
        "drain_tank_volume_l": None,
        "pump_main_ml_per_sec": 10.0,
    }
    defaults.update(kwargs)
    return ZonePlan(**defaults)


def make_phase(**kwargs: Any) -> PhaseTargets:
    started = kwargs.pop(
        "started_at",
        datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
    )
    defaults: dict[str, Any] = {
        "phase_id": 1,
        "started_at": started,
        "interval_sec": 3600,
        "duration_sec": 60,
        "soil_moisture_min": 40.0,
        "soil_moisture_max": 60.0,
        "soil_moisture_unit": "%",
        "on_time": "06:00:00",
        "off_time": "22:00:00",
    }
    defaults.update(kwargs)
    return PhaseTargets(**defaults)


def make_planting(*, zone_id: int = 1, grow_cycle_id: int = 10, **phase_kw: Any) -> PlantingState:
    return PlantingState(
        zone_id=zone_id,
        grow_cycle_id=grow_cycle_id,
        phase=make_phase(**phase_kw),
    )


def level(
    *,
    channel: str,
    value: int | None,
    bound: bool = True,
    fresh: bool = True,
    ts: datetime | None = None,
) -> LevelReading:
    return LevelReading(
        channel=channel,
        value=value,
        ts=ts or datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
        bound=bound,
        fresh=fresh,
    )


def make_telemetry(
    *,
    feed_min: int = 1,
    feed_max: int = 0,
    clean_min: int = 1,
    clean_max: int = 0,
    drain_min: int | None = None,
    drain_max: int | None = None,
    drain_bound: bool = False,
    soil_value: float | None = 50.0,
    now: datetime | None = None,
    unbound_feed_min: bool = False,
    stale_feed_min: bool = False,
    ec_value: float | None = None,
    ph_value: float | None = None,
    ec_drain_value: float | None = None,
    ec_unit: str = "mS/cm",
    ph_unit: str = "pH",
    stale_ec: bool = False,
    stale_ph: bool = False,
    stale_ec_drain: bool = False,
) -> ZoneTelemetrySnapshot:
    stamp = now or datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    stale_stamp = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    from ae4.domain.planting import TelemetrySample

    soil = None
    if soil_value is not None:
        soil = TelemetrySample(
            metric_type="SOIL_MOISTURE",
            channel="soil_moisture",
            value=soil_value,
            ts=stamp,
            unit="%",
        )
    ec = None
    if ec_value is not None:
        ec = TelemetrySample(
            metric_type="EC",
            channel="ec_sensor",
            value=ec_value,
            ts=stale_stamp if stale_ec else stamp,
            unit=ec_unit,
        )
    ec_drain = None
    if ec_drain_value is not None:
        ec_drain = TelemetrySample(
            metric_type="EC",
            channel="ec_drain_sensor",
            value=ec_drain_value,
            ts=stale_stamp if stale_ec_drain else stamp,
            unit=ec_unit,
        )
    ph = None
    if ph_value is not None:
        ph = TelemetrySample(
            metric_type="PH",
            channel="ph_sensor",
            value=ph_value,
            ts=stale_stamp if stale_ph else stamp,
            unit=ph_unit,
        )
    return ZoneTelemetrySnapshot(
        level_solution_min=level(
            channel="level_solution_min",
            value=None if unbound_feed_min or stale_feed_min else feed_min,
            bound=not unbound_feed_min,
            fresh=not stale_feed_min and not unbound_feed_min,
            ts=stamp,
        ),
        level_solution_max=level(
            channel="level_solution_max",
            value=feed_max,
            ts=stamp,
        ),
        level_clean_min=level(
            channel="level_clean_min",
            value=clean_min,
            ts=stamp,
        ),
        level_clean_max=level(
            channel="level_clean_max",
            value=clean_max,
            ts=stamp,
        ),
        level_drain_min=level(
            channel="level_drain_min",
            value=drain_min if drain_bound else None,
            bound=drain_bound,
            fresh=drain_bound and drain_min is not None,
            ts=stamp,
        ),
        level_drain_max=level(
            channel="level_drain_max",
            value=drain_max if drain_bound else None,
            bound=drain_bound,
            fresh=drain_bound and drain_max is not None,
            ts=stamp,
        ),
        ec_feed=ec,
        ec_drain=ec_drain,
        ph_feed=ph,
        soil_moisture=soil,
        temp_air=None,
        humidity_air=None,
        solution_temp=None,
        light_samples=(),
    )
