import asyncio
from typing import Any, Optional

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


