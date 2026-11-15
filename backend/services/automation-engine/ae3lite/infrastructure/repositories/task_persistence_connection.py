"""PgAutomationTaskRepository connection: explicit collaborators and invocation context."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable

import asyncpg


@dataclass(frozen=True)
class TaskPersistenceConnectionPorts:
    global_get_pool: Callable[..., Any]


class TaskPersistenceConnection:
    def __init__(self, ports: TaskPersistenceConnectionPorts) -> None:
        self._ports = ports

    @asynccontextmanager
    async def connection(self, conn: asyncpg.Connection | None = None) -> AsyncIterator[asyncpg.Connection]:
        if conn is not None:
            yield conn
            return

        pool = await self._ports.global_get_pool()
        async with pool.acquire() as acquired_conn:
            yield acquired_conn

    async def fetchrow(
        self,
        query: str,
        *args: Any,
        conn: asyncpg.Connection | None = None,
    ) -> asyncpg.Record | None:
        async with self.connection(conn) as db_conn:
            return await db_conn.fetchrow(query, *args)

    async def fetch(
        self,
        query: str,
        *args: Any,
        conn: asyncpg.Connection | None = None,
    ) -> list[asyncpg.Record]:
        async with self.connection(conn) as db_conn:
            return await db_conn.fetch(query, *args)

    async def execute(
        self,
        query: str,
        *args: Any,
        conn: asyncpg.Connection | None = None,
    ) -> str:
        async with self.connection(conn) as db_conn:
            return await db_conn.execute(query, *args)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        """Open one repository-owned PostgreSQL transaction for multi-repository writes."""
        async with self.connection() as conn:
            async with conn.transaction():
                yield conn
