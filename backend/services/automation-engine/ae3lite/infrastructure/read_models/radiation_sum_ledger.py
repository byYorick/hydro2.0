"""История успешных импульсов полива.

Считаются только завершённые irrigation-задачи, у которых команда старта
полива дошла до terminal DONE и в ``commands`` нет иного статуса.
Память процесса не хранит счётчик: после рестарта AE3 читает те же строки.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from common.db import get_pool

IRRIGATION_PULSE_SQL = """
SELECT
    t.id,
    COALESCE(t.completed_at, t.updated_at) AS finished_at,
    t.irrigation_decision_config AS config
FROM ae_tasks t
WHERE t.zone_id = $1
  AND t.task_type = 'irrigation_start'
  AND t.status = 'completed'
  AND t.current_stage = 'completed_run'
  AND t.irrigation_decision_outcome IN ('run', 'degraded_run')
  AND EXISTS (
      SELECT 1
      FROM ae_commands ac
      LEFT JOIN commands c ON c.cmd_id = ac.external_id
      WHERE ac.task_id = t.id
        AND ac.stage_name = 'irrigation_start'
        AND ac.terminal_status = 'DONE'
        AND (c.status IS NULL OR c.status = 'DONE')
  )
ORDER BY COALESCE(t.completed_at, t.updated_at) DESC
LIMIT 400
"""


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


async def fetch_irrigation_pulses(*, zone_id: int) -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(IRRIGATION_PULSE_SQL, int(zone_id))
    pulses: list[dict[str, Any]] = []
    for row in rows:
        moment = row["finished_at"]
        if not isinstance(moment, datetime):
            continue
        pulses.append({"finished_at": _as_utc(moment), "config": row["config"], "liters": None})
    return pulses
