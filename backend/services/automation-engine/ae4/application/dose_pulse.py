"""Публикация одного импульса: sensor mode, затем cmd=dose params.ml."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

from ae4.application.water_procedures import publish_plan_steps
from ae4.config.zone_plan import (
    DoseActuatorRef,
    ZonePlan,
    ZonePlanConfigurationError,
    require_plan_steps,
)
from ae4.infrastructure.repositories.ae_command_repository import PgAeCommandRepository
from ae4.infrastructure.repositories.dose_state_repository import mark_dose_done
from common.db import fetch
from common.history_logger_gateway import HistoryLoggerGateway, build_ae4_cmd_id

logger = logging.getLogger(__name__)


async def run_dose_pulse(
    *,
    plan: ZonePlan,
    gateway: HistoryLoggerGateway,
    command_repository: PgAeCommandRepository,
    task_id: int,
    zone_id: int,
    now: datetime,
    reagent: str,
    dose_ml: float,
    baseline_value: float,
) -> None:
    """Sensor mode → dose. Длительность в params не кладём. last_dose_at после DONE."""
    if dose_ml <= 0:
        raise ZonePlanConfigurationError(
            reason_code="dose_ml_invalid",
            message="dose_ml должен быть > 0",
        )
    actuator = await _resolve_actuator(plan=plan, zone_id=zone_id, reagent=reagent)
    await _ensure_sensor_mode(
        plan=plan,
        gateway=gateway,
        command_repository=command_repository,
        task_id=task_id,
        zone_id=zone_id,
        now=now,
        node_uid=actuator.node_uid,
    )
    step_no = await command_repository.get_next_step_no(task_id=task_id)
    cmd_id = build_ae4_cmd_id(task_id=task_id, zone_id=zone_id, step_no=step_no)
    params = {"ml": float(dose_ml)}
    ae_command_id = await command_repository.create_pending(
        task_id=task_id,
        step_no=step_no,
        node_uid=actuator.node_uid,
        channel=actuator.channel,
        payload={
            "cmd": "dose",
            "params": params,
            "cmd_id": cmd_id,
            "role": "dose_pulse",
            "reagent": reagent,
        },
        now=now,
        stage_name="dose_pulse",
    )
    if ae_command_id is None:
        raise RuntimeError("Не удалось создать ae_commands для dose_pulse")
    try:
        result = await gateway.publish_and_await_done(
            greenhouse_uid=plan.greenhouse_uid,
            zone_id=zone_id,
            node_uid=actuator.node_uid,
            channel=actuator.channel,
            cmd="dose",
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
        await mark_dose_done(
            zone_id=zone_id,
            reagent=reagent,
            dose_ml=float(dose_ml),
            baseline_value=float(baseline_value),
            now=now,
        )
    finally:
        await _deactivate_sensor_mode(
            plan=plan,
            gateway=gateway,
            command_repository=command_repository,
            task_id=task_id,
            zone_id=zone_id,
            now=now,
            node_uid=actuator.node_uid,
        )


async def _ensure_sensor_mode(
    *,
    plan: ZonePlan,
    gateway: HistoryLoggerGateway,
    command_repository: PgAeCommandRepository,
    task_id: int,
    zone_id: int,
    now: datetime,
    node_uid: str,
) -> None:
    """Импульс только после активного sensor mode узла pH/EC."""
    try:
        steps = require_plan_steps(plan, plan_key="sensor_mode_activate")
    except ZonePlanConfigurationError as exc:
        raise ZonePlanConfigurationError(
            reason_code="sensor_mode_missing",
            message="Нет шагов sensor_mode_activate — импульс запрещён",
        ) from exc
    filtered = [
        step
        for step in steps
        if not node_uid or str(step.get("node_uid") or "").strip() in {"", node_uid}
    ]
    if not filtered:
        raise ZonePlanConfigurationError(
            reason_code="sensor_mode_missing",
            message=f"Нет sensor_mode_activate для узла {node_uid}",
        )
    await publish_plan_steps(
        plan=plan,
        gateway=gateway,
        command_repository=command_repository,
        task_id=task_id,
        zone_id=zone_id,
        plan_key="sensor_mode_activate",
        now=now,
        role="sensor_mode_activate",
        steps=filtered,
    )


async def _deactivate_sensor_mode(
    *,
    plan: ZonePlan,
    gateway: HistoryLoggerGateway,
    command_repository: PgAeCommandRepository,
    task_id: int,
    zone_id: int,
    now: datetime,
    node_uid: str,
) -> None:
    """После импульса, в том числе неуспешного, выключает sensor mode, если шаг есть в плане."""
    try:
        steps = require_plan_steps(plan, plan_key="sensor_mode_deactivate")
    except ZonePlanConfigurationError:
        return
    filtered = [
        step
        for step in steps
        if not node_uid or str(step.get("node_uid") or "").strip() in {"", node_uid}
    ]
    if not filtered:
        return
    try:
        await publish_plan_steps(
            plan=plan,
            gateway=gateway,
            command_repository=command_repository,
            task_id=task_id,
            zone_id=zone_id,
            plan_key="sensor_mode_deactivate",
            now=now,
            role="sensor_mode_deactivate",
            steps=filtered,
        )
    except Exception:
        logger.exception(
            "AE4: не удалось выключить sensor mode после импульса",
            extra={"zone_id": zone_id, "node_uid": node_uid},
        )


async def _resolve_actuator(
    *,
    plan: ZonePlan,
    zone_id: int,
    reagent: str,
) -> DoseActuatorRef:
    ref: DoseActuatorRef | None = None
    if plan.dose is not None:
        ref = plan.dose.actuators.get(reagent)
    if ref is not None and ref.node_uid and ref.channel:
        return ref
    channel = ref.channel if ref is not None else _default_channel(reagent)
    if not channel:
        raise ZonePlanConfigurationError(
            reason_code="dose_actuator_missing",
            message=f"Нет канала дозатора для реагента {reagent}",
        )
    node_uid = await _lookup_node_uid(zone_id=zone_id, channel=channel)
    if not node_uid:
        raise ZonePlanConfigurationError(
            reason_code="dose_actuator_missing",
            message=f"Нет узла с каналом {channel} для реагента {reagent}",
        )
    return DoseActuatorRef(
        node_uid=node_uid,
        channel=channel,
        ml_per_sec=ref.ml_per_sec if ref is not None else None,
    )


def _default_channel(reagent: str) -> str:
    return {
        "nutrition": "pump_a",
        "ph_up": "ph_up",
        "ph_down": "ph_down",
    }.get(reagent, "")


async def _lookup_node_uid(*, zone_id: int, channel: str) -> str:
    rows = await fetch(
        """
        SELECT uid, config
        FROM nodes
        WHERE zone_id = $1
        """,
        zone_id,
    )
    want = channel.strip().lower()
    for row in rows:
        node_uid = str(row.get("uid") or "").strip()
        config = row.get("config")
        channels: list[Any] = []
        if isinstance(config, Mapping):
            raw = config.get("channels")
            if isinstance(raw, list):
                channels = raw
            elif isinstance(raw, Mapping):
                channels = list(raw.values())
        for item in channels:
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("id") or item.get("channel") or "").strip().lower()
            if name == want and node_uid:
                return node_uid
    return ""


__all__ = ["run_dose_pulse"]
