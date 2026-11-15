"""История импульсов полива, у которых насос уже включился.

Считается каждая irrigation-задача, где команда старта насоса дошла до DONE,
даже если задача потом упала или ушла в irrigation_stop_to_setup.
Итог задачи не важен: пауза и суточные лимиты считаются от этого момента.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from common.db import get_pool

from ae3lite.domain.services.radiation_sum import duration_sec_from_command

IRRIGATION_PULSE_SQL = """
SELECT
    pulse.id,
    pulse.finished_at,
    pulse.config,
    pulse.requested_duration_sec,
    pulse.command_payload
FROM (
    SELECT DISTINCT ON (t.id)
        t.id,
        COALESCE(ac.terminal_at, c.updated_at, ac.updated_at) AS finished_at,
        t.irrigation_decision_config AS config,
        t.irrigation_requested_duration_sec AS requested_duration_sec,
        ac.payload AS command_payload
    FROM ae_tasks t
    JOIN ae_commands ac ON ac.task_id = t.id
    LEFT JOIN commands c ON c.cmd_id = ac.external_id
    WHERE t.zone_id = $1
      AND t.task_type = 'irrigation_start'
      AND ac.stage_name = 'irrigation_start'
      AND ac.terminal_status = 'DONE'
      AND (c.status IS NULL OR c.status = 'DONE')
      AND (
          lower(ac.channel) IN ('pump_main', 'pump_irrigation')
          OR lower(COALESCE(ac.payload->>'cmd', '')) = 'run_pump'
          OR (
              lower(COALESCE(ac.payload->>'cmd', '')) = 'set_relay'
              AND lower(ac.channel) LIKE '%pump%'
          )
      )
    ORDER BY t.id, COALESCE(ac.terminal_at, c.updated_at, ac.updated_at) DESC
) pulse
ORDER BY pulse.finished_at DESC
LIMIT 400
"""


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _payload(raw: Any) -> Any:
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None
    return raw


async def fetch_irrigation_pulses(*, zone_id: int) -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(IRRIGATION_PULSE_SQL, int(zone_id))
    pulses: list[dict[str, Any]] = []
    for row in rows:
        moment = row["finished_at"]
        if not isinstance(moment, datetime):
            continue
        payload = _payload(row["command_payload"])
        pulses.append(
            {
                "finished_at": _as_utc(moment),
                "config": row["config"],
                "command_payload": payload,
                "requested_duration_sec": row["requested_duration_sec"],
                "duration_sec": duration_sec_from_command(payload, row["requested_duration_sec"]),
                "liters": None,
            }
        )
    return pulses
