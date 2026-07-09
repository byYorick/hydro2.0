"""Фоновый reconcile intent в claimed/running при terminal ae_task."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from ae3lite.application.dto import OrphanIntentReconcileResult
from ae3lite.infrastructure.metrics import ORPHAN_INTENT_RECONCILED

logger = logging.getLogger(__name__)

SyncTerminalFn = Callable[..., Awaitable[bool]]


class OrphanIntentReconcileUseCase:
    """Периодически синхронизирует terminal ae_tasks с non-terminal intents."""

    def __init__(
        self,
        *,
        zone_intent_repository: Any,
        batch_limit: int = 16,
    ) -> None:
        self._zone_intent_repository = zone_intent_repository
        self._batch_limit = max(1, min(int(batch_limit), 32))

    async def run(
        self,
        *,
        now: datetime,
        sync_terminal_fn: SyncTerminalFn,
    ) -> OrphanIntentReconcileResult:
        list_orphans = getattr(
            self._zone_intent_repository,
            "list_orphan_active_intents_with_terminal_tasks",
            None,
        )
        if not callable(list_orphans):
            return OrphanIntentReconcileResult(
                scanned_intents=0,
                reconciled_intents=0,
                failed_intents=0,
            )

        rows = await list_orphans(limit=self._batch_limit)
        reconciled_intents = 0
        failed_intents = 0

        for row in rows:
            row_map = dict(row)
            intent_id = int(row_map.get("intent_id") or 0)
            task_id = int(row_map.get("task_id") or 0)
            zone_id = int(row_map.get("zone_id") or 0)
            if intent_id <= 0 or task_id <= 0:
                continue

            task_status = str(row_map.get("task_status") or "").strip().lower()
            success = task_status == "completed"
            try:
                synced = await sync_terminal_fn(
                    intent_id=intent_id,
                    now=now,
                    success=success,
                    error_code=row_map.get("error_code"),
                    error_message=row_map.get("error_message"),
                    task_id=task_id,
                    zone_id=zone_id,
                )
            except Exception:
                failed_intents += 1
                ORPHAN_INTENT_RECONCILED.labels(outcome="failed").inc()
                logger.warning(
                    "Orphan intent reconcile: sync_terminal failed intent_id=%s task_id=%s zone_id=%s",
                    intent_id,
                    task_id,
                    zone_id,
                    exc_info=True,
                )
                continue

            if synced:
                reconciled_intents += 1
                ORPHAN_INTENT_RECONCILED.labels(outcome="succeeded").inc()
            else:
                failed_intents += 1
                ORPHAN_INTENT_RECONCILED.labels(outcome="failed").inc()

        return OrphanIntentReconcileResult(
            scanned_intents=len(rows),
            reconciled_intents=reconciled_intents,
            failed_intents=failed_intents,
        )


__all__ = ["OrphanIntentReconcileUseCase"]
