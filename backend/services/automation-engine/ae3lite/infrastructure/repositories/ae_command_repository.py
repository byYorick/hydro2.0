"""PostgreSQL-репозиторий записей выполнения команд AE3-Lite."""

from __future__ import annotations
from functools import cached_property

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

import asyncpg

from common.db import get_pool
from ae3lite.domain.errors import CommandPublishError

# Ставится в payload только после успешной записи last_dose_at/hold.
# Не колонка: повторный startup видит DONE без этого флага и учитывает дозу ещё раз.


from ae3lite.infrastructure.repositories.command_persistence_shared import AE3_DOSE_ACCOUNTED_KEY, _AE3_FAIL_SAFE_KEY

from ae3lite.infrastructure.repositories.command_persistence_authority import (
    CommandPersistenceAuthority,
    CommandPersistenceAuthorityPorts,
)
from ae3lite.infrastructure.repositories.command_persistence_allocation import (
    CommandPersistenceAllocation,
    CommandPersistenceAllocationPorts,
)
from ae3lite.infrastructure.repositories.command_persistence_publication import (
    CommandPersistencePublication,
    CommandPersistencePublicationPorts,
)
from ae3lite.infrastructure.repositories.command_persistence_reconciliation import (
    CommandPersistenceReconciliation,
    CommandPersistenceReconciliationPorts,
)
from ae3lite.infrastructure.repositories.command_persistence_legacy_reads import (
    CommandPersistenceLegacyReads,
    CommandPersistenceLegacyReadsPorts,
)
from ae3lite.infrastructure.repositories.command_persistence_queries import (
    CommandPersistenceQueries,
    CommandPersistenceQueriesPorts,
)


