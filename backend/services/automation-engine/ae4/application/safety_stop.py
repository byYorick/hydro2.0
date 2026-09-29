"""Класс безопасности §11.1: закрытие тракта, OFF дозаторов.

OFF света — ae4.domain.light_policy; здесь тонкая обёртка.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

from ae4.config.zone_plan import ZonePlan, ZonePlanConfigurationError, require_plan_steps
from ae4.domain.light_policy import apply_light_policy
from ae4.domain.planting import PhaseTargets
from common.db import fetch
from common.history_logger_gateway import (
    HistoryLoggerGateway,
    build_ae4_cmd_id,
)

logger = logging.getLogger(__name__)

_DOSE_CHANNEL_HINTS = frozenset(
    {
        "ph_up",
        "ph_down",
        "pump_a",
        "pump_b",
        "pump_c",
        "pump_d",
        "ec_a",
        "ec_b",
        "dose_ph_up",
        "dose_ph_down",
    }
)


async def close_irrigation_tract(
    *,
    plan: ZonePlan,
    gateway: HistoryLoggerGateway,
    task_id: int,
    zone_id: int,
    now: datetime,
    step_base: int = 1,
    node_uid_by_channel: Optional[Mapping[str, str]] = None,
) -> list[str]:
    """Досылает шаги irrigation_stop (клапаны OFF / стоп насоса)."""
    steps = require_plan_steps(plan, plan_key="irrigation_stop")
    return await _publish_steps(
        plan=plan,
        gateway=gateway,
        task_id=task_id,
        zone_id=zone_id,
        steps=steps,
        step_base=step_base,
        role="irrigation_stop",
        node_uid_by_channel=node_uid_by_channel,
    )


async def emergency_off_dosing_and_tract(
    *,
    plan: ZonePlan,
    gateway: HistoryLoggerGateway,
    task_id: int,
    zone_id: int,
    now: datetime,
    step_base: int = 1,
) -> list[str]:
    """E-STOP: закрыть тракт полива и погасить дозаторы."""
    published: list[str] = []
    try:
        published.extend(
            await close_irrigation_tract(
                plan=plan,
                gateway=gateway,
                task_id=task_id,
                zone_id=zone_id,
                now=now,
                step_base=step_base,
            )
        )
        step_base = step_base + len(published)
    except ZonePlanConfigurationError:
        logger.warning(
            "AE4 E-STOP: нет irrigation_stop, гасим только дозаторы",
            extra={"zone_id": zone_id},
        )
    dose_steps = await _dose_off_steps(zone_id=zone_id)
    if dose_steps:
        published.extend(
            await _publish_steps(
                plan=plan,
                gateway=gateway,
                task_id=task_id,
                zone_id=zone_id,
                steps=dose_steps,
                step_base=step_base,
                role="estop_dose_off",
                node_uid_by_channel=None,
            )
        )
    return published


async def light_off_if_outside_window(
    *,
    plan: ZonePlan,
    phase: PhaseTargets,
    gateway: HistoryLoggerGateway,
    task_id: int,
    zone_id: int,
    now: datetime,
    step_base: int = 1,
) -> list[str]:
    """Тонкая обёртка: OFF вне окна через light_policy, ON не публикует."""
    result = await apply_light_policy(
        plan=plan,
        phase=phase,
        gateway=gateway,
        task_id=task_id,
        zone_id=zone_id,
        now=now,
        mutation_busy=True,
        allow_on=False,
        step_base=step_base,
    )
    return list(result.published_cmd_ids)


async def _dose_off_steps(*, zone_id: int) -> list[dict[str, Any]]:
    node_rows = await fetch(
        """
        SELECT uid, config
        FROM nodes
        WHERE zone_id = $1
        """,
        zone_id,
    )
    steps: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in node_rows:
        node_uid = str(row.get("uid") or "").strip()
        config = row.get("config")
        channels = []
        if isinstance(config, Mapping):
            raw = config.get("channels")
            if isinstance(raw, list):
                channels = raw
            elif isinstance(raw, Mapping):
                channels = list(raw.values())
        for item in channels:
            if not isinstance(item, Mapping):
                continue
            channel = str(item.get("id") or item.get("channel") or "").strip()
            actuator = str(item.get("actuator_type") or item.get("type") or "").strip().upper()
            if channel not in _DOSE_CHANNEL_HINTS and actuator not in {
                "DOSE",
                "DOSING_PUMP",
                "PERISTALTIC",
            }:
                continue
            key = (node_uid, channel)
            if not node_uid or not channel or key in seen:
                continue
            seen.add(key)
            steps.append(
                {
                    "node_uid": node_uid,
                    "channel": channel,
                    "cmd": "set_relay",
                    "params": {"state": False},
                }
            )
    return steps


async def _publish_steps(
    *,
    plan: ZonePlan,
    gateway: HistoryLoggerGateway,
    task_id: int,
    zone_id: int,
    steps: Sequence[Mapping[str, Any]],
    step_base: int,
    role: str,
    node_uid_by_channel: Optional[Mapping[str, str]],
) -> list[str]:
    published: list[str] = []
    for index, step in enumerate(steps):
        channel = str(step.get("channel") or "").strip()
        cmd = str(step.get("cmd") or "").strip()
        params = dict(step.get("params") or {})
        node_uid = str(step.get("node_uid") or "").strip()
        if not node_uid and node_uid_by_channel:
            node_uid = str(node_uid_by_channel.get(channel) or "").strip()
        if not node_uid:
            raise RuntimeError(
                f"Нет node_uid для шага безопасности {role}:{channel}"
            )
        # Имя plan в gateway не отправляется.
        cmd_id = build_ae4_cmd_id(
            task_id=task_id,
            zone_id=zone_id,
            step_no=int(step_base) + index,
        )
        logger.info(
            "AE4 safety_stop публикует шаг",
            extra={
                "zone_id": zone_id,
                "task_id": task_id,
                "role": role,
                "channel": channel,
                "cmd": cmd,
                "cmd_id": cmd_id,
            },
        )
        result = await gateway.publish_and_await_done(
            greenhouse_uid=plan.greenhouse_uid,
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
            params=params,
            cmd_id=cmd_id,
        )
        published.append(result.cmd_id)
    return published


__all__ = [
    "close_irrigation_tract",
    "emergency_off_dosing_and_tract",
    "light_off_if_outside_window",
]
