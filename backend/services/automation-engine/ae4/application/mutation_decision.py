"""Решение мутации воды и одного импульса дозы §2.1 / §2.3 / §11.4."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ae4.config.zone_plan import ZonePlan, ZonePlanConfigurationError, require_plan_steps
from ae4.domain.dose_policy import (
    ControllerDoseParams,
    DoseDecision,
    DoseReagentState,
    evaluate_tick_dose,
)
from ae4.domain.drain_policy import (
    assess_drain_room,
    duration_ms_for_portion_l,
    evaluate_portion_for_full_tank,
    has_drain_circuit,
    has_feed_to_drain_plan_steps,
)
from ae4.domain.planting import (
    LightIntegralCursor,
    PhaseTargets,
    ShotMark,
    TelemetrySample,
)
from ae4.domain.water_demand import WaterDemandDecision, evaluate_water_demand
from ae4.infrastructure.zone_telemetry import (
    ZoneTelemetrySnapshot,
    level_stale_or_unbound,
    tank_empty,
    tank_full,
    tank_not_empty,
)


# Каналы irrigation_start из ZoneLogicProfileNormalizer::TWO_TANK_REQUIRED_PLAN_CHANNELS.
_FEED_ONLY_REQUIRED_CHANNELS = ("valve_solution_supply", "valve_irrigation", "pump_main")
# Интервал и окно наблюдения — коррекция уже запущена, новый вызов не нужен.
_CORRECTION_IN_PROGRESS = frozenset(
    {
        "reagent_min_interval",
        "reagent_observation_pending",
    }
)

_DRAIN_OR_RETURN_CHANNELS = frozenset(
    {
        "valve_drain",
        "valve_drain_return",
        "pump_drain",
        "valve_return",
        "drain_return",
    }
)


@dataclass(frozen=True)
class MutationDecision:
    kind: str | None
    reason_code: str
    human_message: str
    failed: bool
    create_task: bool
    create_alert: bool
    water_demand: WaterDemandDecision | None = None
    shot_kind: str | None = None
    duration_sec: int | None = None
    dose_ml: float | None = None
    reagent: str | None = None
    dose_decision: DoseDecision | None = None
    drain_volume_l: float | None = None
    drain_duration_ms: int | None = None


def has_feed_only_circuit(*, plan: ZonePlan) -> bool:
    """Привязка контура feed_only — шаги irrigation_start с обязательными каналами."""
    try:
        steps = require_plan_steps(plan, plan_key="irrigation_start")
    except ZonePlanConfigurationError:
        return False
    present = {
        str(step.get("channel") or "").strip()
        for step in steps
        if str(step.get("channel") or "").strip()
    }
    if not all(channel in present for channel in _FEED_ONLY_REQUIRED_CHANNELS):
        return False
    if present & _DRAIN_OR_RETURN_CHANNELS:
        return False
    for step in steps:
        if not str(step.get("node_uid") or "").strip():
            return False
    return True


def _steps_bound(*, plan: ZonePlan, plan_key: str) -> bool:
    try:
        steps = require_plan_steps(plan, plan_key=plan_key)
    except ZonePlanConfigurationError:
        return False
    return all(str(step.get("node_uid") or "").strip() for step in steps)


def has_clean_fill_steps(*, plan: ZonePlan) -> bool:
    return _steps_bound(plan=plan, plan_key="clean_fill_start") and _steps_bound(
        plan=plan, plan_key="clean_fill_stop"
    )


def has_solution_fill_steps(*, plan: ZonePlan) -> bool:
    return _steps_bound(plan=plan, plan_key="solution_fill_start") and _steps_bound(
        plan=plan, plan_key="solution_fill_stop"
    )


def decide_mutation(
    *,
    plan: ZonePlan,
    phase: PhaseTargets,
    telemetry: ZoneTelemetrySnapshot,
    now: datetime,
    emergency_stop: bool,
    last_shot: ShotMark | None,
    last_planned_shot_at: datetime | None,
    extra_used_in_half_interval: bool,
    successful_shots_in_window: int,
    integral: LightIntegralCursor,
    new_light_samples: tuple[TelemetrySample, ...],
    ec_state: DoseReagentState | None = None,
    ph_up_state: DoseReagentState | None = None,
    ph_down_state: DoseReagentState | None = None,
) -> MutationDecision:
    """Первая подходящая мутация §2.1. E-STOP обрабатывается до вызова."""
    if emergency_stop:
        return MutationDecision(
            kind=None,
            reason_code="emergency_stop_activated",
            human_message="E-STOP активен — мутации воды нет",
            failed=True,
            create_task=False,
            create_alert=True,
        )

    if not has_feed_only_circuit(plan=plan):
        return MutationDecision(
            kind=None,
            reason_code="feed_only_circuit_unbound",
            human_message="Нет привязки контура feed_only",
            failed=True,
            create_task=False,
            create_alert=True,
        )

    if level_stale_or_unbound(reading=telemetry.level_solution_min):
        return MutationDecision(
            kind=None,
            reason_code="level_solution_min_unbound_or_stale",
            human_message="Нет привязки level_solution_min или проба старше окна свежести",
            failed=True,
            create_task=False,
            create_alert=True,
        )

    clean_empty = tank_empty(reading=telemetry.level_clean_min)
    feed_empty = tank_empty(reading=telemetry.level_solution_min)
    clean_ok = tank_not_empty(reading=telemetry.level_clean_min)
    feed_full = tank_full(reading=telemetry.level_solution_max)

    if feed_empty and clean_empty and has_clean_fill_steps(plan=plan):
        return MutationDecision(
            kind="supply_to_clean",
            reason_code="supply_to_clean",
            human_message="Оба бака пусты — сначала набор чистой воды, насос полива не включается",
            failed=False,
            create_task=True,
            create_alert=False,
        )

    if feed_empty and clean_empty:
        return MutationDecision(
            kind=None,
            reason_code="both_tanks_empty",
            human_message="Оба бака пусты и нет шагов набора чистой воды — насос не включается",
            failed=True,
            create_task=False,
            create_alert=True,
        )

    if clean_empty and has_clean_fill_steps(plan=plan):
        return MutationDecision(
            kind="supply_to_clean",
            reason_code="supply_to_clean",
            human_message="Пустой clean — набор чистой воды",
            failed=False,
            create_task=True,
            create_alert=False,
        )

    if clean_empty and not has_clean_fill_steps(plan=plan):
        return MutationDecision(
            kind=None,
            reason_code="clean_fill_steps_missing",
            human_message="Пустой clean, но шагов clean_fill нет — клапан не выдумывается",
            failed=True,
            create_task=False,
            create_alert=True,
        )

    if feed_empty:
        if clean_ok and has_solution_fill_steps(plan=plan):
            return MutationDecision(
                kind="clean_to_feed",
                reason_code="clean_to_feed_empty",
                human_message="Пустой feed — долив из clean",
                failed=False,
                create_task=True,
                create_alert=False,
            )
        return MutationDecision(
            kind=None,
            reason_code="solution_fill_steps_missing",
            human_message="Пустой feed, но шагов solution_fill нет",
            failed=True,
            create_task=False,
            create_alert=True,
        )

    ec_high = _ec_above_corridor(
        phase=phase,
        telemetry=telemetry,
        now=now,
        telemetry_max_age_sec=plan.telemetry_max_age_sec,
    )
    if ec_high:
        if feed_full:
            return _decide_full_tank_drain(
                plan=plan,
                phase=phase,
                telemetry=telemetry,
                now=now,
            )
        if has_solution_fill_steps(plan=plan):
            return MutationDecision(
                kind="clean_to_feed",
                reason_code="ec_high_dilute",
                human_message="EC выше коридора — долив clean без кадра и соли",
                failed=False,
                create_task=True,
                create_alert=False,
            )
        return MutationDecision(
            kind=None,
            reason_code="ec_high_no_dilute_steps",
            human_message="EC выше коридора, шагов долива нет",
            failed=False,
            create_task=False,
            create_alert=True,
        )

    dose = _decide_dose(
        plan=plan,
        phase=phase,
        telemetry=telemetry,
        now=now,
        ec_state=ec_state,
        ph_up_state=ph_up_state,
        ph_down_state=ph_down_state,
    )
    if dose.blocks_shot:
        return MutationDecision(
            kind=None,
            reason_code=dose.reason_code,
            human_message=dose.human_message,
            failed=False,
            create_task=False,
            create_alert=False,
            dose_decision=dose,
        )
    if dose.allow_pulse and dose.dose_ml is not None and dose.reagent:
        if _solution_outside_corridor(
            phase=phase,
            telemetry=telemetry,
            now=now,
            telemetry_max_age_sec=plan.telemetry_max_age_sec,
        ) and not _steps_bound(plan=plan, plan_key="sensor_mode_activate"):
            return MutationDecision(
                kind=None,
                reason_code="solution_not_ready",
                human_message=(
                    "Раствор вне коридора, но нет шагов sensor_mode_activate — "
                    "импульс не публикуется. Полив остановлен, ждём решения."
                ),
                failed=False,
                create_task=False,
                create_alert=True,
                dose_ml=float(dose.dose_ml),
                reagent=str(dose.reagent),
                dose_decision=dose,
            )
        return MutationDecision(
            kind="dose_pulse",
            reason_code=dose.reason_code,
            human_message=dose.human_message,
            failed=False,
            create_task=True,
            create_alert=False,
            dose_ml=float(dose.dose_ml),
            reagent=str(dose.reagent),
            dose_decision=dose,
        )

    unready = _solution_outside_corridor(
        phase=phase,
        telemetry=telemetry,
        now=now,
        telemetry_max_age_sec=plan.telemetry_max_age_sec,
    )
    if unready is not None:
        correcting = dose.reason_code in _CORRECTION_IN_PROGRESS
        return MutationDecision(
            kind=None,
            reason_code="solution_correcting" if correcting else "solution_not_ready",
            human_message=(
                f"{unready} Коррекция уже идёт — полив ждёт следующий импульс."
                if correcting
                else (
                    f"{unready} Импульс в этом тике не публикуется "
                    f"({dose.reason_code}). Полив остановлен, ждём решения."
                )
            ),
            failed=False,
            create_task=False,
            create_alert=not correcting,
            dose_decision=dose,
        )

    room = assess_drain_room(
        circuit_alive=_circuit_alive(plan=plan, telemetry=telemetry),
        level_drain_max_value=telemetry.level_drain_max.value,
        level_drain_max_fresh=bool(
            telemetry.level_drain_max.bound and telemetry.level_drain_max.fresh
        ),
        volume_ml=phase.volume_ml,
        duration_sec=phase.duration_sec,
        pump_ml_per_sec=plan.pump_main_ml_per_sec,
    )
    if room.status == "full" or room.reason_code == "drain_room_level_unseen":
        # Свежий не-max разрешает кадр. Протухший уровень стока кадр не открывает.
        # Нет объёма кадра (drain_room_volume_unseen) при свежем не-max кадр не держит.
        return MutationDecision(
            kind=None,
            reason_code=room.reason_code,
            human_message=room.human_message,
            failed=False,
            create_task=False,
            create_alert=room.reason_code == "drain_room_level_unseen",
            dose_decision=dose,
        )

    demand = evaluate_water_demand(
        phase=phase,
        now=now,
        timezone_name=plan.timezone,
        telemetry_max_age_sec=plan.telemetry_max_age_sec,
        last_shot=last_shot,
        last_planned_shot_at=last_planned_shot_at,
        extra_used_in_half_interval=extra_used_in_half_interval,
        successful_shots_in_window=successful_shots_in_window,
        integral=integral,
        new_light_samples=new_light_samples,
        soil_moisture=telemetry.soil_moisture,
        temp_air=telemetry.temp_air,
        humidity_air=telemetry.humidity_air,
        emergency_stop=False,
        feed_empty=False,
        ec_blocks_shot=False,
    )
    alert = bool(dose.critical_alert)
    if demand.shoot:
        duration = int(phase.duration_sec or 0)
        return MutationDecision(
            kind="feed_to_plants",
            reason_code=demand.reason_code,
            human_message=demand.human_message,
            failed=False,
            create_task=True,
            create_alert=alert,
            water_demand=demand,
            shot_kind=demand.kind,
            duration_sec=duration if duration > 0 else None,
            dose_decision=dose,
        )

    if alert:
        return MutationDecision(
            kind=None,
            reason_code=dose.reason_code,
            human_message=dose.human_message,
            failed=False,
            create_task=False,
            create_alert=True,
            water_demand=demand,
            dose_decision=dose,
        )

    return MutationDecision(
        kind=None,
        reason_code=demand.reason_code,
        human_message=demand.human_message,
        failed=False,
        create_task=False,
        create_alert=False,
        water_demand=demand,
        dose_decision=dose,
    )


def _circuit_alive(*, plan: ZonePlan, telemetry: ZoneTelemetrySnapshot) -> bool:
    return has_drain_circuit(
        level_drain_min_bound=telemetry.level_drain_min.bound,
        level_drain_max_bound=telemetry.level_drain_max.bound,
        ec_drain_bound=telemetry.ec_drain is not None,
        has_feed_to_drain_steps=has_feed_to_drain_plan_steps(
            command_plans=plan.command_plans
        ),
    )


def _decide_full_tank_drain(
    *,
    plan: ZonePlan,
    phase: PhaseTargets,
    telemetry: ZoneTelemetrySnapshot,
    now: datetime,
) -> MutationDecision:
    circuit = _circuit_alive(plan=plan, telemetry=telemetry)
    ec_fresh = _sample_fresh(
        sample=telemetry.ec_feed,
        now=now,
        telemetry_max_age_sec=plan.telemetry_max_age_sec,
    )
    portion = evaluate_portion_for_full_tank(
        circuit_alive=circuit,
        nutrient_solution_volume_l=plan.nutrient_solution_volume_l,
        ec_feed=float(telemetry.ec_feed.value) if telemetry.ec_feed is not None else None,
        ec_feed_fresh=ec_fresh,
        ec_target=phase.ec_target,
        ec_clean=plan.ec_clean,
    )
    if not portion.allow or portion.volume_l is None:
        return MutationDecision(
            kind=None,
            reason_code=portion.reason_code,
            human_message=portion.human_message,
            failed=False,
            create_task=False,
            create_alert=portion.critical_alert,
        )
    duration_ms = duration_ms_for_portion_l(
        volume_l=float(portion.volume_l),
        pump_ml_per_sec=plan.pump_main_ml_per_sec,
    )
    if duration_ms is None:
        return MutationDecision(
            kind=None,
            reason_code="drain_portion_pump_rate_missing",
            human_message=(
                "Нет расхода насоса для доли слива — секунды из литров не выдумываем"
            ),
            failed=False,
            create_task=False,
            create_alert=True,
        )
    return MutationDecision(
        kind="feed_to_drain",
        reason_code=portion.reason_code,
        human_message=portion.human_message,
        failed=False,
        create_task=True,
        create_alert=False,
        drain_volume_l=float(portion.volume_l),
        drain_duration_ms=int(duration_ms),
    )


def _decide_dose(
    *,
    plan: ZonePlan,
    phase: PhaseTargets,
    telemetry: ZoneTelemetrySnapshot,
    now: datetime,
    ec_state: DoseReagentState | None,
    ph_up_state: DoseReagentState | None,
    ph_down_state: DoseReagentState | None,
) -> DoseDecision:
    stale_setting = (
        plan.dose.stale_ec_allows_shot
        if plan.dose is not None
        else plan.stale_ec_allows_shot
    )
    if plan.dose is None:
        empty = ControllerDoseParams(
            gain=None,
            max_dose_ml=None,
            min_interval_sec=None,
            decision_window_sec=None,
            min_effect_fraction=None,
            no_effect_limit=None,
            min_dose_ms=None,
            ml_per_sec=None,
        )
        ec_params = empty
        ph_params = empty
        ph_up_gain = None
        ph_down_gain = None
    else:
        ec_params = plan.dose.ec
        ph_params = plan.dose.ph
        ph_up_gain = plan.dose.ph_up_gain
        ph_down_gain = plan.dose.ph_down_gain
    return evaluate_tick_dose(
        ec_sample=telemetry.ec_feed,
        ph_sample=telemetry.ph_feed,
        ec_target=phase.ec_target,
        ph_target=phase.ph_target,
        ec_unit=phase.ec_unit,
        ph_unit=None,
        ec_params=ec_params,
        ph_params=ph_params,
        now=now,
        telemetry_max_age_sec=plan.telemetry_max_age_sec,
        stale_ec_allows_shot=stale_setting,
        ec_state=ec_state,
        ph_up_state=ph_up_state,
        ph_down_state=ph_down_state,
        ph_up_gain=ph_up_gain,
        ph_down_gain=ph_down_gain,
        ec_drain_sample=telemetry.ec_drain,
        ec_max=phase.ec_max,
    )


def _solution_outside_corridor(
    *,
    phase: PhaseTargets,
    telemetry: ZoneTelemetrySnapshot,
    now: datetime,
    telemetry_max_age_sec: int,
) -> str | None:
    """Свежий pH или EC вне коридора фазы. Протухшая проба кадр этим фактом не держит."""
    parts: list[str] = []
    ph = telemetry.ph_feed
    if (
        ph is not None
        and _sample_fresh(sample=ph, now=now, telemetry_max_age_sec=telemetry_max_age_sec)
        and _value_outside_corridor(
            value=float(ph.value),
            low=phase.ph_min,
            high=phase.ph_max,
        )
    ):
        parts.append(
            f"pH {float(ph.value):g} вне коридора {_corridor_label(phase.ph_min, phase.ph_max)}."
        )
    ec = telemetry.ec_feed
    if (
        ec is not None
        and _sample_fresh(sample=ec, now=now, telemetry_max_age_sec=telemetry_max_age_sec)
        and _value_outside_corridor(
            value=float(ec.value),
            low=phase.ec_min,
            high=phase.ec_max,
        )
    ):
        parts.append(
            f"EC {float(ec.value):g} вне коридора {_corridor_label(phase.ec_min, phase.ec_max)}."
        )
    if not parts:
        return None
    return "Раствор для полива не готов: " + " ".join(parts)


def _corridor_label(low: float | None, high: float | None) -> str:
    if low is not None and high is not None:
        return f"{float(low):g}–{float(high):g}"
    if low is not None:
        return f"не ниже {float(low):g}"
    if high is not None:
        return f"не выше {float(high):g}"
    return "фазы"


def _value_outside_corridor(
    *,
    value: float,
    low: float | None,
    high: float | None,
) -> bool:
    if low is None and high is None:
        return False
    if low is not None and value < float(low):
        return True
    if high is not None and value > float(high):
        return True
    return False


def _ec_above_corridor(
    *,
    phase: PhaseTargets,
    telemetry: ZoneTelemetrySnapshot,
    now: datetime,
    telemetry_max_age_sec: int,
) -> bool:
    """Свежий EC feed выше ec_max."""
    sample = telemetry.ec_feed
    if sample is None or phase.ec_max is None:
        return False
    if not _sample_fresh(
        sample=sample, now=now, telemetry_max_age_sec=telemetry_max_age_sec
    ):
        return False
    return float(sample.value) > float(phase.ec_max)


def _sample_fresh(
    *,
    sample: TelemetrySample | None,
    now: datetime,
    telemetry_max_age_sec: int,
) -> bool:
    if sample is None:
        return False
    ts = sample.ts
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    now_naive = now
    if now_naive.tzinfo is not None:
        now_naive = now_naive.astimezone(timezone.utc).replace(tzinfo=None)
    return now_naive - ts <= timedelta(seconds=int(telemetry_max_age_sec))


__all__ = [
    "MutationDecision",
    "decide_mutation",
    "has_feed_only_circuit",
    "has_clean_fill_steps",
    "has_solution_fill_steps",
]
