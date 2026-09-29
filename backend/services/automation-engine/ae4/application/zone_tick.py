"""Тик зон ae4: класс безопасности + одна мутация воды."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from ae4.application.mutation_decision import MutationDecision, decide_mutation
from ae4.application.safety_stop import emergency_off_dosing_and_tract
from ae4.application.solution_heat import apply_solution_heat
from ae4.config.zone_plan import ZonePlanConfigurationError, load_zone_plan
from ae4.domain.dose_policy import resolve_observation
from ae4.domain.light_policy import LightPolicyConfigError, apply_light_policy
from ae4.domain.water_demand import advance_light_integral
from ae4.infrastructure.climate_wake import wake_greenhouse_climate_ticks
from ae4.infrastructure.failure_report import (
    report_critical_call,
    report_exception,
    report_failure,
    report_planting_decision,
)
from ae4.infrastructure.phase_loader import PhaseLoadError, load_planting_state
from ae4.infrastructure.repositories.automation_task_repository import (
    PgAutomationTaskRepository,
)
from ae4.infrastructure.repositories.dose_state_repository import (
    load_reagent_state,
    save_observation_state,
)
from ae4.infrastructure.repositories.zone_lease_repository import PgZoneLeaseRepository
from ae4.infrastructure.shot_events import (
    load_light_integral_cursor,
    load_shot_marks,
    save_light_integral_cursor,
)
from ae4.infrastructure.zone_telemetry import load_zone_telemetry
from common.db import fetch
from common.history_logger_gateway import HistoryLoggerGateway

logger = logging.getLogger(__name__)

_ESTOP_TYPE = "EMERGENCY_STOP_ACTIVATED"


async def list_ae4_zone_ids() -> list[tuple[int, int]]:
    """(zone_id, greenhouse_id) для зон automation_runtime=ae4."""
    rows = await fetch(
        """
        SELECT id AS zone_id, greenhouse_id
        FROM zones
        WHERE automation_runtime IS DISTINCT FROM 'ae3'
        ORDER BY id ASC
        """
    )
    return [(int(row["zone_id"]), int(row["greenhouse_id"])) for row in rows]


async def zone_has_active_work(
    *,
    zone_id: int,
    task_repository: PgAutomationTaskRepository,
    lease_repository: PgZoneLeaseRepository,
    now: datetime,
) -> bool:
    active = await task_repository.get_active_for_zone(zone_id=zone_id)
    if active is not None:
        return True
    lease = await lease_repository.get(zone_id=zone_id)
    if lease is None:
        return False
    until = lease.leased_until
    now_naive = now
    if now_naive.tzinfo is not None:
        now_naive = now_naive.astimezone(timezone.utc).replace(tzinfo=None)
    if until.tzinfo is not None:
        until = until.astimezone(timezone.utc).replace(tzinfo=None)
    return until > now_naive


async def has_active_emergency_stop(*, zone_id: int) -> bool:
    rows = await fetch(
        """
        SELECT id
        FROM zone_events
        WHERE zone_id = $1
          AND type = $2
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        zone_id,
        _ESTOP_TYPE,
    )
    return bool(rows)


async def tick_ae4_zones(
    *,
    now: datetime,
    task_repository: PgAutomationTaskRepository,
    lease_repository: PgZoneLeaseRepository,
    gateway: HistoryLoggerGateway,
    wake_climate: bool = True,
) -> dict[str, Any]:
    """Обходит зоны ae4: безопасность каждый проход, мутация — одна задача due_at=now."""
    zones = await list_ae4_zone_ids()
    greenhouse_ids: set[int] = set()
    created = 0
    paused = 0
    failed = 0
    for zone_id, greenhouse_id in zones:
        greenhouse_ids.add(greenhouse_id)
        outcome = await tick_one_zone(
            zone_id=zone_id,
            now=now,
            task_repository=task_repository,
            lease_repository=lease_repository,
            gateway=gateway,
        )
        if outcome == "created":
            created += 1
        elif outcome == "paused":
            paused += 1
        elif outcome == "failed":
            failed += 1
    climate_woken: list[int] = []
    if wake_climate and greenhouse_ids:
        climate_woken = await wake_greenhouse_climate_ticks(
            greenhouse_ids=greenhouse_ids,
            now=now,
        )
    return {
        "zones": len(zones),
        "created": created,
        "paused": paused,
        "failed": failed,
        "climate_woken": climate_woken,
    }