class PgAeCommandRepository:
    """Сохраняет шаги команд AE3-Lite и разрешает legacy-связки с history-logger."""

    @cached_property
    def _command_persistence_authority(self):
        return CommandPersistenceAuthority(
            CommandPersistenceAuthorityPorts(
                global_get_pool=lambda *args, **kwargs: get_pool(*args, **kwargs),
            )
        )

    @cached_property
    def _command_persistence_allocation(self):
        return CommandPersistenceAllocation(
            CommandPersistenceAllocationPorts(
                claim_token_holds_task=lambda *args, **kwargs: self._claim_token_holds_task(*args, **kwargs),
                normalize_timestamp=lambda *args, **kwargs: self._normalize_timestamp(*args, **kwargs),
                global_get_pool=lambda *args, **kwargs: get_pool(*args, **kwargs),
            )
        )

    @cached_property
    def _command_persistence_publication(self):
        return CommandPersistencePublication(
            CommandPersistencePublicationPorts(
                normalize_timestamp=lambda *args, **kwargs: self._normalize_timestamp(*args, **kwargs),
                global_get_pool=lambda *args, **kwargs: get_pool(*args, **kwargs),
            )
        )

    @cached_property
    def _command_persistence_reconciliation(self):
        return CommandPersistenceReconciliation(
            CommandPersistenceReconciliationPorts(
                normalize_timestamp=lambda *args, **kwargs: self._normalize_timestamp(*args, **kwargs),
                global_get_pool=lambda *args, **kwargs: get_pool(*args, **kwargs),
            )
        )

    @cached_property
    def _command_persistence_legacy_reads(self):
        return CommandPersistenceLegacyReads(
            CommandPersistenceLegacyReadsPorts(
                global_get_pool=lambda *args, **kwargs: get_pool(*args, **kwargs),
            )
        )

    @cached_property
    def _command_persistence_queries(self):
        return CommandPersistenceQueries(
            CommandPersistenceQueriesPorts(
                global_get_pool=lambda *args, **kwargs: get_pool(*args, **kwargs),
            )
        )

    def _normalize_timestamp(self, value: Optional[datetime]) -> Optional[datetime]:
        return self._command_persistence_queries.normalize_timestamp(value=value)

    async def _claim_token_holds_task(
        self,
        conn: Any,
        *,
        task_id: int,
        owner: Optional[str],
        claim_generation: Optional[int],
        payload: Mapping[str, Any] | None = None,
    ) -> bool:
        return await self._command_persistence_authority.claim_token_holds_task(
            conn=conn, task_id=task_id, owner=owner, claim_generation=claim_generation, payload=payload
        )

    async def assert_publish_authority(self, *, task_id, owner, claim_generation, payload):
        return await self._command_persistence_authority.assert_publish_authority(
            task_id=task_id, owner=owner, claim_generation=claim_generation, payload=payload
        )

    async def create_pending(
        self,
        *,
        task_id: int,
        step_no: int,
        node_uid: str,
        channel: str,
        payload: Mapping[str, Any],
        now: datetime,
        stage_name: Optional[str] = None,
        owner: Optional[str] = None,
        claim_generation: Optional[int] = None,
    ) -> Optional[int]:
        return await self._command_persistence_allocation.create_pending(
            task_id=task_id,
            step_no=step_no,
            node_uid=node_uid,
            channel=channel,
            payload=payload,
            now=now,
            stage_name=stage_name,
            owner=owner,
            claim_generation=claim_generation,
        )

    async def allocate_and_create_pending(
        self,
        *,
        task_id: int,
        zone_id: int,
        node_uid: str,
        channel: str,
        payload: Mapping[str, Any],
        now: datetime,
        stage_name: Optional[str] = None,
        planner_step: Optional[str] = None,
        owner: Optional[str] = None,
        claim_generation: Optional[int] = None,
    ) -> Optional[tuple[int, int, bool, str]]:
        return await self._command_persistence_allocation.allocate_and_create_pending(
            task_id=task_id,
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            payload=payload,
            now=now,
            stage_name=stage_name,
            planner_step=planner_step,
            owner=owner,
            claim_generation=claim_generation,
        )

    async def mark_publish_published_unconfirmed(self, *, ae_command_id: int, now: datetime) -> bool:
        return await self._command_persistence_publication.mark_publish_published_unconfirmed(
            ae_command_id=ae_command_id, now=now
        )

    async def mark_publish_accepted(
        self,
        *,
        ae_command_id: int,
        external_id: str,
        now: datetime,
    ) -> bool:
        return await self._command_persistence_publication.mark_publish_accepted(
            ae_command_id=ae_command_id, external_id=external_id, now=now
        )

    async def record_publish_retryable_error(
        self,
        *,
        ae_command_id: int,
        last_error: str,
        now: datetime,
        outcome_unknown: bool,
    ) -> bool:
        return await self._command_persistence_publication.record_publish_retryable_error(
            ae_command_id=ae_command_id, last_error=last_error, now=now, outcome_unknown=outcome_unknown
        )

    async def mark_publish_failed(self, *, ae_command_id: int, last_error: str, now: datetime) -> bool:
        return await self._command_persistence_publication.mark_publish_failed(
            ae_command_id=ae_command_id, last_error=last_error, now=now
        )

    async def update_from_legacy(
        self,
        *,
        ae_command_id: int,
        external_id: Optional[str],
        ack_received_at: Optional[datetime],
        terminal_status: Optional[str],
        terminal_at: Optional[datetime],
        last_error: Optional[str],
        now: datetime,
    ) -> Optional[Mapping[str, Any]]:
        return await self._command_persistence_reconciliation.update_from_legacy(
            ae_command_id=ae_command_id,
            external_id=external_id,
            ack_received_at=ack_received_at,
            terminal_status=terminal_status,
            terminal_at=terminal_at,
            last_error=last_error,
            now=now,
        )

    async def mark_recovery_batch_resume(
        self,
        *,
        ae_command_id: int,
        stage_name: str,
        stage_execution_token: str,
        now: datetime,
    ) -> bool:
        return await self._command_persistence_reconciliation.mark_recovery_batch_resume(
            ae_command_id=ae_command_id, stage_name=stage_name, stage_execution_token=stage_execution_token, now=now
        )

    async def resolve_greenhouse_uid(self, *, zone_id: int) -> Optional[str]:
        return await self._command_persistence_legacy_reads.resolve_greenhouse_uid(zone_id=zone_id)

    async def resolve_legacy_command_id(self, *, zone_id: int, cmd_id: str) -> Optional[int]:
        return await self._command_persistence_legacy_reads.resolve_legacy_command_id(zone_id=zone_id, cmd_id=cmd_id)

    async def get_legacy_command_by_id(self, *, external_id: str) -> Optional[Mapping[str, Any]]:
        return await self._command_persistence_legacy_reads.get_legacy_command_by_id(external_id=external_id)

    async def get_legacy_command_by_cmd_id(self, *, zone_id: int, cmd_id: str) -> Optional[Mapping[str, Any]]:
        return await self._command_persistence_legacy_reads.get_legacy_command_by_cmd_id(zone_id=zone_id, cmd_id=cmd_id)

    async def get_node_runtime_context(self, *, node_uid: str) -> Optional[Mapping[str, Any]]:
        return await self._command_persistence_legacy_reads.get_node_runtime_context(node_uid=node_uid)

    async def get_latest_for_task(
        self,
        *,
        task_id: int,
        exclude_fail_safe: bool = True,
    ) -> Optional[Mapping[str, Any]]:
        return await self._command_persistence_queries.get_latest_for_task(
            task_id=task_id, exclude_fail_safe=exclude_fail_safe
        )

    async def mark_dose_accounted(self, *, ae_command_id: int, now: datetime) -> bool:
        return await self._command_persistence_reconciliation.mark_dose_accounted(ae_command_id=ae_command_id, now=now)

    async def list_unreconciled_for_terminal_tasks(
        self,
        *,
        limit: int = 100,
    ) -> list[Mapping[str, Any]]:
        return await self._command_persistence_reconciliation.list_unreconciled_for_terminal_tasks(limit=limit)

    async def has_recovery_batch_resume(
        self,
        *,
        task_id: int,
        stage_name: str,
        stage_execution_token: str,
    ) -> bool:
        return await self._command_persistence_reconciliation.has_recovery_batch_resume(
            task_id=task_id, stage_name=stage_name, stage_execution_token=stage_execution_token
        )

    async def get_latest_by_planner_step(
        self,
        *,
        task_id: int,
        planner_step: str,
    ) -> Optional[Mapping[str, Any]]:
        return await self._command_persistence_queries.get_latest_by_planner_step(
            task_id=task_id, planner_step=planner_step
        )

    async def get_by_task_step(self, *, task_id: int, step_no: int) -> Optional[Mapping[str, Any]]:
        return await self._command_persistence_queries.get_by_task_step(task_id=task_id, step_no=step_no)

    async def get_next_step_no(self, *, task_id: int) -> int:
        return await self._command_persistence_allocation.get_next_step_no(task_id=task_id)
