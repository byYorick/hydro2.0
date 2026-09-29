"""Исполнение claimed-задачи AE4."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

from ae4.application.water_procedures import (
    run_clean_to_feed,
    run_feed_to_drain,
    run_feed_to_plants,
    run_supply_to_clean,
)
from ae4.application.dose_pulse import run_dose_pulse
from ae4.config.zone_plan import ZonePlanConfigurationError, load_zone_plan
from ae4.infrastructure.failure_report import (
    report_exception,
    report_failure,
    report_planting_decision,
)
from ae4.domain.water_demand import reset_integral_after_shot
from ae4.infrastructure.phase_loader import load_planting_state
from ae4.infrastructure.repositories.ae_command_repository import PgAeCommandRepository
from ae4.infrastructure.repositories.automation_task_repository import (
    PgAutomationTaskRepository,
)
from ae4.infrastructure.repositories.zone_lease_repository import PgZoneLeaseRepository
from ae4.infrastructure.shot_events import save_light_integral_cursor
from ae4.infrastructure.zone_telemetry import load_zone_telemetry
from common.history_logger_gateway import (
    CommandNotDoneError,
    HistoryLoggerGateway,
    build_ae4_cmd_id,
)

logger = logging.getLogger(__name__)

LEASE_TTL_SEC = 120
_MUTATION_KINDS = frozenset(
    {"supply_to_clean", "clean_to_feed", "feed_to_plants", "dose_pulse", "feed_to_drain"}
)


async def execute_claimed_task(
    *,
    claimed_task_id: int,
    zone_id: int,
    worker_owner: str,
    now: datetime,
    task_repository: PgAutomationTaskRepository,
    command_repository: PgAeCommandRepository,
    lease_repository: PgZoneLeaseRepository,
    gateway: HistoryLoggerGateway,
) -> None:
    """Исполняет одну claimed-задачу. Исключение и не-DONE → failure_report."""
    lease = await lease_repository.claim(
        zone_id=zone_id,
        owner=worker_owner,
        now=now,
        lease_ttl_sec=LEASE_TTL_SEC,
    )
    if lease is None:
        from ae4.infrastructure.metrics import ZONE_LEASE_LOST

        ZONE_LEASE_LOST.labels(zone_id=str(zone_id)).inc()
        await report_failure(
            zone_id=zone_id,
            reason_code="ae4_lease_lost",
            human_message="Не удалось взять lease зоны",
            task_id=claimed_task_id,
            error_code="ae4_lease_lost",
        )
        await task_repository.mark_failed(
            task_id=claimed_task_id,
            owner=worker_owner,
            error_code="ae4_lease_lost",
            error_message="Не удалось взять lease зоны",
            now=now,
        )
        return

    try:
        running = await task_repository.mark_running(
            task_id=claimed_task_id,
            owner=worker_owner,
            now=now,
        )
        if running is None:
            raise RuntimeError("Не удалось перевести задачу в running")

        meta = dict(running.intent_meta or {})
        kind = str(meta.get("kind") or "").strip()
        if kind == "probe_command":
            await _run_probe_command(
                task=running,
                meta=meta,
                worker_owner=worker_owner,
                now=now,
                task_repository=task_repository,
                command_repository=command_repository,
                gateway=gateway,
            )
            return

        if kind == "policy_pause":
            reason_code = str(meta.get("reason_code") or "").strip() or "policy_pause"
            human_message = str(meta.get("human_message") or "").strip()
            if not human_message:
                raise RuntimeError("policy_pause без human_message")
            grow_cycle_raw = meta.get("grow_cycle_id")
            grow_cycle_id = int(grow_cycle_raw) if grow_cycle_raw is not None else None
            await report_planting_decision(
                zone_id=zone_id,
                reason_code=reason_code,
                human_message=human_message,
                grow_cycle_id=grow_cycle_id,
            )
            await task_repository.mark_completed(
                task_id=claimed_task_id,
                owner=worker_owner,
                now=now,
            )
            return

        if kind in _MUTATION_KINDS:
            await _run_mutation(
                task=running,
                meta=meta,
                kind=kind,
                worker_owner=worker_owner,
                now=now,
                task_repository=task_repository,
                command_repository=command_repository,
                gateway=gateway,
            )
            return

        # Чужая pending (в т.ч. от диспетчера) — fail-closed, без машины стадий AE3.
        await report_failure(
            zone_id=zone_id,
            reason_code="ae4_foreign_task_rejected",
            human_message=(
                f"Задача kind={kind or running.task_type} не исполняется воркером AE4"
            ),
            task_id=claimed_task_id,
            error_code="ae4_foreign_task_rejected",
        )
        await task_repository.mark_failed(
            task_id=claimed_task_id,
            owner=worker_owner,
            error_code="ae4_foreign_task_rejected",
            error_message=f"unsupported kind={kind or running.task_type}",
            now=now,
        )
    except CommandNotDoneError as exc:
        await report_failure(
            zone_id=zone_id,
            reason_code="ae4_command_not_done",
            human_message=str(exc),
            task_id=claimed_task_id,
            error_code="ae4_command_not_done",
            details={"cmd_id": exc.cmd_id, "status": exc.status},
        )
        await task_repository.mark_failed(
            task_id=claimed_task_id,
            owner=worker_owner,
            error_code="ae4_command_not_done",
            error_message=str(exc),
            now=now,
        )
    except ZonePlanConfigurationError as exc:
        await report_failure(
            zone_id=zone_id,
            reason_code=exc.reason_code,
            human_message=str(exc),
            task_id=claimed_task_id,
            error_code=exc.reason_code,
        )
        await task_repository.mark_failed(
            task_id=claimed_task_id,
            owner=worker_owner,
            error_code=exc.reason_code,
            error_message=str(exc),
            now=now,
        )
    except Exception as exc:
        await report_exception(
            zone_id=zone_id,
            reason_code="ae4_task_exception",
            human_message=f"Исключение при исполнении задачи: {exc}",
            exc=exc,
            task_id=claimed_task_id,
        )
        await task_repository.mark_failed(
            task_id=claimed_task_id,
            owner=worker_owner,
            error_code="ae4_task_exception",
            error_message=str(exc),
            now=now,
        )
    finally:
        await lease_repository.release(zone_id=zone_id, owner=worker_owner)


async def _run_mutation(
    *,
    task: Any,
    meta: Mapping[str, Any],
    kind: str,
    worker_owner: str,
    now: datetime,
    task_repository: PgAutomationTaskRepository,
    command_repository: PgAeCommandRepository,
    gateway: HistoryLoggerGateway,
) -> None:
    plan = await load_zone_plan(zone_id=task.zone_id)
    if plan.control_mode == "manual":
        await report_planting_decision(
            zone_id=task.zone_id,
            reason_code="control_mode_manual",
            human_message="control_mode=manual — новых команд нет",
            grow_cycle_id=plan.grow_cycle_id,
        )
        await task_repository.mark_completed(
            task_id=task.id,
            owner=worker_owner,
            now=now,
        )
        return

    await task_repository.mark_waiting_command(
        task_id=task.id,
        owner=worker_owner,
        now=now,
    )

    if kind == "supply_to_clean":
        await run_supply_to_clean(
            plan=plan,
            gateway=gateway,
            command_repository=command_repository,
            task_id=task.id,
            zone_id=task.zone_id,
            now=now,
        )
    elif kind == "clean_to_feed":
        await run_clean_to_feed(
            plan=plan,
            gateway=gateway,
            command_repository=command_repository,
            task_id=task.id,
            zone_id=task.zone_id,
            now=now,
        )
    elif kind == "feed_to_plants":
        planting = await load_planting_state(zone_id=task.zone_id)
        duration_sec = int(meta.get("duration_sec") or planting.phase.duration_sec or 0)
        if duration_sec <= 0:
            raise ZonePlanConfigurationError(
                reason_code="irrigation_duration_missing",
                message="Нет duration_sec фазы для кадра",
            )
        shot_kind = str(meta.get("shot_kind") or "extra").strip() or "extra"
        reason_code = str(meta.get("reason_code") or "feed_to_plants").strip()
        await run_feed_to_plants(
            plan=plan,
            gateway=gateway,
            command_repository=command_repository,
            task_id=task.id,
            zone_id=task.zone_id,
            now=now,
            duration_sec=duration_sec,
            shot_kind=shot_kind,
            reason_code=reason_code,
            grow_cycle_id=plan.grow_cycle_id,
            phase_id=planting.phase.phase_id,
        )
        await save_light_integral_cursor(
            zone_id=task.zone_id,
            phase_id=planting.phase.phase_id,
            cursor=reset_integral_after_shot(phase=planting.phase, shot_at=now),
        )
    elif kind == "feed_to_drain":
        duration_ms = int(meta.get("drain_duration_ms") or 0)
        if duration_ms <= 0:
            raise ZonePlanConfigurationError(
                reason_code="drain_portion_duration_missing",
                message="feed_to_drain без drain_duration_ms",
            )
        await run_feed_to_drain(
            plan=plan,
            gateway=gateway,
            command_repository=command_repository,
            task_id=task.id,
            zone_id=task.zone_id,
            now=now,
            duration_ms=duration_ms,
        )
    elif kind == "dose_pulse":
        reagent = str(meta.get("reagent") or "").strip()
        dose_ml = float(meta.get("dose_ml") or 0)
        if not reagent or dose_ml <= 0:
            raise ZonePlanConfigurationError(
                reason_code="dose_pulse_meta_invalid",
                message="dose_pulse без reagent/dose_ml",
            )
        telemetry = await load_zone_telemetry(
            zone_id=task.zone_id,
            now=now,
            telemetry_max_age_sec=plan.telemetry_max_age_sec,
        )
        if reagent == "nutrition":
            sample = telemetry.ec_feed
        else:
            sample = telemetry.ph_feed
        if sample is None:
            raise ZonePlanConfigurationError(
                reason_code="dose_baseline_missing",
                message="Нет свежей пробы для baseline импульса",
            )
        await run_dose_pulse(
            plan=plan,
            gateway=gateway,
            command_repository=command_repository,
            task_id=task.id,
            zone_id=task.zone_id,
            now=now,
            reagent=reagent,
            dose_ml=dose_ml,
            baseline_value=float(sample.value),
        )
    else:
        raise RuntimeError(f"неизвестный kind мутации: {kind}")

    await task_repository.mark_completed(
        task_id=task.id,
        owner=worker_owner,
        now=now,
    )


async def _run_probe_command(
    *,
    task: Any,
    meta: Mapping[str, Any],
    worker_owner: str,
    now: datetime,
    task_repository: PgAutomationTaskRepository,
    command_repository: PgAeCommandRepository,
    gateway: HistoryLoggerGateway,
) -> None:
    greenhouse_uid = str(meta.get("greenhouse_uid") or "").strip()
    node_uid = str(meta.get("node_uid") or "").strip()
    channel = str(meta.get("channel") or "").strip()
    cmd = str(meta.get("cmd") or "").strip()
    params = meta.get("params") if isinstance(meta.get("params"), Mapping) else {}
    if not greenhouse_uid or not node_uid or not channel or not cmd:
        raise RuntimeError("probe_command без greenhouse_uid/node_uid/channel/cmd")

    await task_repository.mark_waiting_command(
        task_id=task.id,
        owner=worker_owner,
        now=now,
    )
    step_no = await command_repository.get_next_step_no(task_id=task.id)
    cmd_id = build_ae4_cmd_id(task_id=task.id, zone_id=task.zone_id, step_no=step_no)
    ae_command_id = await command_repository.create_pending(
        task_id=task.id,
        step_no=step_no,
        node_uid=node_uid,
        channel=channel,
        payload={
            "cmd": cmd,
            "params": dict(params),
            "cmd_id": cmd_id,
            "role": "probe_command",
        },
        now=now,
        stage_name="probe_command",
    )
    if ae_command_id is None:
        raise RuntimeError("Не удалось создать ae_commands для probe")

    result = await gateway.publish_and_await_done(
        greenhouse_uid=greenhouse_uid,
        zone_id=task.zone_id,
        node_uid=node_uid,
        channel=channel,
        cmd=cmd,
        params=dict(params),
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
    await task_repository.mark_completed(
        task_id=task.id,
        owner=worker_owner,
        now=now,
    )


__all__ = ["execute_claimed_task"]
