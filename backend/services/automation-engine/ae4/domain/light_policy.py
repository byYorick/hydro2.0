"""Политика света §1.1.6 / §11.5: ON в окне, OFF на границе.

Окно считает только resolve_light_window из water_demand. Второй формулы нет.
OFF — класс безопасности, мутацию воды/дозы не ждёт. ON может отложиться.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Mapping, Sequence
from zoneinfo import ZoneInfo

from ae4.config.zone_plan import ZonePlan, ZonePlanConfigurationError, require_plan_steps
from ae4.domain.planting import PhaseTargets
from ae4.domain.water_demand import WaterDemandConfigError, resolve_light_window
from common.db import fetch
from common.history_logger_gateway import (
    HistoryLoggerGateway,
    build_ae4_cmd_id,
)

logger = logging.getLogger(__name__)

# Последнее успешно опубликованное ON/OFF. Повтор того же действия на каждом
# опросе 0,5 с не шлём: узел уже в этом состоянии.
_last_published_light_action: dict[int, str] = {}

LightAction = Literal["on", "off", "noop", "deferred_on"]

_LIGHT_ACTUATOR_CHANNELS = frozenset(
    {"white_light", "uv_light", "light", "light_main", "grow_light"}
)
_BRIGHTNESS_ATTRS = ("brightness", "brightness_pct", "pwm_duty")
# Признак для списка §11.7 (сборку unattended_blockers делает волна 9).
LIGHT_NO_GUARANTEED_OFF = "light_channel_no_guaranteed_off"
_PLAN_ON = "lighting_on"
_PLAN_OFF = "lighting_off"


class LightPolicyConfigError(RuntimeError):
    """Окно света задано неполно или неверно."""

    def __init__(self, *, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class LightPolicyDecision:
    action: LightAction
    reason_code: str
    steps: tuple[Mapping[str, Any], ...]
    unattended_blocker_reason: str | None = None


@dataclass(frozen=True)
class LightPolicyResult:
    decision: LightPolicyDecision
    published_cmd_ids: tuple[str, ...]


def decide_light(
    *,
    phase: PhaseTargets,
    now: datetime,
    timezone_name: str,
    mutation_busy: bool,
    on_steps: Sequence[Mapping[str, Any]],
    off_steps: Sequence[Mapping[str, Any]],
    unattended_blocker_reason: str | None = None,
) -> LightPolicyDecision:
    """Решение ON/OFF. Окно — только §1.1.6 через resolve_light_window."""
    try:
        tz = ZoneInfo(timezone_name)
    except Exception as exc:
        raise LightPolicyConfigError(
            reason_code="light_window_timezone_invalid",
            message=f"Неверный timezone теплицы для окна света: {timezone_name}",
        ) from exc
    try:
        window = resolve_light_window(phase=phase, now=now, tz=tz)
    except WaterDemandConfigError as exc:
        raise LightPolicyConfigError(
            reason_code="light_window_incomplete",
            message=str(exc),
        ) from exc

    if window is None:
        return LightPolicyDecision(
            action="noop",
            reason_code="light_window_absent",
            steps=(),
            unattended_blocker_reason=None,
        )

    local = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)
    inside = window.start_local <= local < window.end_local
    if inside:
        if mutation_busy:
            return LightPolicyDecision(
                action="deferred_on",
                reason_code="light_on_deferred_mutation_busy",
                steps=(),
                unattended_blocker_reason=unattended_blocker_reason,
            )
        steps = _apply_brightness(phase=phase, steps=on_steps, for_on=True)
        return LightPolicyDecision(
            action="on",
            reason_code="light_on_inside_window",
            steps=tuple(steps),
            unattended_blocker_reason=unattended_blocker_reason,
        )

    steps = tuple(off_steps)
    return LightPolicyDecision(
        action="off",
        reason_code="light_off_outside_window",
        steps=steps,
        unattended_blocker_reason=unattended_blocker_reason,
    )


async def light_unattended_blocker(
    *,
    plan: ZonePlan,
    zone_id: int,
) -> str | None:
    """Признак §11.7: канал света без гарантированного OFF."""
    _, _, blocker = await _resolve_light_steps(plan=plan, zone_id=zone_id)
    return blocker


async def apply_light_policy(
    *,
    plan: ZonePlan,
    phase: PhaseTargets,
    gateway: HistoryLoggerGateway,
    task_id: int,
    zone_id: int,
    now: datetime,
    mutation_busy: bool,
    allow_on: bool = True,
    step_base: int = 1,
) -> LightPolicyResult:
    """Публикует OFF всегда при вне окна; ON — если allow_on и мутация свободна."""
    on_steps, off_steps, blocker = await _resolve_light_steps(
        plan=plan,
        zone_id=zone_id,
    )
    decision = decide_light(
        phase=phase,
        now=now,
        timezone_name=plan.timezone,
        mutation_busy=mutation_busy,
        on_steps=on_steps,
        off_steps=off_steps,
        unattended_blocker_reason=blocker,
    )
    if decision.action == "deferred_on" and not allow_on:
        decision = LightPolicyDecision(
            action="noop",
            reason_code="light_on_skipped_allow_on_false",
            steps=(),
            unattended_blocker_reason=decision.unattended_blocker_reason,
        )
    if decision.action == "on" and not allow_on:
        decision = LightPolicyDecision(
            action="noop",
            reason_code="light_on_skipped_allow_on_false",
            steps=(),
            unattended_blocker_reason=decision.unattended_blocker_reason,
        )
    if decision.action not in {"on", "off"} or not decision.steps:
        return LightPolicyResult(decision=decision, published_cmd_ids=())
    if _last_published_light_action.get(zone_id) == decision.action:
        return LightPolicyResult(decision=decision, published_cmd_ids=())

    published = await _publish_steps(
        plan=plan,
        gateway=gateway,
        task_id=task_id,
        zone_id=zone_id,
        steps=decision.steps,
        step_base=step_base,
        role=decision.reason_code,
    )
    _last_published_light_action[zone_id] = decision.action
    return LightPolicyResult(
        decision=decision,
        published_cmd_ids=tuple(published),
    )


def phase_brightness(phase: PhaseTargets) -> int | None:
    """Яркость фазы, если поле уже есть. Нет поля — None, число не выдумываем."""
    for name in _BRIGHTNESS_ATTRS:
        if name not in phase.__dataclass_fields__:
            continue
        raw = getattr(phase, name, None)
        if raw is None:
            continue
        try:
            value = int(float(raw))
        except (TypeError, ValueError):
            continue
        return max(0, min(100, value))
    return None


def _apply_brightness(
    *,
    phase: PhaseTargets,
    steps: Sequence[Mapping[str, Any]],
    for_on: bool,
) -> list[dict[str, Any]]:
    brightness = phase_brightness(phase) if for_on else None
    result: list[dict[str, Any]] = []
    for step in steps:
        item = {
            "node_uid": str(step.get("node_uid") or "").strip(),
            "channel": str(step.get("channel") or "").strip(),
            "cmd": str(step.get("cmd") or "").strip(),
            "params": dict(step.get("params") or {}),
        }
        if (
            brightness is not None
            and item["cmd"] == "set_pwm"
            and "duty" in item["params"]
        ):
            item["params"]["duty"] = brightness
        result.append(item)
    return result


async def _resolve_light_steps(
    *,
    plan: ZonePlan,
    zone_id: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """Шаги ON/OFF из профиля зоны; иначе каналы света узлов. Блокер §11.7 — признак."""
    on_steps = _optional_plan_steps(plan, _PLAN_ON)
    off_steps = _optional_plan_steps(plan, _PLAN_OFF)
    node_on, node_off, guarantees = await _node_light_steps(zone_id=zone_id)
    if not on_steps:
        on_steps = node_on
    if not off_steps:
        off_steps = node_off
    for step in list(on_steps) + list(off_steps):
        channel = str(step.get("channel") or "").strip()
        if not channel:
            continue
        params = step.get("params") if isinstance(step.get("params"), Mapping) else {}
        if _positive_number(params.get("duration_ms")) or _positive_number(params.get("duration")):
            guarantees[channel] = True
    blocker: str | None = None
    channels = {
        str(step.get("channel") or "").strip()
        for step in list(on_steps) + list(off_steps)
        if str(step.get("channel") or "").strip()
    }
    for channel in channels:
        if not guarantees.get(channel, False):
            blocker = LIGHT_NO_GUARANTEED_OFF
            break
    return on_steps, off_steps, blocker


def _optional_plan_steps(plan: ZonePlan, plan_key: str) -> list[dict[str, Any]]:
    try:
        steps = require_plan_steps(plan, plan_key=plan_key)
    except ZonePlanConfigurationError:
        return []
    return [
        {
            "node_uid": str(step.get("node_uid") or "").strip(),
            "channel": str(step.get("channel") or "").strip(),
            "cmd": str(step.get("cmd") or "").strip(),
            "params": dict(step.get("params") or {}),
        }
        for step in steps
    ]


async def _node_light_steps(
    *,
    zone_id: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, bool]]:
    node_rows = await fetch(
        """
        SELECT uid, config
        FROM nodes
        WHERE zone_id = $1
        """,
        zone_id,
    )
    on_steps: list[dict[str, Any]] = []
    off_steps: list[dict[str, Any]] = []
    guarantees: dict[str, bool] = {}
    seen: set[tuple[str, str]] = set()
    for row in node_rows:
        node_uid = str(row.get("uid") or "").strip()
        config = row.get("config")
        channels = _channels_from_config(config)
        node_link_loss = _node_has_link_loss(config)
        for item in channels:
            if not isinstance(item, Mapping):
                continue
            channel = str(item.get("id") or item.get("channel") or item.get("name") or "").strip()
            if channel not in _LIGHT_ACTUATOR_CHANNELS:
                continue
            key = (node_uid, channel)
            if not node_uid or key in seen:
                continue
            seen.add(key)
            actuator = str(item.get("actuator_type") or "").strip().upper()
            type_name = str(item.get("type") or "").strip().upper()
            is_pwm = actuator == "PWM" or type_name == "PWM" or "pwm" in channel.lower()
            if is_pwm:
                # Яркость не выдумываем: PWM ON только из шагов профиля или поля фазы.
                off_steps.append(
                    {
                        "node_uid": node_uid,
                        "channel": channel,
                        "cmd": "set_pwm",
                        "params": {"duty": 0},
                    }
                )
            else:
                on_steps.append(
                    {
                        "node_uid": node_uid,
                        "channel": channel,
                        "cmd": "set_relay",
                        "params": {"state": True},
                    }
                )
                off_steps.append(
                    {
                        "node_uid": node_uid,
                        "channel": channel,
                        "cmd": "set_relay",
                        "params": {"state": False},
                    }
                )
            guarantees[channel] = node_link_loss or _channel_has_duration(item)
    return on_steps, off_steps, guarantees


def _channels_from_config(config: Any) -> list[Any]:
    if not isinstance(config, Mapping):
        return []
    raw = config.get("channels")
    if isinstance(raw, list):
        return raw
    if isinstance(raw, Mapping):
        return list(raw.values())
    return []


def _node_has_link_loss(config: Any) -> bool:
    if not isinstance(config, Mapping):
        return False
    top = config.get("link_loss_timeout_sec")
    if _positive_number(top):
        return True
    guards = config.get("fail_safe_guards")
    if isinstance(guards, Mapping) and _positive_number(guards.get("link_loss_timeout_sec")):
        return True
    return False


def _channel_has_duration(item: Mapping[str, Any]) -> bool:
    limits = item.get("safe_limits")
    if isinstance(limits, Mapping):
        if _positive_number(limits.get("max_duration_ms")):
            return True
        if _positive_number(limits.get("duration_ms")):
            return True
    if _positive_number(item.get("duration_ms")):
        return True
    if _positive_number(item.get("duration")):
        return True
    return False


def _positive_number(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


async def _publish_steps(
    *,
    plan: ZonePlan,
    gateway: HistoryLoggerGateway,
    task_id: int,
    zone_id: int,
    steps: Sequence[Mapping[str, Any]],
    step_base: int,
    role: str,
) -> list[str]:
    published: list[str] = []
    for index, step in enumerate(steps):
        channel = str(step.get("channel") or "").strip()
        cmd = str(step.get("cmd") or "").strip()
        params = dict(step.get("params") or {})
        node_uid = str(step.get("node_uid") or "").strip()
        if not node_uid or not channel or not cmd:
            raise RuntimeError(f"Нет node_uid/channel/cmd для шага света {role}")
        cmd_id = build_ae4_cmd_id(
            task_id=task_id,
            zone_id=zone_id,
            step_no=int(step_base) + index,
        )
        logger.info(
            "AE4 light_policy публикует шаг",
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
    "LIGHT_NO_GUARANTEED_OFF",
    "LightAction",
    "LightPolicyConfigError",
    "LightPolicyDecision",
    "LightPolicyResult",
    "apply_light_policy",
    "decide_light",
    "light_unattended_blocker",
    "phase_brightness",
]
