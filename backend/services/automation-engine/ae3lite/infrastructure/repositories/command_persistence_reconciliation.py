"""PgAeCommandRepository reconciliation: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Optional

from ae3lite.infrastructure.repositories.command_persistence_shared import _AE3_FAIL_SAFE_KEY, AE3_DOSE_ACCOUNTED_KEY


@dataclass(frozen=True)
class CommandPersistenceReconciliationPorts:
    normalize_timestamp: Callable[..., Any]
    global_get_pool: Callable[..., Any]


class CommandPersistenceReconciliation:
    def __init__(self, ports: CommandPersistenceReconciliationPorts) -> None:
        self._ports = ports

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
        pool = await self._ports.global_get_pool()
        normalized_ack_received_at = self._ports.normalize_timestamp(ack_received_at)
        normalized_terminal_at = self._ports.normalize_timestamp(terminal_at)
        normalized_now = self._ports.normalize_timestamp(now)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_commands
                SET external_id = COALESCE($2, external_id),
                    publish_status = CASE
                        WHEN COALESCE($2, external_id) IS NOT NULL THEN 'accepted'
                        ELSE publish_status
                    END,
                    ack_received_at = COALESCE($3, ack_received_at),
                    terminal_status = COALESCE($4, terminal_status),
                    terminal_at = COALESCE($5, terminal_at),
                    last_error = COALESCE($6, last_error),
                    updated_at = $7
                WHERE id = $1
                RETURNING *
                """,
                ae_command_id,
                external_id,
                normalized_ack_received_at,
                terminal_status,
                normalized_terminal_at,
                last_error,
                normalized_now,
            )
        return dict(row) if row is not None else None

    async def mark_recovery_batch_resume(
        self,
        *,
        ae_command_id: int,
        stage_name: str,
        stage_execution_token: str,
        now: datetime,
    ) -> bool:
        """Помечает command-stage как требующий resume полного RuntimePlan batch."""
        pool = await self._ports.global_get_pool()
        normalized_now = self._ports.normalize_timestamp(now)
        marker = {
            "stage": stage_name,
            "stage_execution_token": stage_execution_token,
        }
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_commands
                SET payload = jsonb_set(
                        COALESCE(payload, '{}'::jsonb),
                        '{_ae3_recovery_resume}',
                        $2::jsonb,
                        true
                    ),
                    updated_at = $3
                WHERE id = $1
                RETURNING id
                """,
                ae_command_id,
                marker,
                normalized_now,
            )
        return row is not None

    async def mark_dose_accounted(self, *, ae_command_id: int, now: datetime) -> bool:
        """Пометить dose учтённой в PID. Fail-safe и не-dose строки не трогает.

        Флаг пишется только вызывающим кодом после успешного last_dose_at/hold.
        """
        pool = await self._ports.global_get_pool()
        normalized_now = self._ports.normalize_timestamp(now)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_commands
                SET payload = jsonb_set(
                        COALESCE(payload, '{}'::jsonb),
                        $3::text[],
                        'true'::jsonb,
                        true
                    ),
                    updated_at = $2
                WHERE id = $1
                  AND terminal_status = 'DONE'
                  AND lower(COALESCE(payload->>'cmd', '')) = 'dose'
                  AND NOT (COALESCE(payload, '{}'::jsonb) @> $4::jsonb)
                RETURNING id
                """,
                int(ae_command_id),
                normalized_now,
                [AE3_DOSE_ACCOUNTED_KEY],
                {_AE3_FAIL_SAFE_KEY: True},
            )
        return row is not None

    async def list_unreconciled_for_terminal_tasks(
        self,
        *,
        limit: int = 100,
    ) -> list[Mapping[str, Any]]:
        """Команды terminal-задач, которые ещё нужно сверить или учесть.

        В выборке три независимых хвоста, без синтеза terminal status:
        accepted/NULL, published_unconfirmed/NULL и DONE dose без маркера
        ``_ae3_dose_accounted``. Fail-safe строки исключены. Маркер не
        выводится из terminal_status: его ставит учёт PID.
        """
        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ac.*
                FROM ae_commands ac
                JOIN ae_tasks t ON t.id = ac.task_id
                WHERE t.status IN ('completed', 'failed', 'cancelled')
                  AND NOT (COALESCE(ac.payload, '{}'::jsonb) @> $2::jsonb)
                  AND (
                    (
                      ac.publish_status = 'accepted'
                      AND ac.terminal_status IS NULL
                    )
                    OR (
                      ac.publish_status = 'published_unconfirmed'
                      AND ac.terminal_status IS NULL
                    )
                    OR (
                      ac.terminal_status = 'DONE'
                      AND lower(COALESCE(ac.payload->>'cmd', '')) = 'dose'
                      AND NOT (COALESCE(ac.payload, '{}'::jsonb) @> $3::jsonb)
                    )
                  )
                ORDER BY ac.created_at ASC, ac.id ASC
                LIMIT $1
                """,
                max(1, min(1000, int(limit))),
                {_AE3_FAIL_SAFE_KEY: True},
                {AE3_DOSE_ACCOUNTED_KEY: True},
            )
        return [dict(row) for row in rows]

    async def has_recovery_batch_resume(
        self,
        *,
        task_id: int,
        stage_name: str,
        stage_execution_token: str,
    ) -> bool:
        """True, если у задачи есть resume-marker текущего stage execution."""
        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id
                FROM ae_commands
                WHERE task_id = $1
                  AND NOT (COALESCE(payload, '{}'::jsonb) @> '{"_ae3_fail_safe": true}'::jsonb)
                  AND COALESCE(payload->'_ae3_recovery_resume'->>'stage', '') = $2
                  AND COALESCE(
                        payload->'_ae3_recovery_resume'->>'stage_execution_token',
                        ''
                      ) = $3
                ORDER BY step_no DESC, id DESC
                LIMIT 1
                """,
                task_id,
                str(stage_name or "").strip(),
                str(stage_execution_token or "").strip(),
            )
        return row is not None
