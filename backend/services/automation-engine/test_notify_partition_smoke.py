from __future__ import annotations

import asyncio
import json
from datetime import datetime
from uuid import uuid4

import asyncpg
import pytest

from common.env import get_settings


def _dsn() -> str:
    settings = get_settings()
    return (
        f"postgresql://{settings.pg_user}:{settings.pg_pass}@"
        f"{settings.pg_host}:{settings.pg_port}/{settings.pg_db}"
    )


@pytest.mark.asyncio
async def test_notify_ae_command_status_smoke_on_new_partition():
    try:
        listener = await asyncpg.connect(dsn=_dsn())
        writer = await asyncpg.connect(dsn=_dsn())
    except Exception as exc:
        pytest.skip(f"postgres not available for notify smoke: {exc}")
        return

    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=8)
    channel = "ae_command_status"
    partition_name = "commands_partitioned_test_2099_01"
    created_at = datetime(2099, 1, 15, 10, 0, 0)
    cmd_id = f"notify-smoke-{uuid4()}"

    def _cb(_conn, _pid: int, _channel: str, payload: str) -> None:
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass

    try:
        commands_rel = await writer.fetchval("SELECT to_regclass('public.commands')")
        if not commands_rel:
            pytest.skip("commands table is not available in current test database")

        is_partitioned = await writer.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_partitioned_table pt
                JOIN pg_class c ON c.oid = pt.partrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname = 'commands'
            )
            """
        )
        if not bool(is_partitioned):
            pytest.skip("commands table is not partitioned in current test database")

        await listener.add_listener(channel, _cb)
        await writer.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {partition_name}
            PARTITION OF commands
            FOR VALUES FROM ('2099-01-01 00:00:00') TO ('2099-02-01 00:00:00')
            """
        )
        await writer.execute(
            """
            INSERT INTO commands (cmd, cmd_id, params, status, created_at, updated_at)
            VALUES ($1, $2, $3::jsonb, $4, $5, $5)
            """,
            "set_relay",
            cmd_id,
            "{}",
            "DONE",
            created_at,
        )

        raw_payload = await asyncio.wait_for(queue.get(), timeout=5.0)
        payload = json.loads(raw_payload)
        assert payload["cmd_id"] == cmd_id
        assert payload["status"] == "DONE"
    finally:
        try:
            await writer.execute("DELETE FROM commands WHERE cmd_id = $1", cmd_id)
        except Exception:
            pass
        try:
            await writer.execute(f"DROP TABLE IF EXISTS {partition_name}")
        except Exception:
            pass
        try:
            await listener.remove_listener(channel, _cb)
        except Exception:
            pass
        await listener.close()
        await writer.close()
