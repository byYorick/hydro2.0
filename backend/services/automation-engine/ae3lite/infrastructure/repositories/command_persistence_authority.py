"""PgAeCommandRepository authority: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from ae3lite.domain.errors import CommandPublishError


@dataclass(frozen=True)
class CommandPersistenceAuthorityPorts:
    global_get_pool: Callable[..., Any]


class CommandPersistenceAuthority:
    def __init__(self, ports: CommandPersistenceAuthorityPorts) -> None:
        self._ports = ports

    async def claim_token_holds_task(
        self,
        conn: Any,
        *,
        task_id: int,
        owner: Optional[str],
        claim_generation: Optional[int],
        payload: Mapping[str, Any] | None = None,
    ) -> bool:
        """True, если token ещё держит задачу. owner=None — repository-only allocation.

        Совпадение строки до HTTP к history-logger не является MQTT fencing.
        """
        normalized_owner = str(owner or "").strip()
        if owner is None:
            return True
        if claim_generation is None:
            return False
        data = payload or {}
        safe_off = (
            data.get("_ae3_fail_safe") is True
            and data.get("cmd") == "set_relay"
            and isinstance(data.get("params"), Mapping)
            and data["params"].get("state") is False
        )
        row = await conn.fetchrow(
            """
            SELECT 1 FROM ae_tasks t
            WHERE t.id = $1 AND (
                (t.claimed_by = $2 AND t.claim_generation = $3
                 AND t.status IN ('claimed', 'running', 'waiting_command'))
                OR ($4 AND t.status IN ('failed', 'cancelled', 'completed')
                    AND NOT EXISTS (
                        SELECT 1 FROM ae_tasks active
                        WHERE active.zone_id = t.zone_id AND active.id <> t.id
                          AND active.status IN ('pending', 'claimed', 'running', 'waiting_command')
                    ))
            )
            """,
            int(task_id),
            normalized_owner,
            int(claim_generation),
            safe_off,
        )
        return row is not None

    async def assert_publish_authority(self, *, task_id, owner, claim_generation, payload):
        """Последняя локальная проверка перед HTTP; транзакция не держится во время сети."""
        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            if not await self.claim_token_holds_task(
                conn,
                task_id=task_id,
                owner=owner,
                claim_generation=claim_generation,
                payload=payload,
            ):
                raise CommandPublishError(f"claim_ownership_lost: task={task_id}")
