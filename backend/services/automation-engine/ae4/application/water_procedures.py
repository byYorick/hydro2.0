"""Короткие процедуры переноса воды §2.1."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence

from ae4.config.zone_plan import ZonePlan, ZonePlanConfigurationError, require_plan_steps
from ae4.infrastructure.repositories.ae_command_repository import PgAeCommandRepository
from ae4.infrastructure.shot_events import record_successful_shot
from ae4.infrastructure.zone_telemetry import (
    LevelReading,
    load_zone_telemetry,
    tank_full,
)
from common.history_logger_gateway import (
    HistoryLoggerGateway,
    build_ae4_cmd_id,
)

logger = logging.getLogger(__name__)

# Потолок history-logger `_MAX_DURATION_MS_SANITY`. Своего потолка нет.
_HL_DURATION_MS_CEILING = 300_000
_MIN_DURATION_MS = 1000
_DRAIN_OR_RETURN_CHANNELS = frozenset(
    {
        "valve_drain",
        "valve_drain_return",
        "pump_drain",
        "valve_return",
        "drain_return",
    }
)

LevelReader = Callable[[], Awaitable[tuple[LevelReading, LevelReading]]]


def duration_ms_for_frame(*, duration_sec: int) -> int:
    raw = int(duration_sec) * 1000
    if raw < _MIN_DURATION_MS:
        return _MIN_DURATION_MS
    if raw > _HL_DURATION_MS_CEILING:
        return _HL_DURATION_MS_CEILING
    return raw


async def publish_plan_steps(
    *,
    plan: ZonePlan,
    gateway: HistoryLoggerGateway,
    command_repository: PgAeCommandRepository,
    task_id: int,
    zone_id: int,
    plan_key: str,
    now: datetime,
    role: str,
    steps: Sequence[Mapping[str, Any]] | None = None,
    forbid_drain: bool = False,
) -> list[str]:
    """Публикует шаги по порядку. Имя plan_key в gateway не отправляется."""
    resolved = list(steps) if steps is not None else require_plan_steps(plan, plan_key=plan_key)
    published: list[str] = []
    for step in resolved:
        channel = str(step.get("channel") or "").strip()
        cmd = str(step.get("cmd") or "").strip()
        params = dict(step.get("params") or {})
        node_uid = str(step.get("node_uid") or "").strip()
        if not channel or not cmd:
            raise ZonePlanConfigurationError(
                reason_code="zone_plan_invalid_step",
                message=f"Шаг {plan_key} без channel/cmd",
            )
        if forbid_drain and channel in _DRAIN_OR_RETURN_CHANNELS:
            raise RuntimeError(
                f"feed_only запрещает канал слива/возврата: {channel}"
            )
        if not node_uid:
            raise ZonePlanConfigurationError(
                reason_code="zone_plan_missing_node_uid",
                message=f"Нет node_uid для шага {plan_key}:{channel}",
            )
        step_no = await command_repository.get_next_step_no(task_id=task_id)
        cmd_id = build_ae4_cmd_id(task_id=task_id, zone_id=zone_id, step_no=step_no)
        ae_command_id = await command_repository.create_pending(
            task_id=task_id,
            step_no=step_no,
            node_uid=node_uid,
            channel=channel,
            payload={
                "cmd": cmd,
                "params": params,
                "cmd_id": cmd_id,
                "role": role,
            },
            now=now,
            stage_name=role,
        )
        if ae_command_id is None:
            raise RuntimeError(f"Не удалось создать ae_commands для {role}:{channel}")
        result = await gateway.publish_and_await_done(
            greenhouse_uid=plan.greenhouse_uid,
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
            params=params,
            cmd_id=cmd_id,
        )
        await command_repository.mark_accepted(
            ae_command_id=ae_command_id,
            external_id=result.legacy_command_id or cmd_id,
            now=now,
        )
        await command_repository.mark_terminal(
            ae_command_id=ae_command_id,
            terminal_status="DONE",
            now=now,
        )
        published.append(cmd_id)
    return published


def build_irrigation_start_steps(
    *,
    plan: ZonePlan,
    duration_sec: int,
) -> list[dict[str, Any]]:
    """Клапаны set_relay true, насос pump_main/run_pump/duration_ms."""
    steps = require_plan_steps(plan, plan_key="irrigation_start")
    channels = {str(step.get("channel") or "").strip() for step in steps}
    for required in ("valve_solution_supply", "valve_irrigation", "pump_main"):
        if required not in channels:
            raise ZonePlanConfigurationError(
                reason_code="zone_plan_missing_steps",
                message=f"Нет канала {required} в irrigation_start",
            )
    duration_ms = duration_ms_for_frame(duration_sec=duration_sec)
    prepared: list[dict[str, Any]] = []
    for step in steps:
        channel = str(step.get("channel") or "").strip()
        if channel in _DRAIN_OR_RETURN_CHANNELS:
            continue
        item = {
            "node_uid": str(step.get("node_uid") or "").strip(),
            "channel": channel,
            "cmd": str(step.get("cmd") or "").strip(),
            "params": dict(step.get("params") or {}),
        }
        if channel == "pump_main":
            item["cmd"] = "run_pump"
            item["params"] = {"duration_ms": duration_ms}
        prepared.append(item)
    return prepared


async def run_feed_to_plants(
    *,
    plan: ZonePlan,
    gateway: HistoryLoggerGateway,
    command_repository: PgAeCommandRepository,
    task_id: int,
    zone_id: int,
    now: datetime,
    duration_sec: int,
    shot_kind: str,
    reason_code: str,
    grow_cycle_id: int,
    phase_id: int,
) -> None:
    """Кадр целиком: start → DONE насоса → stop в том же тике.

    Стоп клапанов публикуется и если шаг старта не дошёл до DONE,
    иначе тракт остаётся открытым.
    """
    start_steps = build_irrigation_start_steps(plan=plan, duration_sec=duration_sec)
    stop_steps = [
        step
        for step in require_plan_steps(plan, plan_key="irrigation_stop")
        if str(step.get("channel") or "").strip() not in _DRAIN_OR_RETURN_CHANNELS
    ]
    try:
        await publish_plan_steps(
            plan=plan,
            gateway=gateway,
            command_repository=command_repository,
            task_id=task_id,
            zone_id=zone_id,
            plan_key="irrigation_start",
            now=now,
            role="irrigation_start",
            steps=start_steps,
            forbid_drain=True,
        )
    finally:
        await publish_plan_steps(
            plan=plan,
            gateway=gateway,
            command_repository=command_repository,
            task_id=task_id,
            zone_id=zone_id,
            plan_key="irrigation_stop",
            now=now,
            role="irrigation_stop",
            steps=stop_steps,
            forbid_drain=True,
        )
    await record_successful_shot(
        zone_id=zone_id,
        grow_cycle_id=grow_cycle_id,
        phase_id=phase_id,
        kind=shot_kind if shot_kind in {"planned", "extra"} else "extra",
        duration_sec=duration_sec,
        reason_code=reason_code,
    )


async def run_supply_to_clean(
    *,
    plan: ZonePlan,
    gateway: HistoryLoggerGateway,
    command_repository: PgAeCommandRepository,
    task_id: int,
    zone_id: int,
    now: datetime,
    level_reader: LevelReader | None = None,
    sleep_fn: Callable[[float], Awaitable[None]] | None = None,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> None:
    """Набор clean: start → max или timeout → stop. Утечка min 1→0 — сбой."""
    timeout_sec = int(plan.clean_fill_timeout_sec)
    if timeout_sec <= 0:
        raise ZonePlanConfigurationError(
            reason_code="zone_plan_missing_key",
            message="Нет runtime.clean_fill_timeout_sec",
        )
    await publish_plan_steps(
        plan=plan,
        gateway=gateway,
        command_repository=command_repository,
        task_id=task_id,
        zone_id=zone_id,
        plan_key="clean_fill_start",
        now=now,
        role="clean_fill_start",
    )
    try:
        await _await_fill(
            zone_id=zone_id,
            plan=plan,
            now=now,
            timeout_sec=timeout_sec,
            min_name="level_clean_min",
            max_name="level_clean_max",
            level_reader=level_reader,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
        )
    finally:
        await publish_plan_steps(
            plan=plan,
            gateway=gateway,
            command_repository=command_repository,
            task_id=task_id,
            zone_id=zone_id,
            plan_key="clean_fill_stop",
            now=now,
            role="clean_fill_stop",
        )


async def run_clean_to_feed(
    *,
    plan: ZonePlan,
    gateway: HistoryLoggerGateway,
    command_repository: PgAeCommandRepository,
    task_id: int,
    zone_id: int,
    now: datetime,
    level_reader: LevelReader | None = None,
    sleep_fn: Callable[[float], Awaitable[None]] | None = None,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> None:
    """Долив feed: solution_fill_start → max или timeout → stop."""
    timeout_sec = int(plan.solution_topup_timeout_sec)
    if timeout_sec <= 0:
        raise ZonePlanConfigurationError(
            reason_code="zone_plan_missing_key",
            message="Нет runtime.solution_topup_timeout_sec",
        )
    await publish_plan_steps(
        plan=plan,
        gateway=gateway,
        command_repository=command_repository,
        task_id=task_id,
        zone_id=zone_id,
        plan_key="solution_fill_start",
        now=now,
        role="solution_fill_start",
    )
    try:
        await _await_fill(
            zone_id=zone_id,
            plan=plan,
            now=now,
            timeout_sec=timeout_sec,
            min_name="level_solution_min",
            max_name="level_solution_max",
            level_reader=level_reader,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
        )
    finally:
        await publish_plan_steps(
            plan=plan,
            gateway=gateway,
            command_repository=command_repository,
            task_id=task_id,
            zone_id=zone_id,
            plan_key="solution_fill_stop",
            now=now,
            role="solution_fill_stop",
        )


async def run_feed_to_drain(
    *,
    plan: ZonePlan,
    gateway: HistoryLoggerGateway,
    command_repository: PgAeCommandRepository,
    task_id: int,
    zone_id: int,
    now: datetime,
    duration_ms: int,
) -> None:
    """Слив доли feed → drain. Имя plan в gateway не отправляется. Стадии AE3 не копируются."""
    if duration_ms <= 0:
        raise ZonePlanConfigurationError(
            reason_code="drain_portion_duration_missing",
            message="Нет duration_ms для доли слива",
        )
    start_steps = _build_timed_plan_steps(
        plan=plan,
        plan_key="feed_to_drain_start",
        duration_ms=duration_ms,
    )
    stop_steps = list(require_plan_steps(plan, plan_key="feed_to_drain_stop"))
    try:
        await publish_plan_steps(
            plan=plan,
            gateway=gateway,
            command_repository=command_repository,
            task_id=task_id,
            zone_id=zone_id,
            plan_key="feed_to_drain_start",
            now=now,
            role="feed_to_drain_start",
            steps=start_steps,
        )
    finally:
        await publish_plan_steps(
            plan=plan,
            gateway=gateway,
            command_repository=command_repository,
            task_id=task_id,
            zone_id=zone_id,
            plan_key="feed_to_drain_stop",
            now=now,
            role="feed_to_drain_stop",
            steps=stop_steps,
        )


def _build_timed_plan_steps(
    *,
    plan: ZonePlan,
    plan_key: str,
    duration_ms: int,
) -> list[dict[str, Any]]:
    steps = require_plan_steps(plan, plan_key=plan_key)
    prepared: list[dict[str, Any]] = []
    for step in steps:
        channel = str(step.get("channel") or "").strip()
        cmd = str(step.get("cmd") or "").strip()
        item = {
            "node_uid": str(step.get("node_uid") or "").strip(),
            "channel": channel,
            "cmd": cmd,
            "params": dict(step.get("params") or {}),
        }
        if channel in {"pump_main", "pump_drain"} or cmd == "run_pump":
            item["cmd"] = "run_pump"
            item["params"] = {"duration_ms": int(duration_ms)}
        prepared.append(item)
    return prepared


async def _await_fill(
    *,
    zone_id: int,
    plan: ZonePlan,
    now: datetime,
    timeout_sec: int,
    min_name: str,
    max_name: str,
    level_reader: LevelReader | None,
    sleep_fn: Callable[[float], Awaitable[None]] | None,
    monotonic_fn: Callable[[], float],
) -> None:
    sleeper = sleep_fn or asyncio.sleep
    started = monotonic_fn()
    saw_min_high = False
    while True:
        if monotonic_fn() - started >= float(timeout_sec):
            logger.info(
                "AE4: таймаут набора/долива",
                extra={"zone_id": zone_id, "max_name": max_name},
            )
            return
        if level_reader is not None:
            min_reading, max_reading = await level_reader()
        else:
            snap = await load_zone_telemetry(
                zone_id=zone_id,
                now=datetime.now(timezone.utc),
                telemetry_max_age_sec=plan.telemetry_max_age_sec,
            )
            min_reading = getattr(snap, min_name)
            max_reading = getattr(snap, max_name)
        if not min_reading.bound or not min_reading.fresh:
            raise RuntimeError(
                f"Проба {min_name} недоступна или протухла во время набора"
            )
        if not max_reading.bound or not max_reading.fresh:
            raise RuntimeError(
                f"Проба {max_name} недоступна или протухла во время набора"
            )
        if min_reading.value == 1:
            saw_min_high = True
        elif saw_min_high and min_reading.value == 0 and max_reading.value != 1:
            raise RuntimeError(
                f"Утечка: {min_name} был 1 и стал 0 до верхнего уровня"
            )
        if tank_full(reading=max_reading):
            return
        await sleeper(0.5)


__all__ = [
    "duration_ms_for_frame",
    "publish_plan_steps",
    "build_irrigation_start_steps",
    "run_feed_to_plants",
    "run_supply_to_clean",
    "run_clean_to_feed",
    "run_feed_to_drain",
]