async def tick_one_zone(
    *,
    zone_id: int,
    now: datetime,
    task_repository: PgAutomationTaskRepository,
    lease_repository: PgZoneLeaseRepository,
    gateway: HistoryLoggerGateway,
) -> str:
    """Один проход зоны. Возвращает created|paused|failed|skipped|manual."""
    try:
        plan = await load_zone_plan(zone_id=zone_id)
        planting = await load_planting_state(zone_id=zone_id)
    except (ZonePlanConfigurationError, PhaseLoadError) as exc:
        reason = getattr(exc, "reason_code", "zone_plan_error")
        await report_failure(
            zone_id=zone_id,
            reason_code=str(reason),
            human_message=str(exc),
            error_code=str(reason),
        )
        return "failed"

    if plan.control_mode == "manual":
        # Новых команд нет: уже запущенный насос гаснет таймером узла.
        return "manual"

    mutation_busy = await zone_has_active_work(
        zone_id=zone_id,
        task_repository=task_repository,
        lease_repository=lease_repository,
        now=now,
    )

    emergency = await has_active_emergency_stop(zone_id=zone_id)
    # Класс безопасности: E-STOP гасит тракт и дозаторы без мутации.
    if emergency:
        pseudo_task_id = 0
        try:
            await emergency_off_dosing_and_tract(
                plan=plan,
                gateway=gateway,
                task_id=pseudo_task_id,
                zone_id=zone_id,
                now=now,
            )
        except Exception as exc:
            logger.exception(
                "AE4: сбой аварийного OFF",
                extra={"zone_id": zone_id},
            )
            await report_failure(
                zone_id=zone_id,
                reason_code="emergency_stop_off_failed",
                human_message=f"E-STOP: не удалось погасить исполнительные: {exc}",
                grow_cycle_id=plan.grow_cycle_id,
                error_code="emergency_stop_off_failed",
            )
            return "failed"
        await report_failure(
            zone_id=zone_id,
            reason_code="emergency_stop_activated",
            human_message="E-STOP активен — автоматика fail-closed",
            grow_cycle_id=plan.grow_cycle_id,
            error_code="emergency_stop_activated",
        )
        return "failed"

    # Свет: OFF — класс безопасности даже при занятой мутации; ON может ждать.
    try:
        await apply_light_policy(
            plan=plan,
            phase=planting.phase,
            gateway=gateway,
            task_id=0,
            zone_id=zone_id,
            now=now,
            mutation_busy=mutation_busy,
        )
    except LightPolicyConfigError as exc:
        await report_failure(
            zone_id=zone_id,
            reason_code=exc.reason_code,
            human_message=str(exc),
            grow_cycle_id=plan.grow_cycle_id,
            error_code=exc.reason_code,
        )
        return "failed"
    except Exception as exc:
        await report_exception(
            zone_id=zone_id,
            reason_code="light_policy_failed",
            human_message="Сбой политики света",
            exc=exc,
            grow_cycle_id=plan.grow_cycle_id,
        )
        return "failed"

    # Нагрев: аварийный OFF — класс безопасности (даже при занятой мутации).
    heat_telemetry = None
    try:
        heat_telemetry = await load_zone_telemetry(
            zone_id=zone_id,
            now=now,
            telemetry_max_age_sec=plan.telemetry_max_age_sec,
        )
        await apply_solution_heat(
            plan=plan,
            phase=planting.phase,
            gateway=gateway,
            zone_id=zone_id,
            now=now,
            solution_temp=heat_telemetry.solution_temp,
            mutation_busy=True,
            allow_on=False,
        )
    except Exception as exc:
        await report_exception(
            zone_id=zone_id,
            reason_code="solution_heat_failed",
            human_message="Сбой нагрева раствора",
            exc=exc,
            grow_cycle_id=plan.grow_cycle_id,
        )
        return "failed"

    if mutation_busy:
        return "skipped"

    telemetry = heat_telemetry or await load_zone_telemetry(
        zone_id=zone_id,
        now=now,
        telemetry_max_age_sec=plan.telemetry_max_age_sec,
    )
    ec_state, ph_up_state, ph_down_state = await _load_and_resolve_dose_states(
        zone_id=zone_id,
        plan=plan,
        telemetry=telemetry,
        now=now,
    )
    last_shot, last_planned, extra_used, successful = await load_shot_marks(
        zone_id=zone_id,
        phase_id=planting.phase.phase_id,
        now=now,
        timezone_name=plan.timezone,
        phase=planting.phase,
    )
    stored_cursor = await load_light_integral_cursor(
        zone_id=zone_id,
        phase_id=planting.phase.phase_id,
        phase_started_at=planting.phase.started_at,
        unit=planting.phase.light_integral_unit,
    )
    integral = advance_light_integral(
        cursor=stored_cursor,
        samples=telemetry.light_samples,
        now=now,
        telemetry_max_age_sec=plan.telemetry_max_age_sec,
        target_unit=planting.phase.light_integral_unit,
        phase_started_at=planting.phase.started_at,
    )
    decision = decide_mutation(
        plan=plan,
        phase=planting.phase,
        telemetry=telemetry,
        now=now,
        emergency_stop=False,
        last_shot=last_shot,
        last_planned_shot_at=last_planned,
        extra_used_in_half_interval=extra_used,
        successful_shots_in_window=successful,
        integral=integral,
        new_light_samples=(),
        ec_state=ec_state,
        ph_up_state=ph_up_state,
        ph_down_state=ph_down_state,
    )
    await save_light_integral_cursor(
        zone_id=zone_id,
        phase_id=planting.phase.phase_id,
        cursor=integral,
    )
    outcome = await _apply_decision(
        zone_id=zone_id,
        grow_cycle_id=plan.grow_cycle_id,
        now=now,
        decision=decision,
        task_repository=task_repository,
    )
    # ON нагрева не делит тик с кадром/дозой/сливом.
    if outcome != "created":
        try:
            await apply_solution_heat(
                plan=plan,
                phase=planting.phase,
                gateway=gateway,
                zone_id=zone_id,
                now=now,
                solution_temp=telemetry.solution_temp,
                mutation_busy=False,
                allow_on=True,
            )
        except Exception as exc:
            await report_exception(
                zone_id=zone_id,
                reason_code="solution_heat_failed",
                human_message="Сбой включения нагрева раствора",
                exc=exc,
                grow_cycle_id=plan.grow_cycle_id,
            )
    return outcome


