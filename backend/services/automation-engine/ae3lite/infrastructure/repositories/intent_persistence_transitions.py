"""PgZoneIntentRepository transitions: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from ae3lite.infrastructure.repositories.intent_persistence_shared import (
    _TRANSIENT_RETRYABLE_ERROR_CODES,
    _affected_rows,
    logger,
)


@dataclass(frozen=True)
class IntentPersistenceTransitionsPorts:
    global_intent_terminal: Callable[..., Any]
    global_execute: Callable[..., Any]
    global_fetch: Callable[..., Any]


class IntentPersistenceTransitions:
    def __init__(self, ports: IntentPersistenceTransitionsPorts) -> None:
        self._ports = ports

    async def mark_running(self, *, intent_id: int, now: datetime) -> bool:
        result = await self._ports.global_execute(
            """
            UPDATE zone_automation_intents
            SET status = 'running',
                updated_at = $2
            WHERE id = $1
              AND status IN ('claimed', 'running')
            """,
            intent_id,
            now,
        )
        return _affected_rows(result) > 0

    async def requeue_claimed_intent(self, *, intent_id: int, now: datetime) -> bool:
        """Return a reactive intent to pending after a task-creation busy race."""
        result = await self._ports.global_execute(
            """
            UPDATE zone_automation_intents
            SET status = 'pending', claimed_at = NULL, updated_at = $2
            WHERE id = $1 AND status = 'claimed'
            """,
            intent_id,
            now,
        )
        return _affected_rows(result) > 0

    async def mark_terminal(
        self,
        *,
        intent_id: int,
        now: datetime,
        success: bool,
        error_code: Optional[str],
        error_message: Optional[str],
    ) -> bool:
        if not success:
            normalized_code = str(error_code or "").strip().lower()
            if normalized_code in {str(code).strip().lower() for code in _TRANSIENT_RETRYABLE_ERROR_CODES}:
                failed_task_rows = await self._ports.global_fetch(
                    """
                    SELECT 1
                    FROM ae_tasks
                    WHERE intent_id = $1
                      AND status = 'failed'
                    LIMIT 1
                    """,
                    intent_id,
                )
                if not failed_task_rows:
                    rows = await self._ports.global_fetch(
                        """
                        SELECT retry_count, max_retries
                        FROM zone_automation_intents
                        WHERE id = $1
                          AND status IN ('pending', 'claimed', 'running')
                        LIMIT 1
                        """,
                        intent_id,
                    )
                    if rows:
                        row = dict(rows[0])
                        retry_count = int(row.get("retry_count") or 0)
                        max_retries = max(1, int(row.get("max_retries") or 3))
                        if retry_count + 1 < max_retries:
                            backoff_sec = min(300, 30 * (retry_count + 1))
                            retry_at = now + timedelta(seconds=backoff_sec)
                            result = await self._ports.global_execute(
                                """
                                UPDATE zone_automation_intents
                                SET status = 'pending',
                                    retry_count = retry_count + 1,
                                    completed_at = NULL,
                                    updated_at = $2,
                                    not_before = $3,
                                    error_code = $4,
                                    error_message = $5
                                WHERE id = $1
                                  AND status IN ('pending', 'claimed', 'running')
                                """,
                                intent_id,
                                now,
                                retry_at,
                                error_code,
                                error_message,
                            )
                            if _affected_rows(result) > 0:
                                logger.info(
                                    "AE3 intent requeued after transient failure: intent_id=%s code=%s retry_count=%s",
                                    intent_id,
                                    normalized_code,
                                    retry_count + 1,
                                )
                                return True

        status = "completed" if success else "failed"
        result = await self._ports.global_execute(
            """
            UPDATE zone_automation_intents
            SET status = $2,
                completed_at = $3,
                updated_at = $3,
                error_code = $4,
                error_message = $5
            WHERE id = $1
              AND status IN ('pending', 'claimed', 'running')
            """,
            intent_id,
            status,
            now,
            error_code if not success else None,
            error_message if not success else None,
        )
        if _affected_rows(result) > 0:
            self._ports.global_intent_terminal().labels(status=status).inc()
            return True

        # Idempotent replay of the same terminal result is a successful sync,
        # but must not inflate the transition metric. A different terminal
        # state (or a missing intent) remains a CAS conflict for the worker.
        terminal_rows = await self._ports.global_fetch(
            """
            SELECT status
            FROM zone_automation_intents
            WHERE id = $1
            LIMIT 1
            """,
            intent_id,
        )
        return bool(terminal_rows and str(terminal_rows[0].get("status") or "").strip().lower() == status)
