"""Repository for zone_prepare_baselines (water EC/pH capture)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

import asyncpg

from common.db import get_pool

logger = logging.getLogger(__name__)


class PgPrepareBaselineRepository:
    """Best-effort INSERT into zone_prepare_baselines when the table exists."""

    async def table_exists(self, *, conn: asyncpg.Connection | None = None) -> bool:
        query = """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'zone_prepare_baselines'
            ) AS exists
        """
        if conn is not None:
            row = await conn.fetchrow(query)
        else:
            pool = await get_pool()
            async with pool.acquire() as acquired:
                row = await acquired.fetchrow(query)
        return bool(row and row["exists"])

    async def insert_baseline(
        self,
        *,
        zone_id: int,
        water_ec: float,
        water_ph: float,
        target_ec: float,
        nutrient_budget: float,
        ratios: Mapping[str, Any],
        component_targets: Mapping[str, Any],
        ae_task_id: int | None = None,
        grow_cycle_id: int | None = None,
        source: str = "ae3",
        captured_at: datetime | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> Optional[int]:
        """Insert baseline row; return id or None if table missing / insert failed."""
        if not await self.table_exists(conn=conn):
            logger.info(
                "zone_prepare_baselines отсутствует — baseline только в corr_* zone_id=%s",
                zone_id,
            )
            return None

        ts = captured_at or datetime.now(timezone.utc).replace(tzinfo=None)
        ratios_json = json.dumps(dict(ratios), separators=(",", ":"), sort_keys=True, default=str)
        targets_json = json.dumps(
            dict(component_targets), separators=(",", ":"), sort_keys=True, default=str
        )
        # captured_at is timestamptz; created_at/updated_at are timestamp (Laravel).
        # Use distinct params so asyncpg does not hit AmbiguousParameterError.
        query = """
            INSERT INTO zone_prepare_baselines (
                zone_id, grow_cycle_id, ae_task_id,
                water_ec, water_ph, target_ec, nutrient_ec_budget,
                ratios_json, component_targets_json,
                captured_at, source, created_at, updated_at
            ) VALUES (
                $1, $2, $3,
                $4, $5, $6, $7,
                $8::jsonb, $9::jsonb,
                $10::timestamptz, $11, $12::timestamp, $13::timestamp
            )
            RETURNING id
        """
        args = (
            int(zone_id),
            grow_cycle_id,
            ae_task_id,
            float(water_ec),
            float(water_ph),
            float(target_ec),
            float(nutrient_budget),
            ratios_json,
            targets_json,
            ts,
            str(source or "ae3"),
            ts,
            ts,
        )
        try:
            if conn is not None:
                row = await conn.fetchrow(query, *args)
            else:
                pool = await get_pool()
                async with pool.acquire() as acquired:
                    row = await acquired.fetchrow(query, *args)
        except Exception:
            logger.warning(
                "Не удалось записать zone_prepare_baselines zone_id=%s",
                zone_id,
                exc_info=True,
            )
            return None
        return int(row["id"]) if row and row.get("id") is not None else None

    async def fetch_latest_baseline(
        self,
        *,
        zone_id: int,
        ae_task_id: int | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> Optional[dict[str, Any]]:
        """Return latest baseline row for zone (optionally scoped to ae_task_id)."""
        if not await self.table_exists(conn=conn):
            return None
        if ae_task_id is not None:
            query = """
                SELECT id, water_ec, water_ph, target_ec, nutrient_ec_budget,
                       ratios_json, component_targets_json, ae_task_id
                FROM zone_prepare_baselines
                WHERE zone_id = $1 AND ae_task_id = $2
                ORDER BY captured_at DESC
                LIMIT 1
            """
            args: tuple[Any, ...] = (int(zone_id), int(ae_task_id))
        else:
            query = """
                SELECT id, water_ec, water_ph, target_ec, nutrient_ec_budget,
                       ratios_json, component_targets_json, ae_task_id
                FROM zone_prepare_baselines
                WHERE zone_id = $1
                ORDER BY captured_at DESC
                LIMIT 1
            """
            args = (int(zone_id),)
        try:
            if conn is not None:
                row = await conn.fetchrow(query, *args)
            else:
                pool = await get_pool()
                async with pool.acquire() as acquired:
                    row = await acquired.fetchrow(query, *args)
        except Exception:
            logger.warning(
                "Не удалось прочитать zone_prepare_baselines zone_id=%s",
                zone_id,
                exc_info=True,
            )
            return None
        if row is None:
            return None
        return dict(row)
