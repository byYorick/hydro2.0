"""Create or resolve canonical AE3-Lite task from legacy scheduler intent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from ae3lite.application.dto import TaskCreationResult
from ae3lite.domain.errors import TaskCreateError
from ae3lite.infrastructure.metrics import TASK_CREATED
from common.db import get_pool


class CreateTaskFromIntentUseCase:
    """Creates a canonical AE3 v2 task while preserving external idempotency semantics.

    Uses PostgreSQL advisory lock (pg_try_advisory_xact_lock) per zone_id to
    prevent duplicate task creation under concurrent requests.
    """

    def __init__(
        self,
        *,
        task_repository: Any,
        zone_lease_repository: Any,
        legacy_intent_mapper: Any,
    ) -> None:
        self._task_repository = task_repository
        self._zone_lease_repository = zone_lease_repository
        self._legacy_intent_mapper = legacy_intent_mapper

    async def run(
        self,
        *,
        zone_id: int,
        source: str,
        idempotency_key: str,
        intent_row: Mapping[str, Any],
        now: datetime,
    ) -> TaskCreationResult:
        normalized_key = str(idempotency_key or "").strip()
        if normalized_key == "":
            raise TaskCreateError("start_cycle_missing_idempotency_key", "idempotency_key is required")

        # Fast path: check idempotency without lock
        existing_task = await self._task_repository.get_by_idempotency_key(idempotency_key=normalized_key)
        if existing_task is not None:
            if existing_task.zone_id != zone_id:
                raise TaskCreateError(
                    "start_cycle_idempotency_key_conflict",
                    f"idempotency_key={normalized_key} already belongs to zone_id={existing_task.zone_id}",
                    details={"conflict_zone_id": existing_task.zone_id},
                )
            return TaskCreationResult(task=existing_task, created=False)

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
                active_task = await self._task_repository.get_active_for_zone(zone_id=zone_id)
                if active_task is not None:
                    raise TaskCreateError(
                        "start_cycle_zone_busy",
                        f"Zone {zone_id} already has active task_id={active_task.id}",
                        details={"active_task_id": active_task.id, "active_task_status": active_task.status},
                    )

                active_lease = await self._zone_lease_repository.get(zone_id=zone_id)
                lease_until = self._normalize_utc(active_lease.leased_until) if active_lease is not None else None
                if active_lease is not None and lease_until is not None and lease_until > self._normalize_utc(now):
                    raise TaskCreateError(
                        "start_cycle_zone_busy",
                        f"Zone {zone_id} already has active lease owner={active_lease.owner}",
                        details={
                            "active_lease_owner": active_lease.owner,
                            "active_lease_until": lease_until.isoformat(),
                        },
                    )

                meta = self._legacy_intent_mapper.extract_intent_metadata(
                    source=source,
                    intent_row=intent_row,
                )
                created_task = await self._task_repository.create_pending(
                    zone_id=zone_id,
                    idempotency_key=normalized_key,
                    topology=meta.topology,
                    intent_source=meta.intent_source,
                    intent_trigger=meta.intent_trigger,
                    intent_id=meta.intent_id,
                    intent_meta=meta.intent_meta,
                    scheduled_for=now,
                    due_at=now,
                    now=now,
                )
                if created_task is not None:
                    TASK_CREATED.labels(topology=meta.topology).inc()
                    return TaskCreationResult(task=created_task, created=True)

        # INSERT returned None (UNIQUE conflict on idempotency_key from concurrent req)
        deduplicated_task = await self._task_repository.get_by_idempotency_key(idempotency_key=normalized_key)
        if deduplicated_task is not None and deduplicated_task.zone_id == zone_id:
            return TaskCreationResult(task=deduplicated_task, created=False)

        raise TaskCreateError("ae3_task_create_failed", f"Unable to create canonical task for zone_id={zone_id}")

    def _normalize_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)
