"""PgZoneIntentRepository recovery: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class IntentPersistenceRecoveryPorts:
    global_fetch: Callable[..., Any]


class IntentPersistenceRecovery:
    def __init__(self, ports: IntentPersistenceRecoveryPorts) -> None:
        self._ports = ports

    async def list_orphan_active_intents_with_terminal_tasks(self, *, limit: int = 16) -> list[dict[str, Any]]:
        """Возвращает intents в claimed/running, у которых связанная ae_task уже terminal."""
        bounded_limit = max(1, min(int(limit), 32))
        rows = await self._ports.global_fetch(
            """
            SELECT
                intents.id AS intent_id,
                intents.zone_id,
                tasks.id AS task_id,
                tasks.status AS task_status,
                tasks.error_code,
                tasks.error_message
            FROM zone_automation_intents AS intents
            INNER JOIN ae_tasks AS tasks ON tasks.intent_id = intents.id
            WHERE intents.status IN ('claimed', 'running')
              AND tasks.status IN ('completed', 'failed', 'cancelled')
            ORDER BY tasks.updated_at ASC, intents.id ASC
            LIMIT $1
            """,
            bounded_limit,
        )
        return [dict(row) for row in rows]
