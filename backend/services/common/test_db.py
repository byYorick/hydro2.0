"""Test utilities for database operations."""
import asyncio
import asyncpg
from typing import Optional


_pool: Optional[asyncpg.pool.Pool] = None


async def get_test_pool() -> asyncpg.pool.Pool:
    """Get test database pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host="localhost",
            port=5432,
            database="hydro_test",
            user="hydro",
            password="hydro",
            min_size=1,
            max_size=5,
        )
    return _pool


async def execute_test(query: str, *args):
    """Execute test query."""
    pool = await get_test_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


async def fetch_test(query: str, *args):
    """Fetch test rows."""
    pool = await get_test_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def cleanup_test():
    """Cleanup test database."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