async def _load_and_resolve_dose_states(
    *,
    zone_id: int,
    plan: Any,
    telemetry: Any,
    now: datetime,
) -> tuple[Any, Any, Any]:
    ec_state = await load_reagent_state(zone_id=zone_id, reagent="nutrition")
    ph_up_state = await load_reagent_state(zone_id=zone_id, reagent="ph_up")
    ph_down_state = await load_reagent_state(zone_id=zone_id, reagent="ph_down")
    dose = getattr(plan, "dose", None)
    if dose is not None and ec_state is not None and ec_state.observation == "pending":
        resolved = resolve_observation(
            state=ec_state,
            now=now,
            sample=telemetry.ec_feed,
            telemetry_max_age_sec=plan.telemetry_max_age_sec,
            decision_window_sec=dose.ec.decision_window_sec,
            gain=dose.ec.gain,
            min_effect_fraction=dose.ec.min_effect_fraction,
        )
        if resolved.observation != ec_state.observation or resolved.no_effect_count != ec_state.no_effect_count:
            await save_observation_state(zone_id=zone_id, state=resolved)
        ec_state = resolved
    for reagent, state, gain_attr in (
        ("ph_up", ph_up_state, "ph_up_gain"),
        ("ph_down", ph_down_state, "ph_down_gain"),
    ):
        if dose is None or state is None or state.observation != "pending":
            continue
        gain = getattr(dose, gain_attr, None)
        resolved = resolve_observation(
            state=state,
            now=now,
            sample=telemetry.ph_feed,
            telemetry_max_age_sec=plan.telemetry_max_age_sec,
            decision_window_sec=dose.ph.decision_window_sec,
            gain=gain,
            min_effect_fraction=dose.ph.min_effect_fraction,
        )
        if resolved.observation != state.observation or resolved.no_effect_count != state.no_effect_count:
            await save_observation_state(zone_id=zone_id, state=resolved)
        if reagent == "ph_up":
            ph_up_state = resolved
        else:
            ph_down_state = resolved
    return ec_state, ph_up_state, ph_down_state


async def _apply_decision(
    *,
    zone_id: int,
    grow_cycle_id: int,
    now: datetime,
    decision: MutationDecision,
    task_repository: PgAutomationTaskRepository,
) -> str:
    if decision.failed:
        await report_failure(
            zone_id=zone_id,
            reason_code=decision.reason_code,
            human_message=decision.human_message,
            grow_cycle_id=grow_cycle_id,
            error_code=decision.reason_code,
            dedupe_key=f"ae4-fail:{zone_id}:{decision.reason_code}",
        )
        return "failed"

    # Три no-effect: импульс стоп, critical без failed=true (E249 / §11.3).
    if (
        decision.create_alert
        and decision.dose_decision is not None
        and decision.dose_decision.critical_alert
    ):
        await report_critical_call(
            zone_id=zone_id,
            reason_code=decision.dose_decision.reason_code,
            human_message=decision.dose_decision.human_message,
            grow_cycle_id=grow_cycle_id,
            details={"reagent": decision.dose_decision.reagent},
            dedupe_key=(
                f"ae4-no-effect:{zone_id}:{decision.dose_decision.reagent or 'reagent'}"
            ),
        )

    if decision.create_task and decision.kind:
        meta: dict[str, Any] = {
            "kind": decision.kind,
            "reason_code": decision.reason_code,
            "human_message": decision.human_message,
            "grow_cycle_id": grow_cycle_id,
        }
        if decision.shot_kind:
            meta["shot_kind"] = decision.shot_kind
        if decision.duration_sec is not None:
            meta["duration_sec"] = decision.duration_sec
        if decision.dose_ml is not None:
            meta["dose_ml"] = decision.dose_ml
        if decision.reagent:
            meta["reagent"] = decision.reagent
        if decision.drain_duration_ms is not None:
            meta["drain_duration_ms"] = decision.drain_duration_ms
        if decision.drain_volume_l is not None:
            meta["drain_volume_l"] = decision.drain_volume_l
        task = await task_repository.create_pending_if_idle(
            zone_id=zone_id,
            idempotency_key=f"ae4-{decision.kind}-{zone_id}-{uuid4().hex[:12]}",
            task_type="irrigation_start",
            current_stage=decision.kind,
            workflow_phase="idle",
            scheduled_for=now,
            due_at=now,
            now=now,
            intent_meta=meta,
        )
        if task is None:
            return "skipped"
        return "created"

    # Пауза политики: повтор reason_code без новой ae_tasks и без нового zone_events.
    critical_already = bool(
        decision.dose_decision is not None and decision.dose_decision.critical_alert
    )
    level_unseen = decision.reason_code == "drain_room_level_unseen"
    if level_unseen:
        await report_critical_call(
            zone_id=zone_id,
            reason_code=decision.reason_code,
            human_message=decision.human_message,
            grow_cycle_id=grow_cycle_id,
            dedupe_key=f"ae4-drain-level:{zone_id}",
        )
    await report_planting_decision(
        zone_id=zone_id,
        reason_code=decision.reason_code,
        human_message=decision.human_message,
        grow_cycle_id=grow_cycle_id,
        create_alert=bool(decision.create_alert) and not critical_already and not level_unseen,
    )
    return "paused"


__all__ = [
    "list_ae4_zone_ids",
    "tick_ae4_zones",
    "tick_one_zone",
    "has_active_emergency_stop",
    "zone_has_active_work",
]
