"""Сток: доля слива §11.4, место в баке, возврат. Единственное место стока."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from ae4.domain.planting import TelemetrySample
from ae4.domain.sensor_gate import is_fresh

# Зеркало NODE_CHANNELS_REFERENCE.md §2.10. Пустой frozenset → контур не стартует (E245).
CONTRACT_DRAIN_TANK_LEVEL_CHANNELS: frozenset[str] = frozenset(
    {"level_drain_min", "level_drain_max"}
)
CONTRACT_DRAIN_TANK_EC_CHANNEL: str = "ec_drain_sensor"

# Клапан слива рабочего бака AE3 — не уровень бака стока.
_NOT_DRAIN_TANK_LEVEL = frozenset(
    {"valve_drain", "drain", "drain_main", "drain_valve", "pump_drain"}
)

_FEED_TO_DRAIN_START = "feed_to_drain_start"
_FEED_TO_DRAIN_STOP = "feed_to_drain_stop"
_DRAIN_TO_FEED_START = "drain_to_feed_start"
_DRAIN_TO_FEED_STOP = "drain_to_feed_stop"


@dataclass(frozen=True)
class DrainPortionDecision:
    allow: bool
    volume_l: float | None
    reason_code: str
    human_message: str
    critical_alert: bool


@dataclass(frozen=True)
class DrainReturnDecision:
    allow: bool
    reason_code: str
    human_message: str


@dataclass(frozen=True)
class DrainRoomAssessment:
    status: str  # ok | unseen | full
    reason_code: str
    human_message: str
    shot_volume_ml: float | None


def drain_tank_channels_in_contract() -> bool:
    """Контур стока стартует только при непустых именах каналов в контракте."""
    if not CONTRACT_DRAIN_TANK_LEVEL_CHANNELS:
        return False
    if not str(CONTRACT_DRAIN_TANK_EC_CHANNEL or "").strip():
        return False
    if CONTRACT_DRAIN_TANK_LEVEL_CHANNELS & _NOT_DRAIN_TANK_LEVEL:
        return False
    if CONTRACT_DRAIN_TANK_EC_CHANNEL in _NOT_DRAIN_TANK_LEVEL:
        return False
    return True


def is_drain_tank_level_channel(channel: str) -> bool:
    name = str(channel or "").strip()
    if name in _NOT_DRAIN_TANK_LEVEL:
        return False
    return name in CONTRACT_DRAIN_TANK_LEVEL_CHANNELS


def has_drain_circuit(
    *,
    level_drain_min_bound: bool,
    level_drain_max_bound: bool,
    ec_drain_bound: bool,
    has_feed_to_drain_steps: bool,
) -> bool:
    """Живой контур: каналы в контракте, привязка уровней/EC и шаги профиля."""
    if not drain_tank_channels_in_contract():
        return False
    if not (level_drain_min_bound and level_drain_max_bound and ec_drain_bound):
        return False
    return bool(has_feed_to_drain_steps)


def compute_drain_portion_l(
    *,
    nutrient_solution_volume_l: float | None,
    ec_feed: float | None,
    ec_target: float | None,
    ec_clean: float | None,
) -> DrainPortionDecision:
    """
    D = V * (EC - EC_target) / (EC - EC_clean).
    V только из nutrient_solution_volume_l фазы. Каталожные 100 л не подставлять.
    """
    if nutrient_solution_volume_l is None or nutrient_solution_volume_l <= 0:
        return DrainPortionDecision(
            allow=False,
            volume_l=None,
            reason_code="drain_portion_volume_missing",
            human_message="Нет nutrient_solution_volume_l фазы — слива нет, кадра нет",
            critical_alert=True,
        )
    if ec_clean is None:
        return DrainPortionDecision(
            allow=False,
            volume_l=None,
            reason_code="drain_portion_ec_clean_missing",
            human_message="Нет EC_clean — долю слива не считать, кадра нет",
            critical_alert=True,
        )
    if ec_feed is None:
        return DrainPortionDecision(
            allow=False,
            volume_l=None,
            reason_code="drain_portion_ec_missing",
            human_message="Нет свежего EC feed — слива нет, кадра нет",
            critical_alert=True,
        )
    if ec_target is None:
        return DrainPortionDecision(
            allow=False,
            volume_l=None,
            reason_code="drain_portion_ec_target_missing",
            human_message="Нет цели EC — слива нет, кадра нет",
            critical_alert=True,
        )
    if float(ec_clean) >= float(ec_target):
        return DrainPortionDecision(
            allow=False,
            volume_l=None,
            reason_code="drain_portion_ec_clean_ge_target",
            human_message="EC_clean >= цели EC — слива нет, критический вызов",
            critical_alert=True,
        )
    denominator = float(ec_feed) - float(ec_clean)
    if denominator <= 0:
        return DrainPortionDecision(
            allow=False,
            volume_l=None,
            reason_code="drain_portion_nonpositive_denominator",
            human_message="Знаменатель доли слива неположительный — слива нет",
            critical_alert=True,
        )
    numerator = float(ec_feed) - float(ec_target)
    if numerator <= 0:
        return DrainPortionDecision(
            allow=False,
            volume_l=None,
            reason_code="drain_portion_ec_not_above_target",
            human_message="EC не выше цели — доля слива не нужна",
            critical_alert=False,
        )
    volume_l = float(nutrient_solution_volume_l) * numerator / denominator
    if volume_l <= 0:
        return DrainPortionDecision(
            allow=False,
            volume_l=None,
            reason_code="drain_portion_nonpositive_result",
            human_message="Расчёт доли слива дал неположительный объём",
            critical_alert=True,
        )
    if volume_l > float(nutrient_solution_volume_l):
        volume_l = float(nutrient_solution_volume_l)
    return DrainPortionDecision(
        allow=True,
        volume_l=volume_l,
        reason_code="feed_to_drain_portion",
        human_message=f"Слив доли {volume_l:.4f} л в бак стока",
        critical_alert=False,
    )


def evaluate_portion_for_full_tank(
    *,
    circuit_alive: bool,
    nutrient_solution_volume_l: float | None,
    ec_feed: float | None,
    ec_feed_fresh: bool,
    ec_target: float | None,
    ec_clean: float | None,
) -> DrainPortionDecision:
    """Полный бак + EC выше коридора: доля или пауза без failed."""
    if not circuit_alive:
        return DrainPortionDecision(
            allow=False,
            volume_l=None,
            reason_code="ec_high_tank_full_await_drain",
            human_message=(
                "EC выше коридора и бак полон — контура стока нет, пауза, кадр запрещён"
            ),
            critical_alert=True,
        )
    if not ec_feed_fresh:
        return DrainPortionDecision(
            allow=False,
            volume_l=None,
            reason_code="drain_portion_ec_stale",
            human_message="EC feed протух — слива нет, кадра нет",
            critical_alert=True,
        )
    return compute_drain_portion_l(
        nutrient_solution_volume_l=nutrient_solution_volume_l,
        ec_feed=ec_feed,
        ec_target=ec_target,
        ec_clean=ec_clean,
    )


def estimate_shot_volume_ml(
    *,
    volume_ml: float | None,
    duration_sec: int | None,
    pump_ml_per_sec: float | None,
) -> float | None:
    """Объём кадра для места в стоке. Секунды сами на литры не умножают."""
    if volume_ml is not None and float(volume_ml) > 0:
        return float(volume_ml)
    if (
        duration_sec is not None
        and int(duration_sec) > 0
        and pump_ml_per_sec is not None
        and float(pump_ml_per_sec) > 0
    ):
        return float(duration_sec) * float(pump_ml_per_sec)
    return None


def assess_drain_room(
    *,
    circuit_alive: bool,
    level_drain_max_value: int | None,
    level_drain_max_fresh: bool,
    volume_ml: float | None,
    duration_sec: int | None,
    pump_ml_per_sec: float | None,
) -> DrainRoomAssessment:
    """Место в стоке. Нет объёма кадра — unseen; полив держит только свежий не-max."""
    if not circuit_alive:
        return DrainRoomAssessment(
            status="ok",
            reason_code="drain_room_no_circuit",
            human_message="Контура стока нет — место в стоке не ограничивает кадр",
            shot_volume_ml=None,
        )
    if not level_drain_max_fresh or level_drain_max_value is None:
        return DrainRoomAssessment(
            status="unseen",
            reason_code="drain_room_level_unseen",
            human_message="Уровень бака стока несвежий — доля стока unseen",
            shot_volume_ml=None,
        )
    if int(level_drain_max_value) == 1:
        return DrainRoomAssessment(
            status="full",
            reason_code="drain_room_full",
            human_message="Бак стока полон — кадр в сток не льём",
            shot_volume_ml=None,
        )
    shot = estimate_shot_volume_ml(
        volume_ml=volume_ml,
        duration_sec=duration_sec,
        pump_ml_per_sec=pump_ml_per_sec,
    )
    if shot is None:
        return DrainRoomAssessment(
            status="unseen",
            reason_code="drain_room_volume_unseen",
            human_message=(
                "Нет volume_ml и нет duration_sec с расходом насоса — "
                "место в стоке unseen, полив только при свежем не-max"
            ),
            shot_volume_ml=None,
        )
    return DrainRoomAssessment(
        status="ok",
        reason_code="drain_room_ok",
        human_message="В баке стока есть место под кадр",
        shot_volume_ml=shot,
    )


def evaluate_drain_return(
    *,
    feed_volume_l: float | None,
    drain_volume_l: float | None,
    ec_drain: TelemetrySample | None,
    now: datetime,
    telemetry_max_age_sec: int | None,
    ec_min: float | None,
    ec_max: float | None,
    feed_ec: float | None,
) -> DrainReturnDecision:
    """
    Возврат в feed только при известных ёмкостях обоих баков и свежем EC стока,
    и только если смесь остаётся в коридоре. Долю возврата не подставлять.
    """
    if feed_volume_l is None or feed_volume_l <= 0:
        return DrainReturnDecision(
            allow=False,
            reason_code="drain_return_feed_volume_unknown",
            human_message="Ёмкость бака feed неизвестна — возврат из стока запрещён",
        )
    if drain_volume_l is None or drain_volume_l <= 0:
        return DrainReturnDecision(
            allow=False,
            reason_code="drain_return_drain_volume_unknown",
            human_message="Ёмкость бака стока неизвестна — возврат запрещён",
        )
    if not is_fresh(
        sample=ec_drain, now=now, telemetry_max_age_sec=telemetry_max_age_sec
    ):
        return DrainReturnDecision(
            allow=False,
            reason_code="drain_return_ec_stale",
            human_message="EC стока протух или отсутствует — возврат запрещён",
        )
    assert ec_drain is not None
    if ec_min is None or ec_max is None or feed_ec is None:
        return DrainReturnDecision(
            allow=False,
            reason_code="drain_return_corridor_unknown",
            human_message="Нет коридора EC или EC feed — возврат запрещён",
        )
    # Смесь равных известных ёмкостей: (V_f*EC_f + V_d*EC_d) / (V_f + V_d).
    # Долю агент не подставляет: обе ёмкости уже проверены выше.
    mixed = (
        float(feed_volume_l) * float(feed_ec)
        + float(drain_volume_l) * float(ec_drain.value)
    ) / (float(feed_volume_l) + float(drain_volume_l))
    if mixed < float(ec_min) or mixed > float(ec_max):
        return DrainReturnDecision(
            allow=False,
            reason_code="drain_return_mixture_out_of_corridor",
            human_message="Смесь после возврата вышла бы из коридора EC — сток удерживается",
        )
    return DrainReturnDecision(
        allow=True,
        reason_code="drain_to_feed",
        human_message="Возврат из стока в feed: смесь в коридоре",
    )


def has_feed_to_drain_plan_steps(*, command_plans: Mapping[str, object]) -> bool:
    return _has_plan_pair(
        command_plans=command_plans,
        start_key=_FEED_TO_DRAIN_START,
        stop_key=_FEED_TO_DRAIN_STOP,
    )


def has_drain_to_feed_plan_steps(*, command_plans: Mapping[str, object]) -> bool:
    return _has_plan_pair(
        command_plans=command_plans,
        start_key=_DRAIN_TO_FEED_START,
        stop_key=_DRAIN_TO_FEED_STOP,
    )


def _has_plan_pair(
    *,
    command_plans: Mapping[str, object],
    start_key: str,
    stop_key: str,
) -> bool:
    plans_root = command_plans.get("plans")
    if not isinstance(plans_root, Mapping):
        plans_root = command_plans
    if not isinstance(plans_root, Mapping):
        return False
    start = plans_root.get(start_key)
    stop = plans_root.get(stop_key)
    if not isinstance(start, list) or not start:
        return False
    if not isinstance(stop, list) or not stop:
        return False
    for step in list(start) + list(stop):
        if not isinstance(step, Mapping):
            return False
        channel = str(step.get("channel") or "").strip()
        if not channel or not str(step.get("cmd") or "").strip():
            return False
        if channel in _NOT_DRAIN_TANK_LEVEL and channel.startswith("level_"):
            return False
    return True


def duration_ms_for_portion_l(
    *,
    volume_l: float,
    pump_ml_per_sec: float | None,
) -> int | None:
    """Длительность слива доли. Без расхода насоса секунды из литров не выдумываем."""
    if volume_l <= 0:
        return None
    if pump_ml_per_sec is None or pump_ml_per_sec <= 0:
        return None
    ml = float(volume_l) * 1000.0
    duration_ms = int(ml / float(pump_ml_per_sec) * 1000.0)
    if duration_ms < 1000:
        return 1000
    if duration_ms > 300_000:
        return 300_000
    return duration_ms


__all__ = [
    "CONTRACT_DRAIN_TANK_LEVEL_CHANNELS",
    "CONTRACT_DRAIN_TANK_EC_CHANNEL",
    "DrainPortionDecision",
    "DrainReturnDecision",
    "DrainRoomAssessment",
    "drain_tank_channels_in_contract",
    "is_drain_tank_level_channel",
    "has_drain_circuit",
    "compute_drain_portion_l",
    "evaluate_portion_for_full_tank",
    "estimate_shot_volume_ml",
    "assess_drain_room",
    "evaluate_drain_return",
    "has_feed_to_drain_plan_steps",
    "has_drain_to_feed_plan_steps",
    "duration_ms_for_portion_l",
]
