"""Создаёт или разрешает каноническую задачу AE3-Lite из legacy scheduler intent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from ae3lite.application.dto import TaskCreationResult
from ae3lite.domain.errors import ErrorCodes, TaskCreateError
from ae3lite.infrastructure.metrics import TASK_CREATED
from common.db import get_pool


class CreateTaskFromIntentUseCase:
    """Создаёт каноническую задачу AE3 v2, сохраняя внешнюю семантику idempotency.

    Использует advisory lock PostgreSQL (`pg_try_advisory_xact_lock`) на `zone_id`,
    чтобы предотвратить дублирующее создание задачи при конкурентных запросах.
    """

    HARD_BLOCKING_ALERT_CODES = frozenset({
        "biz_zone_correction_config_missing",
        "biz_zone_dosing_calibration_missing",
    })

    def __init__(
        self,
        *,
        task_repository: Any,
        zone_lease_repository: Any,
        legacy_intent_mapper: Any,
        zone_alert_repository: Any | None = None,
    ) -> None:
        self._task_repository = task_repository
        self._zone_lease_repository = zone_lease_repository
        self._legacy_intent_mapper = legacy_intent_mapper
        self._zone_alert_repository = zone_alert_repository

    async def run(
        self,
        *,
        zone_id: int,
        source: str,
        idempotency_key: str,
        intent_row: Mapping[str, Any],
        now: datetime,
        allow_create: bool = True,
    ) -> TaskCreationResult:
        normalized_key = str(idempotency_key or "").strip()
        if normalized_key == "":
            raise TaskCreateError("start_cycle_missing_idempotency_key", "Для запуска обязателен idempotency_key")

        # Быстрый путь: проверить idempotency без lock
        existing_task = await self._task_repository.get_by_idempotency_key(
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
        pool = await get_pool()
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
                active_task_getter = getattr(self._task_repository, "get_active_for_zone_with_conn", None)
                if callable(active_task_getter):
                    active_task = await active_task_getter(zone_id=zone_id, conn=conn)
                else:
                    active_task = await self._task_repository.get_active_for_zone(zone_id=zone_id)
                if active_task is not None:
                    raise TaskCreateError(
                        ErrorCodes.START_CYCLE_ZONE_BUSY,
                        f"У зоны {zone_id} уже есть активная задача task_id={active_task.id}",
                        details={"active_task_id": active_task.id, "active_task_status": active_task.status},
                    )

                active_lease = await self._zone_lease_repository.get(zone_id=zone_id, conn=conn)
                lease_until = self._normalize_utc(active_lease.leased_until) if active_lease is not None else None
                if active_lease is not None and lease_until is not None and lease_until > self._normalize_utc(now):
                    raise TaskCreateError(
                        ErrorCodes.START_CYCLE_ZONE_BUSY,
                        f"У зоны {zone_id} уже есть активный lease owner={active_lease.owner}",
                        details={
                            "active_lease_owner": active_lease.owner,
                            "active_lease_until": lease_until.isoformat(),
                        },
                    )

                blocking_alert = await self._find_blocking_alert(zone_id=zone_id, conn=conn)
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

                meta = self._legacy_intent_mapper.extract_intent_metadata(
                    source=source,
                    intent_row=intent_row,
                )
                irrigation_snapshot = await self._resolve_irrigation_decision_snapshot(
                    zone_id=zone_id,
                    meta=meta,
                    conn=conn,
                )
                created_task = await self._task_repository.create_pending(
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
                    TASK_CREATED.labels(topology=meta.topology).inc()
                    return TaskCreationResult(task=created_task, created=True)

        # INSERT вернул None: произошёл UNIQUE-конфликт по idempotency_key из конкурентного запроса
        deduplicated_task = await self._task_repository.get_by_idempotency_key(
            zone_id=zone_id,
            idempotency_key=normalized_key,
        )
        if deduplicated_task is not None:
            return TaskCreationResult(task=deduplicated_task, created=False)

        raise TaskCreateError("ae3_task_create_failed", f"Не удалось создать каноническую задачу для zone_id={zone_id}")

    async def _find_blocking_alert(self, *, zone_id: int, conn: Any | None = None) -> dict[str, Any] | None:
        repository = self._zone_alert_repository
        if repository is None:
            return None
        finder = getattr(repository, "find_first_active_by_codes", None)
        if not callable(finder):
            return None
        if conn is not None:
            try:
                alert = await finder(zone_id=zone_id, codes=self.HARD_BLOCKING_ALERT_CODES, conn=conn)
            except TypeError:
                alert = await finder(zone_id=zone_id, codes=self.HARD_BLOCKING_ALERT_CODES)
        else:
            alert = await finder(zone_id=zone_id, codes=self.HARD_BLOCKING_ALERT_CODES)
        return dict(alert) if isinstance(alert, Mapping) else None

    async def _resolve_irrigation_decision_snapshot(
        self,
        *,
        zone_id: int,
        meta: Any,
        conn: Any,
    ) -> dict[str, Any]:
        if str(getattr(meta, "task_type", "") or "").strip().lower() != "irrigation_start":
            return {}

        grow_cycle_row = await conn.fetchrow(
            """
            SELECT
                gc.id AS grow_cycle_id,
                gc.settings AS cycle_settings
            FROM grow_cycles gc
            WHERE gc.zone_id = $1
              AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
            ORDER BY
                CASE gc.status
                    WHEN 'RUNNING' THEN 0
                    WHEN 'PAUSED' THEN 1
                    ELSE 2
                END,
                gc.updated_at DESC,
                gc.id DESC
            LIMIT 1
            """,
            zone_id,
        )
        if grow_cycle_row is None:
            return {}

        cycle_settings = grow_cycle_row.get("cycle_settings")
        cycle_settings = cycle_settings if isinstance(cycle_settings, Mapping) else {}
        expected_bundle_revision = str(cycle_settings.get("bundle_revision") or "").strip()
        grow_cycle_id = int(grow_cycle_row.get("grow_cycle_id") or 0)
        if grow_cycle_id <= 0:
            return {}

        bundle_row = await conn.fetchrow(
            """
            SELECT bundle_revision, config
            FROM automation_effective_bundles
            WHERE scope_type = 'grow_cycle'
              AND scope_id = $1
            LIMIT 1
            """,
            grow_cycle_id,
        )
        if bundle_row is None:
            return {}

        actual_bundle_revision = str(bundle_row.get("bundle_revision") or "").strip()
        if expected_bundle_revision and actual_bundle_revision and expected_bundle_revision != actual_bundle_revision:
            return {}

        bundle_config = bundle_row.get("config")
        if not isinstance(bundle_config, Mapping):
            return {}

        zone_bundle = bundle_config.get("zone")
        if not isinstance(zone_bundle, Mapping):
            return {}

        logic_profile = zone_bundle.get("logic_profile")
        if not isinstance(logic_profile, Mapping):
            return {}

        active_profile = logic_profile.get("active_profile")
        if not isinstance(active_profile, Mapping):
            return {}

        subsystems = active_profile.get("subsystems")
        if not isinstance(subsystems, Mapping):
            return {}

        irrigation = subsystems.get("irrigation")
        if not isinstance(irrigation, Mapping):
            return {}

        decision = irrigation.get("decision")
        if not isinstance(decision, Mapping):
            return {}

        strategy = str(decision.get("strategy") or "task").strip().lower() or "task"
        config = decision.get("config")
        config_mapping = dict(config) if isinstance(config, Mapping) else {}
        return {
            "irrigation_decision_strategy": strategy,
            "irrigation_decision_config": config_mapping or None,
            "irrigation_bundle_revision": actual_bundle_revision or expected_bundle_revision or None,
        }

    def _normalize_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)
