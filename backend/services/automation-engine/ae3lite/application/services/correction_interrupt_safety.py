"""Безопасная верификация железа после startup_recovery_correction_interrupted.

После power-loss / рестарта AE нельзя сразу эскалировать critical
``biz_flow_stop_failed_hardware_may_be_active``: узлы ещё offline, актуаторы
обычно уже OFF после brownout. Сначала pending-verify → при подтверждённом
безопасном состоянии — safe; critical только если после grace оборудование
ON или безопасность не подтверждена.

Fail-closed инварианты (safety):
- ``ready|idle`` + отсутствующий/устаревший IRR_STATE_SNAPSHOT **не** auto-safe:
  pending до grace, затем unsafe (нужен свежий OFF snapshot).
- Irrig OFF через irr_state — необходимое, но **недостаточное** условие для
  ``corr_dose_*`` / ``corr_wait_*``: каналы дозирующих насосов EC/pH через
  irr_state пока **недоступны** → dose-path fail-closed (не safe, pending до
  grace / unsafe после). Без подтверждения dose-path нельзя эмитить
  HARDWARE_SAFE и разрешать irrigation replay.
- Resume mid-dose запрещён (pending-check строится только для dose/wait steps;
  safe ≠ resume коррекции).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from ae3lite.application.handlers.flow_path_guard import (
    CORRECTION_DOSE_STEPS,
    emit_correction_interrupted_hardware_risk,
    flow_path_stage_config,
)
from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.services.zone_node_availability import TWO_TANK_REQUIRED_NODE_TYPES
from ae3lite.infrastructure.metrics import inc_observability_write_failed
from common.biz_alerts import send_biz_alert
from common.db import create_zone_event, fetch

_logger = logging.getLogger(__name__)

PENDING_VERIFY_EVENT = "AE_CORRECTION_INTERRUPT_PENDING_VERIFY"
HARDWARE_SAFE_EVENT = "AE_CORRECTION_INTERRUPT_HARDWARE_SAFE"
ESCALATED_HARDWARE_RISK_EVENT = "FLOW_STOP_FAILED_HARDWARE_MAY_BE_ACTIVE"

DEFAULT_VERIFY_GRACE_SEC = 120
DEFAULT_IRR_STATE_MAX_AGE_SEC = 90
# status=online без свежего last_seen/heartbeat считается stale → не online (fail-closed).
DEFAULT_NODE_ONLINE_MAX_AGE_SEC = 120
# Сколько хранить «открытые» PENDING_VERIFY для reload после рестарта AE.
DEFAULT_PENDING_VERIFY_LOOKBACK_HOURS = 24

# Dose actuators (EC/pH pumps) are not represented in irrig IRR_STATE_SNAPSHOT.
DOSE_ACTUATORS_UNVERIFIABLE_REASON = "dose_actuators_unverifiable_via_irr_state"

# Mirror ExecuteTaskUseCase.FAIL_SAFE_SHUTDOWN_CHANNELS for interrupt fail-safe stop.
FAIL_SAFE_SHUTDOWN_CHANNELS = (
    "pump_main",
    "valve_clean_fill",
    "valve_clean_supply",
    "valve_solution_fill",
    "valve_solution_supply",
    "valve_irrigation",
)


@dataclass(frozen=True)
class CorrectionInterruptPendingCheck:
    """Отложенная проверка железа после fail коррекции на startup recovery."""

    zone_id: int
    task_id: int
    task_type: str
    topology: str
    stage: str
    corr_step: str
    workflow_phase: str
    recovery_source: str
    deadline_at: datetime
    irrigation_mode: str | None = None
    irrigation_requested_duration_sec: int | None = None
    intent_id: int | None = None


@dataclass(frozen=True)
class CorrectionInterruptSafetyVerdict:
    """Итог одной попытки verify: pending | safe | unsafe.

    ``dose_risk`` — явная оценка dose-path: None если шаг не dose/wait или
    риск снят; иначе reason, почему dose actuators нельзя считать подтверждённо
    безопасными (сейчас всегда unverifiable через irr_state).
    """

    status: str  # pending | safe | unsafe
    reason: str
    snapshot: Mapping[str, Any] | None = None
    nodes_online: bool = False
    dose_risk: str | None = None


def is_dose_correction_step(corr_step: object) -> bool:
    return str(corr_step or "").strip().lower() in CORRECTION_DOSE_STEPS


def assess_dose_path_risk(*, corr_step: object) -> str | None:
    """Оценка риска dose-path для interrupt safety.

    Для ``corr_dose_*`` / ``corr_wait_*`` probe каналов дозирующих насосов EC/pH
    через irrig ``IRR_STATE_SNAPSHOT`` пока недоступен → fail-closed
    (возвращает reason, не None). Без подтверждения dose actuators нельзя
    считать железо safe и нельзя разрешать HARDWARE_SAFE / replay.

    Returns:
        None — dose-path не применим (не dose/wait step) или подтверждён.
        str  — reason, почему dose-path нельзя считать безопасным.
    """
    if not is_dose_correction_step(corr_step):
        return None
    # Planned: отдельный probe EC/pH pump channels (telemetry/command status).
    # До появления probe — всегда fail-closed.
    return DOSE_ACTUATORS_UNVERIFIABLE_REASON


def _parse_deadline_at(raw: object, *, fallback_now: datetime) -> datetime:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=timezone.utc)
    text = str(raw or "").strip()
    if text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return fallback_now + timedelta(seconds=DEFAULT_VERIFY_GRACE_SEC)


def pending_check_to_event_payload(check: CorrectionInterruptPendingCheck) -> dict[str, Any]:
    """Сериализация pending-check в payload zone_event (для persist/restore)."""
    payload: dict[str, Any] = {
        "task_id": int(check.task_id),
        "stage": check.stage,
        "corr_step": check.corr_step,
        "task_type": check.task_type,
        "topology": check.topology,
        "workflow_phase": check.workflow_phase,
        "recovery_source": check.recovery_source,
        "deadline_at": check.deadline_at.astimezone(timezone.utc).isoformat(),
        "reason": "startup_recovery_correction_interrupted",
    }
    if check.irrigation_mode:
        payload["irrigation_mode"] = check.irrigation_mode
    if check.irrigation_requested_duration_sec is not None:
        payload["irrigation_requested_duration_sec"] = int(check.irrigation_requested_duration_sec)
    if check.intent_id is not None:
        payload["intent_id"] = int(check.intent_id)
    return payload


def pending_check_from_event_payload(
    *,
    zone_id: int,
    payload: Mapping[str, Any],
    fallback_now: datetime | None = None,
) -> CorrectionInterruptPendingCheck | None:
    """Восстанавливает pending-check из payload PENDING_VERIFY zone_event."""
    try:
        task_id = int(payload.get("task_id") or 0)
    except (TypeError, ValueError):
        return None
    if zone_id <= 0 or task_id <= 0:
        return None
    corr_step = str(payload.get("corr_step") or "").strip().lower()
    if not is_dose_correction_step(corr_step):
        return None
    base_now = fallback_now or datetime.now(timezone.utc)
    intent_raw = payload.get("intent_id")
    try:
        intent_id = int(intent_raw) if intent_raw not in (None, "") else None
    except (TypeError, ValueError):
        intent_id = None
    duration_raw = payload.get("irrigation_requested_duration_sec")
    try:
        duration = int(duration_raw) if duration_raw not in (None, "") else None
    except (TypeError, ValueError):
        duration = None
    return CorrectionInterruptPendingCheck(
        zone_id=int(zone_id),
        task_id=task_id,
        task_type=str(payload.get("task_type") or "").strip().lower(),
        topology=str(payload.get("topology") or "").strip().lower(),
        stage=str(payload.get("stage") or "").strip().lower(),
        corr_step=corr_step,
        workflow_phase=str(payload.get("workflow_phase") or "").strip().lower(),
        recovery_source=str(payload.get("recovery_source") or "startup_recovery").strip()
        or "startup_recovery",
        deadline_at=_parse_deadline_at(payload.get("deadline_at"), fallback_now=base_now),
        irrigation_mode=str(payload.get("irrigation_mode") or "").strip().lower() or None,
        irrigation_requested_duration_sec=duration,
        intent_id=intent_id,
    )


async def load_open_pending_correction_interrupt_checks(
    *,
    now: datetime,
    lookback_hours: int = DEFAULT_PENDING_VERIFY_LOOKBACK_HOURS,
) -> tuple[CorrectionInterruptPendingCheck, ...]:
    """Восстанавливает незакрытые PENDING_VERIFY после рестарта AE.

    «Закрыт» = для того же task_id уже есть HARDWARE_SAFE или FLOW_STOP_FAILED
    после PENDING_VERIFY. Дедуп по task_id: последний payload побеждает.
    """
    lookback = max(1, int(lookback_hours))
    rows = await fetch(
        """
        WITH pending AS (
            SELECT
                zone_id,
                id AS event_id,
                created_at,
                COALESCE(payload_json, details, '{}'::jsonb) AS payload
            FROM zone_events
            WHERE type = $1
              AND created_at >= (NOW() - ($3::text || ' hours')::interval)
        ),
        closed AS (
            SELECT
                zone_id,
                NULLIF(COALESCE(payload_json->>'task_id', details->>'task_id'), '')::bigint AS task_id,
                MAX(created_at) AS closed_at
            FROM zone_events
            WHERE type = ANY($2::text[])
              AND created_at >= (NOW() - ($3::text || ' hours')::interval)
            GROUP BY 1, 2
        )
        SELECT p.zone_id, p.payload, p.created_at
        FROM pending p
        LEFT JOIN closed c
          ON c.zone_id = p.zone_id
         AND c.task_id = NULLIF(p.payload->>'task_id', '')::bigint
         AND c.closed_at >= p.created_at
        WHERE c.task_id IS NULL
        ORDER BY p.created_at ASC, p.event_id ASC
        """,
        PENDING_VERIFY_EVENT,
        [HARDWARE_SAFE_EVENT, ESCALATED_HARDWARE_RISK_EVENT],
        str(lookback),
    )
    by_task: dict[int, CorrectionInterruptPendingCheck] = {}
    for row in rows or ():
        try:
            zone_id = int(row.get("zone_id") or 0)
        except (TypeError, ValueError):
            continue
        payload = row.get("payload")
        if isinstance(payload, str):
            import json

            try:
                payload = json.loads(payload)
            except (TypeError, ValueError):
                continue
        if not isinstance(payload, Mapping):
            continue
        check = pending_check_from_event_payload(
            zone_id=zone_id,
            payload=payload,
            fallback_now=now,
        )
        if check is None:
            continue
        by_task[int(check.task_id)] = check
    return tuple(by_task.values())


@dataclass(frozen=True)
class CorrectionInterruptFailSafeStopResult:
    """Итог попытки fail-safe stop перед escalate."""

    attempted: bool
    success: bool
    reason: str
    commands_total: int = 0


async def load_irrig_fail_safe_actuators(*, zone_id: int) -> tuple[Mapping[str, Any], ...]:
    """Активные ACTUATOR/SERVICE каналы irrig-нод зоны для fail-safe OFF publish."""
    rows = await fetch(
        """
        SELECT
            n.uid AS node_uid,
            LOWER(COALESCE(n.type, '')) AS node_type,
            LOWER(TRIM(COALESCE(nc.channel, ''))) AS channel
        FROM nodes n
        JOIN node_channels nc ON nc.node_id = n.id
        WHERE n.zone_id = $1
          AND LOWER(COALESCE(n.type, '')) = 'irrig'
          AND UPPER(TRIM(COALESCE(nc.type, ''))) IN ('ACTUATOR', 'SERVICE')
          AND COALESCE(nc.is_active, TRUE) = TRUE
        ORDER BY n.id ASC, nc.id ASC
        """,
        zone_id,
    )
    out: list[dict[str, Any]] = []
    for row in rows or ():
        node_uid = str(row.get("node_uid") or "").strip()
        channel = str(row.get("channel") or "").strip().lower()
        if not node_uid or not channel:
            continue
        if channel not in FAIL_SAFE_SHUTDOWN_CHANNELS:
            continue
        out.append(
            {
                "node_uid": node_uid,
                "node_type": "irrig",
                "channel": channel,
            }
        )
    return tuple(out)


def build_fail_safe_shutdown_commands(
    *,
    actuators: Sequence[Mapping[str, Any]],
) -> tuple[PlannedCommand, ...]:
    """Строит OFF set_relay batch: pump_main строго первым, только irrig-каналы."""
    pump: list[PlannedCommand] = []
    other: list[PlannedCommand] = []
    seen: set[tuple[str, str]] = set()
    for actuator in actuators:
        node_uid = str(actuator.get("node_uid") or "").strip()
        node_type = str(actuator.get("node_type") or "").strip().lower()
        channel = str(actuator.get("channel") or "").strip().lower()
        if not node_uid or node_type != "irrig" or channel not in FAIL_SAFE_SHUTDOWN_CHANNELS:
            continue
        pair = (node_uid, channel)
        if pair in seen:
            continue
        seen.add(pair)
        cmd = PlannedCommand(
            step_no=0,
            node_uid=node_uid,
            channel=channel,
            payload={
                "name": "fail_safe_shutdown",
                "cmd": "set_relay",
                "params": {"state": False},
                "allow_no_effect": True,
                "dedupe_bypass": True,
                "_ae3_fail_safe": True,
            },
        )
        if channel == "pump_main":
            pump.append(cmd)
        else:
            other.append(cmd)
    ordered = [*pump, *other]
    return tuple(
        PlannedCommand(
            step_no=idx + 1,
            node_uid=item.node_uid,
            channel=item.channel,
            planner_step=f"corr_interrupt_fail_safe:{idx + 1}:{item.channel}"[:160],
            payload=item.payload,
        )
        for idx, item in enumerate(ordered)
    )


async def attempt_correction_interrupt_fail_safe_stop(
    *,
    check: CorrectionInterruptPendingCheck,
    now: datetime,
    command_gateway: Any | None,
) -> CorrectionInterruptFailSafeStopResult:
    """Publish-only fail-safe OFF irrig actuators через history-logger gateway.

    Не ждёт terminal DONE (как ExecuteTaskUseCase._attempt_fail_safe_shutdown).
    Не требует active task: failed task_id остаётся валидным FK для ae_commands.
    """
    if command_gateway is None or not callable(
        getattr(command_gateway, "run_publish_only_batch", None)
    ):
        return CorrectionInterruptFailSafeStopResult(
            attempted=False,
            success=False,
            reason="no_command_gateway",
        )

    topology = str(check.topology or "").strip().lower()
    if topology and topology not in {"two_tank", "two_tank_drip_substrate_trays"}:
        return CorrectionInterruptFailSafeStopResult(
            attempted=False,
            success=False,
            reason=f"unsupported_topology:{topology}",
        )

    try:
        actuators = await load_irrig_fail_safe_actuators(zone_id=int(check.zone_id))
    except Exception:
        _logger.warning(
            "AE3 correction interrupt: не удалось загрузить irrig actuators zone_id=%s",
            check.zone_id,
            exc_info=True,
        )
        return CorrectionInterruptFailSafeStopResult(
            attempted=False,
            success=False,
            reason="actuators_load_failed",
        )
    commands = build_fail_safe_shutdown_commands(actuators=actuators)
    if not commands:
        return CorrectionInterruptFailSafeStopResult(
            attempted=False,
            success=False,
            reason="no_irrig_actuators",
        )

    task = _FakeTaskForFailSafe(check)
    try:
        result = await command_gateway.run_publish_only_batch(
            task=task,
            commands=commands,
            now=now,
        )
    except Exception as exc:
        _logger.warning(
            "AE3 correction interrupt: fail-safe publish failed zone_id=%s task_id=%s",
            check.zone_id,
            check.task_id,
            exc_info=True,
        )
        return CorrectionInterruptFailSafeStopResult(
            attempted=True,
            success=False,
            reason=f"publish_exception:{type(exc).__name__}",
            commands_total=len(commands),
        )

    success = bool(isinstance(result, Mapping) and result.get("success"))
    if success:
        _logger.info(
            "AE3 correction interrupt fail-safe stop published zone_id=%s task_id=%s commands=%s",
            check.zone_id,
            check.task_id,
            len(commands),
        )
        return CorrectionInterruptFailSafeStopResult(
            attempted=True,
            success=True,
            reason="ok",
            commands_total=len(commands),
        )
    error_code = (
        str(result.get("error_code") or "publish_failed")
        if isinstance(result, Mapping)
        else "publish_failed"
    )
    _logger.error(
        "AE3 correction interrupt fail-safe stop non-success "
        "zone_id=%s task_id=%s error_code=%s",
        check.zone_id,
        check.task_id,
        error_code,
    )
    return CorrectionInterruptFailSafeStopResult(
        attempted=True,
        success=False,
        reason=error_code,
        commands_total=len(commands),
    )


def build_pending_check_from_task(
    *,
    task: Any,
    now: datetime,
    recovery_source: str = "startup_recovery",
    verify_grace_sec: int = DEFAULT_VERIFY_GRACE_SEC,
) -> CorrectionInterruptPendingCheck | None:
    correction = getattr(task, "correction", None)
    if correction is None:
        return None
    corr_step = str(getattr(correction, "corr_step", "") or "").strip().lower()
    if not is_dose_correction_step(corr_step):
        return None
    grace = max(15, int(verify_grace_sec))
    intent_id_raw = getattr(task, "intent_id", None)
    intent_id = int(intent_id_raw) if intent_id_raw not in (None, "") else None
    duration_raw = getattr(task, "irrigation_requested_duration_sec", None)
    duration = int(duration_raw) if duration_raw not in (None, "") else None
    return CorrectionInterruptPendingCheck(
        zone_id=int(task.zone_id),
        task_id=int(task.id),
        task_type=str(getattr(task, "task_type", "") or "").strip().lower(),
        topology=str(getattr(task, "topology", "") or "").strip().lower(),
        stage=str(getattr(task, "current_stage", "") or "").strip().lower(),
        corr_step=corr_step,
        workflow_phase=str(getattr(task, "workflow_phase", "") or "").strip().lower(),
        recovery_source=str(recovery_source or "startup_recovery"),
        deadline_at=now + timedelta(seconds=grace),
        irrigation_mode=str(getattr(task, "irrigation_mode", "") or "").strip().lower() or None,
        irrigation_requested_duration_sec=duration,
        intent_id=intent_id,
    )


def flow_snapshot_is_safe(*, stage: str, snapshot: Mapping[str, Any] | None) -> bool:
    """True, если irr_state соответствует OFF-ожиданиям stop-плана stage."""
    config = flow_path_stage_config(stage)
    if config is None:
        return True
    if not isinstance(snapshot, Mapping):
        return False
    for channel, expected_off in config.off_expected.items():
        raw = snapshot.get(channel)
        if raw is None:
            # отсутствует ключ — не подтверждаем safe
            return False
        actual = bool(raw)
        if actual != bool(expected_off):
            return False
    return True


async def emit_correction_interrupt_pending_verify(
    *,
    check: CorrectionInterruptPendingCheck,
    now: datetime,
) -> None:
    payload = with_runtime_event_contract(
        {
            **pending_check_to_event_payload(check),
            "message": (
                "Коррекция прервана при recovery; ожидается подтверждение безопасного "
                "состояния оборудования после восстановления узлов"
            ),
        }
    )
    try:
        await create_zone_event(check.zone_id, PENDING_VERIFY_EVENT, payload)
    except Exception:
        inc_observability_write_failed(kind="zone_event")
        _logger.warning(
            "AE3 correction interrupt: не удалось записать PENDING_VERIFY zone_id=%s task_id=%s",
            check.zone_id,
            check.task_id,
            exc_info=True,
        )
    try:
        await send_biz_alert(
            zone_id=check.zone_id,
            code="biz_ae3_correction_interrupt_pending_verify",
            severity="warning",
            message=(
                "Коррекция прервана при recovery — проверяем оборудование "
                "после восстановления узлов"
            ),
            details={
                "task_id": check.task_id,
                "stage": check.stage,
                "corr_step": check.corr_step,
                "recovery_source": check.recovery_source,
                "deadline_at": check.deadline_at.astimezone(timezone.utc).isoformat(),
                "alert_policy_mode": "auto_resolve",
                "auto_resolve_eligible": True,
            },
            scope_parts=(f"task_id:{check.task_id}", f"stage:{check.stage}"),
        )
    except Exception:
        inc_observability_write_failed(kind="biz_alert")
        _logger.warning(
            "AE3 correction interrupt: не удалось создать pending-verify alert zone_id=%s",
            check.zone_id,
            exc_info=True,
        )


async def emit_correction_interrupt_hardware_safe(
    *,
    check: CorrectionInterruptPendingCheck,
    now: datetime,
    reason: str,
    snapshot: Mapping[str, Any] | None = None,
) -> None:
    payload = with_runtime_event_contract(
        {
            "task_id": check.task_id,
            "stage": check.stage,
            "corr_step": check.corr_step,
            "task_type": check.task_type,
            "recovery_source": check.recovery_source,
            "reason": reason,
            "snapshot": dict(snapshot) if isinstance(snapshot, Mapping) else None,
            "message": "Оборудование подтверждено в безопасном состоянии после прерывания коррекции",
        }
    )
    try:
        await create_zone_event(check.zone_id, HARDWARE_SAFE_EVENT, payload)
    except Exception:
        inc_observability_write_failed(kind="zone_event")
        _logger.warning(
            "AE3 correction interrupt: не удалось записать HARDWARE_SAFE zone_id=%s task_id=%s",
            check.zone_id,
            check.task_id,
            exc_info=True,
        )
    # Закрываем pending-verify warning (тот же dedupe scope, что и raise).
    try:
        from common.biz_alerts import _build_dedupe_key
        from common.alert_publisher import AlertPublisher

        details = {
            "task_id": check.task_id,
            "stage": check.stage,
            "corr_step": check.corr_step,
            "recovery_source": check.recovery_source,
            "message": "Оборудование подтверждено безопасным после recovery",
            "resolved_reason": reason,
        }
        dedupe_key = _build_dedupe_key(
            code="biz_ae3_correction_interrupt_pending_verify",
            zone_id=check.zone_id,
            details=details,
            scope_parts=(f"task_id:{check.task_id}", f"stage:{check.stage}"),
        )
        publisher = AlertPublisher(default_source="biz")
        await publisher.resolve(
            zone_id=check.zone_id,
            source="biz",
            code="biz_ae3_correction_interrupt_pending_verify",
            alert_type="Business Alert",
            details=details,
            dedupe_key=dedupe_key,
            scoped=True,
            severity="warning",
        )
    except Exception:
        _logger.warning(
            "AE3 correction interrupt: не удалось resolve pending-verify alert zone_id=%s",
            check.zone_id,
            exc_info=True,
        )


async def escalate_correction_interrupt_hardware_risk(
    *,
    check: CorrectionInterruptPendingCheck,
    now: datetime,
    reason: str,
) -> None:
    """Эскалация в critical — только после неуспешной верификации / grace timeout."""
    task = _FakeTaskForAlert(check)
    await emit_correction_interrupted_hardware_risk(
        task=task,
        now=now,
        recovery_source=f"{check.recovery_source}:{reason}",
    )


class _FakeTaskForAlert:
    """Минимальный task-like для emit_correction_interrupted_hardware_risk."""

    def __init__(self, check: CorrectionInterruptPendingCheck) -> None:
        self.id = check.task_id
        self.zone_id = check.zone_id
        self.current_stage = check.stage
        self.correction = type("C", (), {"corr_step": check.corr_step})()
        self.workflow = type("W", (), {"control_mode": "auto"})()


class _FakeTaskForFailSafe:
    """Task-like для publish-only fail-safe batch (без corr_step в planner_step)."""

    def __init__(self, check: CorrectionInterruptPendingCheck) -> None:
        self.id = check.task_id
        self.zone_id = check.zone_id
        self.current_stage = check.stage or "correction_interrupt_fail_safe"
        self.topology = check.topology
        self.claimed_by = "ae3-correction-interrupt-fail-safe"
        self.correction = None
        self.workflow = type(
            "W",
            (),
            {
                "control_mode": "auto",
                "workflow_phase": check.workflow_phase,
                "stage_entered_at": None,
                "corr_step": None,
            },
        )()


async def zone_has_active_ae_task(*, zone_id: int) -> bool:
    rows = await fetch(
        """
        SELECT 1
        FROM ae_tasks
        WHERE zone_id = $1
          AND status = ANY(ARRAY['pending','claimed','running','waiting_command']::text[])
        LIMIT 1
        """,
        zone_id,
    )
    return bool(rows)


def _node_is_fresh_online(
    *,
    status: str,
    last_seen_age_sec: int | None,
    max_age_sec: int,
) -> bool:
    if str(status or "").strip().lower() != "online":
        return False
    if last_seen_age_sec is None:
        # Нет timestamp активности — fail-closed (не считаем online).
        return False
    return int(last_seen_age_sec) < int(max_age_sec)


async def required_nodes_online(
    *,
    zone_id: int,
    required_types: Sequence[str] = tuple(sorted(TWO_TANK_REQUIRED_NODE_TYPES)),
    max_age_sec: int = DEFAULT_NODE_ONLINE_MAX_AGE_SEC,
) -> tuple[bool, tuple[str, ...]]:
    """Все assigned-ноды каждого required type должны быть fresh-online.

    Не берём «первую попавшуюся» ноду типа: если у зоны два irrig, оба должны
    быть online со свежим last_seen/last_heartbeat. Отсутствие нод типа —
    missing (fail-closed).
    """
    rows = await fetch(
        """
        SELECT LOWER(COALESCE(type, '')) AS node_type,
               LOWER(TRIM(COALESCE(status, ''))) AS status,
               EXTRACT(
                   EPOCH FROM (
                       NOW() - COALESCE(
                           last_seen_at,
                           last_heartbeat_at,
                           updated_at
                       )
                   )
               )::BIGINT AS last_seen_age_sec
        FROM nodes
        WHERE zone_id = $1
        """,
        zone_id,
    )
    by_type: dict[str, list[tuple[str, int | None]]] = {}
    for row in rows:
        node_type = str(row.get("node_type") or "").strip().lower()
        if not node_type:
            continue
        status = str(row.get("status") or "").strip().lower()
        age_raw = row.get("last_seen_age_sec")
        try:
            age = int(age_raw) if age_raw is not None else None
        except (TypeError, ValueError):
            age = None
        by_type.setdefault(node_type, []).append((status, age))

    freshness_limit = max(1, int(max_age_sec))
    missing: list[str] = []
    for node_type in required_types:
        nodes = by_type.get(str(node_type).strip().lower()) or []
        if not nodes:
            missing.append(str(node_type))
            continue
        if not all(
            _node_is_fresh_online(
                status=status,
                last_seen_age_sec=age,
                max_age_sec=freshness_limit,
            )
            for status, age in nodes
        ):
            missing.append(str(node_type))
    return (not missing, tuple(missing))


async def read_workflow_phase(*, zone_id: int) -> str | None:
    rows = await fetch(
        """
        SELECT workflow_phase
        FROM zone_workflow_state
        WHERE zone_id = $1
        LIMIT 1
        """,
        zone_id,
    )
    if not rows:
        return None
    return str(rows[0].get("workflow_phase") or "").strip().lower() or None


def _pending_or_unsafe_after_grace(
    *,
    now: datetime,
    deadline_at: datetime,
    pending_reason: str,
    unsafe_reason: str,
    snapshot: Mapping[str, Any] | None = None,
    nodes_online: bool = True,
    dose_risk: str | None = None,
) -> CorrectionInterruptSafetyVerdict:
    if now >= deadline_at:
        return CorrectionInterruptSafetyVerdict(
            status="unsafe",
            reason=unsafe_reason,
            snapshot=snapshot,
            nodes_online=nodes_online,
            dose_risk=dose_risk,
        )
    return CorrectionInterruptSafetyVerdict(
        status="pending",
        reason=pending_reason,
        snapshot=snapshot,
        nodes_online=nodes_online,
        dose_risk=dose_risk,
    )


async def evaluate_correction_interrupt_safety(
    *,
    check: CorrectionInterruptPendingCheck,
    now: datetime,
    runtime_monitor: Any,
    irr_state_max_age_sec: int = DEFAULT_IRR_STATE_MAX_AGE_SEC,
) -> CorrectionInterruptSafetyVerdict:
    """Оценивает, можно ли считать железо безопасным после interrupt.

    Safe только при: нет active task, required nodes online, свежий irrig OFF
    snapshot **и** отсутствие dose-risk (для dose/wait — сейчас всегда risk,
    т.к. EC/pH pump channels через irr_state не probe'ятся).
    """
    dose_risk = assess_dose_path_risk(corr_step=check.corr_step)

    if await zone_has_active_ae_task(zone_id=check.zone_id):
        return CorrectionInterruptSafetyVerdict(
            status="pending",
            reason="zone_has_active_task",
            nodes_online=True,
            dose_risk=dose_risk,
        )

    nodes_ok, missing = await required_nodes_online(zone_id=check.zone_id)
    if not nodes_ok:
        return _pending_or_unsafe_after_grace(
            now=now,
            deadline_at=check.deadline_at,
            pending_reason=f"waiting_nodes:{','.join(missing)}",
            unsafe_reason=f"required_nodes_offline:{','.join(missing)}",
            nodes_online=False,
            dose_risk=dose_risk,
        )

    state = await runtime_monitor.read_latest_irr_state(
        zone_id=check.zone_id,
        max_age_sec=max(5, int(irr_state_max_age_sec)),
    )
    snapshot = state.get("snapshot") if isinstance(state, Mapping) else None
    has_snapshot = bool(isinstance(state, Mapping) and state.get("has_snapshot"))
    is_stale = bool(isinstance(state, Mapping) and state.get("is_stale"))
    workflow_phase = await read_workflow_phase(zone_id=check.zone_id)
    snap_map = snapshot if isinstance(snapshot, Mapping) else None

    # ready/idle + missing/stale — НЕ auto-safe (fail-closed): без свежего
    # OFF snapshot нельзя скрыть потенциально активные актуаторы.
    if not has_snapshot or is_stale or snap_map is None:
        phase_suffix = (
            f"_in_{workflow_phase}"
            if workflow_phase in {"ready", "idle"}
            else ""
        )
        return _pending_or_unsafe_after_grace(
            now=now,
            deadline_at=check.deadline_at,
            pending_reason=f"waiting_fresh_irr_state{phase_suffix}",
            unsafe_reason=f"irr_state_unavailable_after_grace{phase_suffix}",
            snapshot=snap_map,
            nodes_online=True,
            dose_risk=dose_risk,
        )

    if not flow_snapshot_is_safe(stage=check.stage, snapshot=snap_map):
        # Свежий ON — stuck actuators; в ready/idle особенно опасно.
        if workflow_phase in {"ready", "idle"}:
            return _pending_or_unsafe_after_grace(
                now=now,
                deadline_at=check.deadline_at,
                pending_reason="waiting_actuators_off_in_ready",
                unsafe_reason="irr_state_actuators_active_in_ready",
                snapshot=dict(snap_map),
                nodes_online=True,
                dose_risk=dose_risk,
            )
        return _pending_or_unsafe_after_grace(
            now=now,
            deadline_at=check.deadline_at,
            pending_reason="waiting_actuators_off",
            unsafe_reason="irr_state_actuators_active_after_grace",
            snapshot=dict(snap_map),
            nodes_online=True,
            dose_risk=dose_risk,
        )

    # Irrig OFF подтверждён — необходимое условие. Для dose/wait без probe
    # dose actuators всё ещё не safe.
    if dose_risk is not None:
        return _pending_or_unsafe_after_grace(
            now=now,
            deadline_at=check.deadline_at,
            pending_reason=dose_risk,
            unsafe_reason=f"{dose_risk}_after_grace",
            snapshot=dict(snap_map),
            nodes_online=True,
            dose_risk=dose_risk,
        )

    return CorrectionInterruptSafetyVerdict(
        status="safe",
        reason="irr_state_off_confirmed",
        snapshot=dict(snap_map),
        nodes_online=True,
        dose_risk=None,
    )


__all__ = [
    "CorrectionInterruptFailSafeStopResult",
    "CorrectionInterruptPendingCheck",
    "CorrectionInterruptSafetyVerdict",
    "DEFAULT_IRR_STATE_MAX_AGE_SEC",
    "DEFAULT_NODE_ONLINE_MAX_AGE_SEC",
    "DEFAULT_PENDING_VERIFY_LOOKBACK_HOURS",
    "DEFAULT_VERIFY_GRACE_SEC",
    "DOSE_ACTUATORS_UNVERIFIABLE_REASON",
    "ESCALATED_HARDWARE_RISK_EVENT",
    "FAIL_SAFE_SHUTDOWN_CHANNELS",
    "HARDWARE_SAFE_EVENT",
    "PENDING_VERIFY_EVENT",
    "assess_dose_path_risk",
    "attempt_correction_interrupt_fail_safe_stop",
    "build_fail_safe_shutdown_commands",
    "build_pending_check_from_task",
    "emit_correction_interrupt_hardware_safe",
    "emit_correction_interrupt_pending_verify",
    "escalate_correction_interrupt_hardware_risk",
    "evaluate_correction_interrupt_safety",
    "flow_snapshot_is_safe",
    "is_dose_correction_step",
    "load_irrig_fail_safe_actuators",
    "load_open_pending_correction_interrupt_checks",
    "pending_check_from_event_payload",
    "pending_check_to_event_payload",
    "read_workflow_phase",
    "required_nodes_online",
    "zone_has_active_ae_task",
]
