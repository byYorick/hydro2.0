"""PostgreSQL repository for AE3-Lite correction-config apply acknowledgements."""

from __future__ import annotations

from datetime import datetime, timezone

from common.db import execute

_SQL_MARK_APPLIED = """
    UPDATE zone_correction_configs
    SET
        last_applied_at = $3,
        last_applied_version = $2,
        updated_at = GREATEST(updated_at, $4)
    WHERE zone_id = $1
      AND version = $2
      AND (last_applied_version IS DISTINCT FROM $2 OR last_applied_at IS NULL)
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
        await execute(
            _SQL_MARK_APPLIED,
            int(zone_id),
            int(version),
            self._normalize_applied_at(now),
            self._normalize_updated_at(now),
        )
