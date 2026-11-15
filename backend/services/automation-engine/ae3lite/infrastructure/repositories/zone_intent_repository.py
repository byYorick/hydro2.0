"""PostgreSQL-репозиторий жизненного цикла zone automation intent в AE3-Lite."""

from __future__ import annotations
from functools import cached_property

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional

from ae3lite.api.contracts import (
    StartCycleRequest,
    StartIrrigationRequest,
    StartLightingTickRequest,
    StartSolutionChangeRequest,
    StartSolutionTopupRequest,
)
from ae3lite.domain.errors import ErrorCodes, TaskCreateError
from ae3lite.domain.intent_metadata import IntentMetadata
from ae3lite.infrastructure.metrics import INTENT_CLAIMED, INTENT_STALE_RECLAIMED, INTENT_TERMINAL
from common.db import execute, fetch


from ae3lite.infrastructure.repositories.intent_persistence_shared import (
    logger,
    _affected_rows,
    _TERMINAL_STATUSES,
    _ACTIVE_STATUSES,
    _is_retryable_failed_intent,
    _TRANSIENT_RETRYABLE_ERROR_CODES,
)

from ae3lite.infrastructure.repositories.intent_persistence_entry_points import (
    IntentPersistenceEntryPoints,
    IntentPersistenceEntryPointsPorts,
)
from ae3lite.infrastructure.repositories.intent_persistence_creation import (
    IntentPersistenceCreation,
    IntentPersistenceCreationPorts,
)
from ae3lite.infrastructure.repositories.intent_persistence_claim import (
    IntentPersistenceClaim,
    IntentPersistenceClaimPorts,
)
from ae3lite.infrastructure.repositories.intent_persistence_metadata import (
    IntentPersistenceMetadata,
    IntentPersistenceMetadataPorts,
)
from ae3lite.infrastructure.repositories.intent_persistence_transitions import (
    IntentPersistenceTransitions,
    IntentPersistenceTransitionsPorts,
)
from ae3lite.infrastructure.repositories.intent_persistence_recovery import (
    IntentPersistenceRecovery,
    IntentPersistenceRecoveryPorts,
)


