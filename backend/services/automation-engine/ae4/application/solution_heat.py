"""Нагрев раствора: ON только ниже min, аварийный OFF выше max — класс безопасности."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping, Optional

from ae4.config.zone_plan import ZonePlan
from ae4.domain.planting import PhaseTargets, TelemetrySample
from ae4.domain.sensor_gate import is_fresh
from common.db import fetch
from common.history_logger_gateway import HistoryLoggerGateway, build_ae4_cmd_id

logger = logging.getLogger(__name__)

_HEATER_CHANNELS = frozenset({"heater", "solution_heater"})
_SOLUTION_TEMP_CHANNELS = frozenset({"solution_temp_c"})


async def apply_solution_heat(
    *,
    plan: ZonePlan,
    phase: PhaseTargets,
    gateway: HistoryLoggerGateway,
    zone_id: int,
    now: datetime,
    solution_temp: TelemetrySample | None,
    mutation_busy: bool,
    allow_on: bool = True,
) -> str | None:
    """OFF при перегреве — всегда. ON при холоде — только если слот мутации свободен."""
    binding = await resolve_heater_binding(zone_id=zone_id)
    if binding is None:
        return None

    node_uid, channel = binding
    temp = _fresh_solution_temp(
        sample=solution_temp,
        now=now,
        telemetry_max_age_sec=plan.telemetry_max_age_sec,
    )

    if (
        temp is not None
        and phase.solution_temp_max is not None
        and temp > float(phase.solution_temp_max)
    ):
        await _publish_heater(
            plan=plan,
            gateway=gateway,
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            state=False,
            role="heater_emergency_off",
        )
        return "off_over_max"

    if mutation_busy or not allow_on:
        return None

    if (
        temp is not None
        and phase.solution_temp_min is not None
        and temp < float(phase.solution_temp_min)
    ):
        await _publish_heater(
            plan=plan,
            gateway=gateway,
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            state=True,
            role="heater_on",
        )
        return "on_below_min"

    return None


async def resolve_heater_binding(*, zone_id: int) -> tuple[str, str] | None:
    rows = await fetch("SELECT uid, config FROM nodes WHERE zone_id = $1", zone_id)
    for row in rows:
        node_uid = str(row.get("uid") or "").strip()
        config = row.get("config")
        if not node_uid or not isinstance(config, Mapping):
            continue
        channels = config.get("channels")
        items: list[Any] = []
        if isinstance(channels, list):
            items = list(channels)
        elif isinstance(channels, Mapping):
            items = list(channels.values())
        for item in items:
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("id") or item.get("channel") or "").strip().lower()
            role = str(item.get("zone_role") or item.get("role") or "").strip().lower()
            if name in _HEATER_CHANNELS or role in _HEATER_CHANNELS:
                return node_uid, name or role
    return None


def _fresh_solution_temp(
    *,
    sample: TelemetrySample | None,
    now: datetime,
    telemetry_max_age_sec: int,
) -> float | None:
    if sample is None:
        return None
    channel = str(sample.channel or "").strip().lower()
    if channel not in _SOLUTION_TEMP_CHANNELS:
        return None
    if not is_fresh(
        sample=sample, now=now, telemetry_max_age_sec=telemetry_max_age_sec
    ):
        return None
    return float(sample.value)


async def _publish_heater(
    *,
    plan: ZonePlan,
    gateway: HistoryLoggerGateway,
    zone_id: int,
    node_uid: str,
    channel: str,
    state: bool,
    role: str,
) -> None:
    cmd_id = build_ae4_cmd_id(task_id=0, zone_id=zone_id, step_no=9000 if state else 9001)
    params = {"state": bool(state)}
    logger.info(
        "AE4 нагрев раствора",
        extra={
            "zone_id": zone_id,
            "channel": channel,
            "state": state,
            "role": role,
        },
    )
    await gateway.publish_and_await_done(
        greenhouse_uid=plan.greenhouse_uid,
        zone_id=zone_id,
        node_uid=node_uid,
        channel=channel,
        cmd="set_relay",
        params=params,
        cmd_id=cmd_id,
    )


__all__ = ["apply_solution_heat", "resolve_heater_binding"]
