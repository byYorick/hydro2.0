"""CreateTaskFromIntentUseCase creation: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.dto import TaskCreationResult
from ae3lite.domain.errors import ErrorCodes, TaskCreateError


@dataclass(frozen=True)
class IntentTaskCreationPorts:
    assert_required_nodes_available_for_task: Callable[..., Awaitable[Any]]
    ensure_runtime_cycle_preconditions: Callable[..., Awaitable[Any]]
    ensure_solution_change_preconditions: Callable[..., Awaitable[Any]]
    ensure_solution_topup_preconditions: Callable[..., Awaitable[Any]]
    find_blocking_alert: Callable[..., Awaitable[Any]]
    merge_lighting_tick_intent_payload: Callable[..., Any]
    merge_solution_topup_intent_payload: Callable[..., Any]
    normalize_utc: Callable[..., Any]
    resolve_irrigation_decision_snapshot: Callable[..., Awaitable[Any]]
    task_repository: Callable[[], Any]
    zone_intent_repository: Callable[[], Any]
    zone_lease_repository: Callable[[], Any]
    global_task_created: Callable[..., Any]
    global_get_pool: Callable[..., Any]
    global_get_trace_id: Callable[..., Any]


class IntentTaskCreation:
    def __init__(self, ports: IntentTaskCreationPorts) -> None:
        self._ports = ports

    async def run(
        self,
        *,
        zone_id: int,
        source: str,
        idempotency_key: str,
        intent_row: Mapping[str, Any],
        now: datetime,
        allow_create: bool = True,
        lighting_desired_state: str | None = None,
        lighting_brightness_pct: int | None = None,
        solution_topup_mode: str | None = None,
        solution_topup_trigger: str | None = None,
    ) -> TaskCreationResult:
        normalized_key = str(idempotency_key or "").strip()
        if normalized_key == "":
            raise TaskCreateError("start_cycle_missing_idempotency_key", "Для запуска обязателен idempotency_key")

        # Быстрый путь: проверить idempotency без lock
        existing_task = await self._ports.task_repository().get_by_idempotency_key(
            zone_id=zone_id,
            idempotency_key=normalized_key,
        )
        if existing_task is not None:
            return TaskCreationResult(task=existing_task, created=False)
        if not allow_create:
            raise TaskCreateError(
                ErrorCodes.START_CYCLE_INTENT_TERMINAL,
                (
                    f"У terminal intent idempotency_key={normalized_key} для zone_id={zone_id} "
                    "отсутствует canonical task"
                ),
                details={"idempotency_key": normalized_key},
            )

        # Взять advisory lock по зоне, чтобы операция check+create была атомарной
        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                lock_acquired = await conn.fetchval(
                    "SELECT pg_try_advisory_xact_lock($1)",
                    zone_id,
                )
                if not lock_acquired:
                    raise TaskCreateError(
                        "start_cycle_zone_busy",
                        f"Зона {zone_id} заблокирована конкурентным запросом",
                        details={"zone_id": zone_id},
                    )

                # Под lock: проверить активные задачи и lease
                active_task_getter = getattr(self._ports.task_repository(), "get_active_for_zone_with_conn", None)
                if callable(active_task_getter):
                    active_task = await active_task_getter(zone_id=zone_id, conn=conn)
                else:
                    active_task = await self._ports.task_repository().get_active_for_zone(zone_id=zone_id)
                if active_task is not None:
                    raise TaskCreateError(
                        ErrorCodes.START_CYCLE_ZONE_BUSY,
                        f"У зоны {zone_id} уже есть активная задача task_id={active_task.id}",
                        details={"active_task_id": active_task.id, "active_task_status": active_task.status},
                    )

                active_lease = await self._ports.zone_lease_repository().get(zone_id=zone_id, conn=conn)
                lease_until = self._ports.normalize_utc(active_lease.leased_until) if active_lease is not None else None
                if (
                    active_lease is not None
                    and lease_until is not None
                    and lease_until > self._ports.normalize_utc(now)
                ):
                    raise TaskCreateError(
                        ErrorCodes.START_CYCLE_ZONE_BUSY,
                        f"У зоны {zone_id} уже есть активный lease owner={active_lease.owner}",
                        details={
                            "active_lease_owner": active_lease.owner,
                            "active_lease_until": lease_until.isoformat(),
                        },
                    )

                blocking_alert = await self._ports.find_blocking_alert(zone_id=zone_id, conn=conn)
                if blocking_alert is not None:
                    raise TaskCreateError(
                        ErrorCodes.START_CYCLE_ZONE_BUSY,
                        (
                            f"Зона {zone_id} заблокирована активным алертом "
                            f"code={blocking_alert['code']} alert_id={blocking_alert['id']}"
                        ),
                        details={
                            "blocking_alert_id": blocking_alert["id"],
                            "blocking_alert_code": blocking_alert["code"],
                            "blocking_alert_status": blocking_alert["status"],
                        },
                    )

                meta = self._ports.zone_intent_repository().extract_intent_metadata(
                    source=source,
                    intent_row=intent_row,
                )
                intent_meta = dict(meta.intent_meta) if isinstance(meta.intent_meta, Mapping) else {}
                if str(meta.task_type or "").strip().lower() == "lighting_tick":
                    intent_meta = self._ports.merge_lighting_tick_intent_payload(
                        intent_meta=intent_meta,
                        lighting_desired_state=lighting_desired_state,
                        lighting_brightness_pct=lighting_brightness_pct,
                    )
                if str(meta.task_type or "").strip().lower() == "solution_topup":
                    intent_meta = self._ports.merge_solution_topup_intent_payload(
                        intent_meta=intent_meta,
                        solution_topup_mode=solution_topup_mode,
                        solution_topup_trigger=solution_topup_trigger,
                    )
                trace_id = str(self._ports.global_get_trace_id() or "").strip()
                if trace_id:
                    intent_meta["trace_id"] = trace_id
                meta = replace(meta, intent_meta=intent_meta)
                await self._ports.ensure_runtime_cycle_preconditions(
                    zone_id=zone_id,
                    meta=meta,
                    conn=conn,
                )
                await self._ports.ensure_solution_topup_preconditions(
                    zone_id=zone_id,
                    meta=meta,
                    conn=conn,
                    now=now,
                )
                await self._ports.ensure_solution_change_preconditions(
                    zone_id=zone_id,
                    meta=meta,
                    conn=conn,
                )
                await self._ports.assert_required_nodes_available_for_task(
                    zone_id=zone_id,
                    topology=meta.topology,
                    conn=conn,
                    task_type=meta.task_type,
                    current_stage=meta.current_stage,
                )
                irrigation_snapshot = await self._ports.resolve_irrigation_decision_snapshot(
                    zone_id=zone_id,
                    meta=meta,
                    conn=conn,
                )
                created_task = await self._ports.task_repository().create_pending(
                    zone_id=zone_id,
                    idempotency_key=normalized_key,
                    task_type=meta.task_type,
                    topology=meta.topology,
                    current_stage=meta.current_stage,
                    workflow_phase=meta.workflow_phase,
                    intent_source=meta.intent_source,
                    intent_trigger=meta.intent_trigger,
                    intent_id=meta.intent_id,
                    intent_meta=meta.intent_meta,
                    scheduled_for=now,
                    due_at=now,
                    now=now,
                    irrigation_mode=meta.irrigation_mode,
                    irrigation_requested_duration_sec=meta.irrigation_requested_duration_sec,
                    irrigation_decision_strategy=irrigation_snapshot.get("irrigation_decision_strategy"),
                    irrigation_decision_config=irrigation_snapshot.get("irrigation_decision_config"),
                    irrigation_bundle_revision=irrigation_snapshot.get("irrigation_bundle_revision"),
                    conn=conn,
                )
                if created_task is not None:
                    self._ports.global_task_created().labels(topology=meta.topology).inc()
                    return TaskCreationResult(task=created_task, created=True)

        # INSERT вернул None: произошёл UNIQUE-конфликт по idempotency_key из конкурентного запроса
        deduplicated_task = await self._ports.task_repository().get_by_idempotency_key(
            zone_id=zone_id,
            idempotency_key=normalized_key,
        )
        if deduplicated_task is not None:
            return TaskCreationResult(task=deduplicated_task, created=False)

        raise TaskCreateError("ae3_task_create_failed", f"Не удалось создать каноническую задачу для zone_id={zone_id}")