class PgZoneIntentRepository:
    """Управляет жизненным циклом `zone_automation_intents` для AE3-Lite."""

    @cached_property
    def _intent_persistence_entry_points(self):
        return IntentPersistenceEntryPoints(
            IntentPersistenceEntryPointsPorts(
                claim_by_idempotency_key=lambda *args, **kwargs: self._claim_by_idempotency_key(*args, **kwargs),
            )
        )

    @cached_property
    def _intent_persistence_creation(self):
        return IntentPersistenceCreation(
            IntentPersistenceCreationPorts(
                global_fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
            )
        )

    @cached_property
    def _intent_persistence_claim(self):
        return IntentPersistenceClaim(
            IntentPersistenceClaimPorts(
                global_intent_claimed=lambda: INTENT_CLAIMED,
                global_intent_stale_reclaimed=lambda: INTENT_STALE_RECLAIMED,
                global_fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
            )
        )

    @cached_property
    def _intent_persistence_metadata(self):
        return IntentPersistenceMetadata(IntentPersistenceMetadataPorts())

    @cached_property
    def _intent_persistence_transitions(self):
        return IntentPersistenceTransitions(
            IntentPersistenceTransitionsPorts(
                global_intent_terminal=lambda: INTENT_TERMINAL,
                global_execute=lambda *args, **kwargs: execute(*args, **kwargs),
                global_fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
            )
        )

    @cached_property
    def _intent_persistence_recovery(self):
        return IntentPersistenceRecovery(
            IntentPersistenceRecoveryPorts(
                global_fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
            )
        )

    async def claim_start_cycle(
        self,
        *,
        zone_id: int,
        req: StartCycleRequest,
        now: datetime,
        claimed_stale_after_sec: int = 180,
        running_stale_after_sec: int = 1800,
    ) -> dict[str, Any]:
        return await self._intent_persistence_entry_points.claim_start_cycle(
            zone_id=zone_id,
            req=req,
            now=now,
            claimed_stale_after_sec=claimed_stale_after_sec,
            running_stale_after_sec=running_stale_after_sec,
        )

    async def claim_start_irrigation(
        self,
        *,
        zone_id: int,
        req: StartIrrigationRequest,
        now: datetime,
        claimed_stale_after_sec: int = 180,
        running_stale_after_sec: int = 1800,
    ) -> dict[str, Any]:
        return await self._intent_persistence_entry_points.claim_start_irrigation(
            zone_id=zone_id,
            req=req,
            now=now,
            claimed_stale_after_sec=claimed_stale_after_sec,
            running_stale_after_sec=running_stale_after_sec,
        )

    async def claim_start_lighting_tick(
        self,
        *,
        zone_id: int,
        req: StartLightingTickRequest,
        now: datetime,
        claimed_stale_after_sec: int = 180,
        running_stale_after_sec: int = 1800,
    ) -> dict[str, Any]:
        return await self._intent_persistence_entry_points.claim_start_lighting_tick(
            zone_id=zone_id,
            req=req,
            now=now,
            claimed_stale_after_sec=claimed_stale_after_sec,
            running_stale_after_sec=running_stale_after_sec,
        )

    async def claim_start_solution_topup(
        self,
        *,
        zone_id: int,
        req: StartSolutionTopupRequest,
        now: datetime,
        claimed_stale_after_sec: int = 180,
        running_stale_after_sec: int = 1800,
    ) -> dict[str, Any]:
        return await self._intent_persistence_entry_points.claim_start_solution_topup(
            zone_id=zone_id,
            req=req,
            now=now,
            claimed_stale_after_sec=claimed_stale_after_sec,
            running_stale_after_sec=running_stale_after_sec,
        )

    async def upsert_irrigation_replay_intent(
        self,
        *,
        zone_id: int,
        idempotency_key: str,
        topology: str,
        now: datetime,
        mode: str = "normal",
        requested_duration_sec: int | None = None,
        source: str = "ae3_startup_recovery",
        failed_task_id: int | None = None,
    ) -> int | None:
        return await self._intent_persistence_creation.upsert_irrigation_replay_intent(
            zone_id=zone_id,
            idempotency_key=idempotency_key,
            topology=topology,
            now=now,
            mode=mode,
            requested_duration_sec=requested_duration_sec,
            source=source,
            failed_task_id=failed_task_id,
        )

    async def claim_pending_intent_by_id(
        self,
        *,
        zone_id: int,
        intent_id: int,
        now: datetime,
        claimed_stale_after_sec: int = 180,
        running_stale_after_sec: int = 1800,
    ) -> dict[str, Any]:
        return await self._intent_persistence_claim.claim_pending_intent_by_id(
            zone_id=zone_id,
            intent_id=intent_id,
            now=now,
            claimed_stale_after_sec=claimed_stale_after_sec,
            running_stale_after_sec=running_stale_after_sec,
        )

    async def claim_start_solution_change(
        self,
        *,
        zone_id: int,
        req: StartSolutionChangeRequest,
        now: datetime,
        claimed_stale_after_sec: int = 180,
        running_stale_after_sec: int = 1800,
    ) -> dict[str, Any]:
        return await self._intent_persistence_entry_points.claim_start_solution_change(
            zone_id=zone_id,
            req=req,
            now=now,
            claimed_stale_after_sec=claimed_stale_after_sec,
            running_stale_after_sec=running_stale_after_sec,
        )

    async def upsert_solution_topup_intent(
        self,
        *,
        zone_id: int,
        idempotency_key: str,
        source: str,
        trigger: str,
        topology: str,
        now: datetime,
        mode: str = "normal",
    ) -> int | None:
        return await self._intent_persistence_creation.upsert_solution_topup_intent(
            zone_id=zone_id,
            idempotency_key=idempotency_key,
            source=source,
            trigger=trigger,
            topology=topology,
            now=now,
            mode=mode,
        )

    async def _execution_busy_row(self, *, zone_id: int, now: datetime) -> dict[str, Any] | None:
        return await self._intent_persistence_claim.execution_busy_row(zone_id=zone_id, now=now)

    async def _claim_by_idempotency_key(
        self,
        *,
        zone_id: int,
        idempotency_key: str,
        now: datetime,
        claimed_stale_after_sec: int,
        running_stale_after_sec: int,
    ) -> dict[str, Any]:
        return await self._intent_persistence_claim.claim_by_idempotency_key(
            zone_id=zone_id,
            idempotency_key=idempotency_key,
            now=now,
            claimed_stale_after_sec=claimed_stale_after_sec,
            running_stale_after_sec=running_stale_after_sec,
        )

    def extract_intent_metadata(
        self,
        *,
        source: str,
        intent_row: Mapping[str, Any],
    ) -> IntentMetadata:
        return self._intent_persistence_metadata.extract_intent_metadata(source=source, intent_row=intent_row)

    async def mark_running(self, *, intent_id: int, now: datetime) -> bool:
        return await self._intent_persistence_transitions.mark_running(intent_id=intent_id, now=now)

    async def requeue_claimed_intent(self, *, intent_id: int, now: datetime) -> bool:
        return await self._intent_persistence_transitions.requeue_claimed_intent(intent_id=intent_id, now=now)

    async def mark_terminal(
        self,
        *,
        intent_id: int,
        now: datetime,
        success: bool,
        error_code: Optional[str],
        error_message: Optional[str],
    ) -> bool:
        return await self._intent_persistence_transitions.mark_terminal(
            intent_id=intent_id, now=now, success=success, error_code=error_code, error_message=error_message
        )

    async def list_orphan_active_intents_with_terminal_tasks(self, *, limit: int = 16) -> list[dict[str, Any]]:
        return await self._intent_persistence_recovery.list_orphan_active_intents_with_terminal_tasks(limit=limit)


__all__ = ["PgZoneIntentRepository"]
