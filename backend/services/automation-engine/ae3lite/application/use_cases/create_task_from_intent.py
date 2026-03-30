"""Create or resolve canonical AE3-Lite task from legacy scheduler intent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from ae3lite.application.dto import TaskCreationResult
from ae3lite.domain.errors import ErrorCodes, TaskCreateError
from ae3lite.infrastructure.metrics import TASK_CREATED
from common.db import get_pool


class CreateTaskFromIntentUseCase:
    """Creates a canonical AE3 v2 task while preserving external idempotency semantics.

    Uses PostgreSQL advisory lock (pg_try_advisory_xact_lock) per zone_id to
    prevent duplicate task creation under concurrent requests.
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
            raise TaskCreateError("start_cycle_missing_idempotency_key", "idempotency_key is required")

        # Fast path: check idempotency without lock
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
                    f"Terminal intent idempotency_key={normalized_key} for zone_id={zone_id} "
                    "has no canonical task"
                ),
                details={"idempotency_key": normalized_key},
            )

        # Acquire advisory lock for zone to make the check+create atomic
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
                        f"Zone {zone_id} is locked by concurrent request",
                        details={"zone_id": zone_id},
                    )

                # Within the lock: check active tasks and lease
                active_task_getter = getattr(self._task_repository, "get_active_for_zone_with_conn", None)
                if callable(active_task_getter):
                    active_task = await active_task_getter(zone_id=zone_id, conn=conn)
                else:
                    active_task = await self._task_repository.get_active_for_zone(zone_id=zone_id)
                if active_task is not None:
                    raise TaskCreateError(
                        ErrorCodes.START_CYCLE_ZONE_BUSY,
                        f"Zone {zone_id} already has active task_id={active_task.id}",
                        details={"active_task_id": active_task.id, "active_task_status": active_task.status},
                    )

                active_lease = await self._zone_lease_repository.get(zone_id=zone_id, conn=conn)
                lease_until = self._normalize_utc(active_lease.leased_until) if active_lease is not None else None
                if active_lease is not None and lease_until is not None and lease_until > self._normalize_utc(now):
                    raise TaskCreateError(
                        ErrorCodes.START_CYCLE_ZONE_BUSY,
                        f"Zone {zone_id} already has active lease owner={active_lease.owner}",
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
                            f"Zone {zone_id} is blocked by active alert "
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
                    conn=conn,
                )
                if created_task is not None:
                    TASK_CREATED.labels(topology=meta.topology).inc()
                    return TaskCreationResult(task=created_task, created=True)

        # INSERT returned None (UNIQUE conflict on idempotency_key from concurrent req)
        deduplicated_task = await self._task_repository.get_by_idempotency_key(
            zone_id=zone_id,
            idempotency_key=normalized_key,
        )
        if deduplicated_task is not None:
            return TaskCreationResult(task=deduplicated_task, created=False)

        raise TaskCreateError("ae3_task_create_failed", f"Unable to create canonical task for zone_id={zone_id}")

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

    def _normalize_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)
