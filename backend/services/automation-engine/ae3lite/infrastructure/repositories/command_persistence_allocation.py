"""PgAeCommandRepository allocation: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping, Optional

import asyncpg

from ae3lite.domain.errors import CommandPublishError


@dataclass(frozen=True)
class CommandPersistenceAllocationPorts:
    claim_token_holds_task: Callable[..., Awaitable[Any]]
    normalize_timestamp: Callable[..., Any]
    global_get_pool: Callable[..., Any]


class CommandPersistenceAllocation:
    def __init__(self, ports: CommandPersistenceAllocationPorts) -> None:
        self._ports = ports

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
        pool = await self._ports.global_get_pool()
        normalized_now = self._ports.normalize_timestamp(now)
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    if not await self._ports.claim_token_holds_task(
                        conn,
                        task_id=task_id,
                        owner=owner,
                        claim_generation=claim_generation,
                        payload=payload,
                    ):
                        return None
                    row = await conn.fetchrow(
                        """
                        INSERT INTO ae_commands (
                            task_id,
                            step_no,
                            node_uid,
                            channel,
                            payload,
                            stage_name,
                            publish_status,
                            created_at,
                            updated_at
                        )
                        VALUES ($1, $2, $3, $4, $5::jsonb, $6, 'pending', $7, $7)
                        RETURNING id
                        """,
                        task_id,
                        step_no,
                        node_uid,
                        channel,
                        dict(payload),
                        stage_name or None,
                        normalized_now,
                    )
        except asyncpg.exceptions.ForeignKeyViolationError:
            # Родительская строка `ae_tasks` была удалена между шагом планирования и INSERT
            # (например, raw DELETE в e2e или админском сценарии).
            return None
        except asyncpg.exceptions.UniqueViolationError:
            return None
        return int(row["id"])

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
        """Атомарно выделяет step_no и создаёт строку `ae_commands` под advisory lock task_id.

        При заданном `planner_step` переиспользует непубликованную строку (pending/published_unconfirmed)
        с тем же ключом — стабильный cmd_id для retry.

        Возвращает ``(ae_command_id, step_no, reused, publish_status)``.
        """
        pool = await self._ports.global_get_pool()
        normalized_now = self._ports.normalize_timestamp(now)
        normalized_planner_step = str(planner_step or "").strip() or None
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("SELECT pg_advisory_xact_lock($1::bigint)", int(task_id))
                    # Локальная проверка token до INSERT. Это не MQTT/HL fencing.
                    if not await self._ports.claim_token_holds_task(
                        conn,
                        task_id=task_id,
                        owner=owner,
                        claim_generation=claim_generation,
                        payload=payload,
                    ):
                        return None
                    if normalized_planner_step:
                        existing = await conn.fetchrow(
                            """
                            SELECT id, step_no, publish_status, node_uid, channel, payload
                            FROM ae_commands
                            WHERE task_id = $1
                              AND planner_step = $2
                              AND publish_status IN ('pending', 'published_unconfirmed')
                            FOR UPDATE
                            LIMIT 1
                            """,
                            task_id,
                            normalized_planner_step,
                        )
                        if existing is not None:
                            step_no = int(existing["step_no"])
                            ae_command_id = int(existing["id"])
                            existing_publish_status = str(existing["publish_status"] or "pending").strip()
                            stored_payload = existing["payload"]
                            if (
                                existing["node_uid"] != node_uid
                                or existing["channel"] != channel
                                or stored_payload.get("cmd") != payload.get("cmd")
                                or stored_payload.get("params") != payload.get("params")
                            ):
                                raise CommandPublishError(
                                    f"command_identity_conflict: task={task_id} planner_step={normalized_planner_step}"
                                )
                            return ae_command_id, step_no, True, existing_publish_status

                    next_row = await conn.fetchrow(
                        """
                        SELECT COALESCE(MAX(step_no), 0) + 1 AS next_step_no
                        FROM ae_commands
                        WHERE task_id = $1
                        """,
                        task_id,
                    )
                    step_no = int(next_row["next_step_no"]) if next_row is not None else 1
                    stored_payload = dict(payload)
                    stored_payload["cmd_id"] = f"ae3-t{task_id}-z{zone_id}-s{step_no}"
                    row = await conn.fetchrow(
                        """
                        INSERT INTO ae_commands (
                            task_id,
                            step_no,
                            planner_step,
                            node_uid,
                            channel,
                            payload,
                            stage_name,
                            publish_status,
                            created_at,
                            updated_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, 'pending', $8, $8)
                        RETURNING id
                        """,
                        task_id,
                        step_no,
                        normalized_planner_step,
                        node_uid,
                        channel,
                        stored_payload,
                        stage_name or None,
                        normalized_now,
                    )
        except asyncpg.exceptions.ForeignKeyViolationError:
            return None
        if row is None:
            return None
        return int(row["id"]), step_no, False, "pending"

    async def get_next_step_no(self, *, task_id: int) -> int:
        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(MAX(step_no), 0) + 1 AS next_step_no
                FROM ae_commands
                WHERE task_id = $1
                """,
                task_id,
            )
        return int(row["next_step_no"]) if row is not None else 1
