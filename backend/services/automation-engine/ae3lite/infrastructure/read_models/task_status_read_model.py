"""Read-model для канонического endpoint'а статуса задачи AE3-Lite."""

from __future__ import annotations

from typing import Optional

from ae3lite.application.dto import TaskStatusView
from common.db import get_pool


class PgTaskStatusReadModel:
    """Загружает канонический статус задачи AE3, даже если routing зоны потом изменился."""

    async def get_by_task_id(self, *, task_id: int) -> Optional[TaskStatusView]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    tasks.id AS task_id,
                    tasks.zone_id,
                    tasks.task_type,
                    tasks.status,
                    tasks.error_code,
                    tasks.error_message,
                    tasks.created_at,
                    tasks.updated_at,
                    tasks.completed_at
                FROM ae_tasks tasks
                WHERE tasks.id = $1
                LIMIT 1
                """,
                task_id,
            )
        if row is None:
            return None
        return TaskStatusView(
            task_id=int(row["task_id"]),
            zone_id=int(row["zone_id"]),
            task_type=str(row["task_type"]),
            status=str(row["status"]),
            error_code=str(row["error_code"]) if row["error_code"] is not None else None,
            error_message=str(row["error_message"]) if row["error_message"] is not None else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )
