import asyncio
import json
from typing import Any, Optional, Dict

import asyncpg

from .env import get_settings


_pool: Optional[asyncpg.pool.Pool] = None


async def get_pool() -> asyncpg.pool.Pool:
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = await asyncpg.create_pool(
            host=s.pg_host,
            port=s.pg_port,
            database=s.pg_db,
            user=s.pg_user,
            password=s.pg_pass,
            min_size=1,
            max_size=10,
        )
    return _pool


async def execute(query: str, *args: Any) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


async def fetch(query: str, *args: Any):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def upsert_telemetry_last(zone_id: int, metric_type: str, node_id: Optional[int], channel: Optional[str], value: Optional[float]):
    await execute(
        """
        INSERT INTO telemetry_last (zone_id, metric_type, node_id, channel, value, updated_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
        ON CONFLICT (zone_id, metric_type)
        DO UPDATE SET node_id = EXCLUDED.node_id, channel = EXCLUDED.channel, value = EXCLUDED.value, updated_at = NOW()
        """,
        zone_id, metric_type, node_id, channel, value
    )


async def create_zone_event(zone_id: int, event_type: str, details: Optional[Dict[str, Any]] = None):
    """Create a zone event according to DATA_MODEL_REFERENCE.md section 8.1."""
    details_json = json.dumps(details) if details else None
    await execute(
        """
        INSERT INTO zone_events (zone_id, type, details, created_at)
        VALUES ($1, $2, $3, NOW())
        """,
        zone_id, event_type, details_json
    )


async def create_ai_log(zone_id: Optional[int], action: str, details: Optional[Dict[str, Any]] = None):
    """Create an AI log entry."""
    details_json = json.dumps(details) if details else None
    await execute(
        """
        INSERT INTO ai_logs (zone_id, action, details, created_at)
        VALUES ($1, $2, $3, NOW())
        """,
        zone_id, action, details_json
    )


async def create_scheduler_log(task_name: str, status: str, details: Optional[Dict[str, Any]] = None):
    """Create a scheduler log entry."""
    details_json = json.dumps(details) if details else None
    await execute(
        """
        INSERT INTO scheduler_logs (task_name, status, details, created_at)
        VALUES ($1, $2, $3, NOW())
        """,
        task_name, status, details_json
    )


