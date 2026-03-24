"""PostgreSQL repository for AE3-Lite correction-config apply acknowledgements."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from common.db import execute

_logger = logging.getLogger(__name__)

_SQL_MARK_APPLIED = """
    UPDATE automation_config_documents
    SET
        payload = jsonb_set(
            jsonb_set(
                COALESCE(payload, '{}'::jsonb),
                '{last_applied_at}',
                to_jsonb($3::text),
                true
            ),
            '{last_applied_version}',
            to_jsonb($2),
            true
        ),
        updated_at = GREATEST(updated_at, $4)
    WHERE namespace = 'zone.correction'
      AND scope_type = 'zone'
      AND scope_id = $1
"""


class PgZoneCorrectionConfigRepository:
    """Stores the last correction-config version actually accepted by AE."""

    def _normalize_applied_at(self, value: datetime) -> datetime:
        normalized = value.astimezone(timezone.utc) if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return normalized.replace(microsecond=0)

    def _normalize_updated_at(self, value: datetime) -> datetime:
        normalized = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo is not None else value
        return normalized.replace(microsecond=0)

    async def mark_applied(self, *, zone_id: int, version: int, now: datetime) -> None:
        tag = await execute(
            _SQL_MARK_APPLIED,
            int(zone_id),
            int(version),
            self._normalize_applied_at(now),
            self._normalize_updated_at(now),
        )
        if tag == "UPDATE 0":
            _logger.debug(
                "mark_applied: no rows updated (zone_id=%d, version=%d) "
                "— already applied or version mismatch",
                zone_id, version,
            )
