"""Regression tests with the migrated PG16 schema; writes stay in temporary tables."""
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

import main
from common.db import get_pool


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("PG_DB") != "hydro_test", reason="requires migrated hydro_test")
async def test_production_rollups_and_retention(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    pool = await get_pool()
    async with pool.acquire() as connection, connection.transaction():
        # Copy columns, defaults and indexes, but no foreign keys to live devices.
        for table in ("sensors", "telemetry_samples", "aggregator_state",
                      "telemetry_agg_1m", "telemetry_agg_1h", "telemetry_daily"):
            await connection.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL) ON COMMIT DROP")
        # Production runs each query in its own transaction. Use savepoints so
        # PostgreSQL can run the fallback after an unavailable time_bucket().
        async def fetch(query, *args):
            async with connection.transaction():
                return await connection.fetch(query, *args)

        monkeypatch.setattr(main, "fetch", fetch)
        monkeypatch.setattr(main, "execute", connection.execute)
        monkeypatch.setattr(main, "record_simulation_event", AsyncMock())
        midnight = datetime(2025, 1, 2)
        monkeypatch.setattr(main, "utcnow_naive", lambda: midnight + timedelta(minutes=10))
        await connection.execute("""
            INSERT INTO aggregator_state (aggregation_type) VALUES ('1m'), ('1h'), ('daily');
            INSERT INTO sensors (id, greenhouse_id, type, label) VALUES (1, 1, 'PH', 'probe');
        """)
        insert = "INSERT INTO telemetry_samples (sensor_id, ts, value) VALUES (1, $1, $2)"
        await connection.execute(insert, midnight, 4)
        await connection.execute(insert, midnight + timedelta(seconds=30), 6)
        await main.run_aggregation()
        await main.run_aggregation()
        for table in ("telemetry_agg_1m", "telemetry_agg_1h", "telemetry_daily"):
            assert [tuple(row) for row in await connection.fetch(
                f"SELECT sample_count, value_avg FROM {table}"
            )] == [(2, 5)]

        # Data from the previous day arrives after the current day's cursor advanced.
        await connection.execute(insert, midnight - timedelta(minutes=1), 8)
        await main.run_aggregation()
        for table, bucket in (("telemetry_agg_1m", "ts"), ("telemetry_agg_1h", "ts"), ("telemetry_daily", "date")):
            rows = await connection.fetch(f"SELECT sample_count, value_avg FROM {table} ORDER BY {bucket}")
            assert [tuple(row) for row in rows] == [(1, 8), (2, 5)]

        await connection.execute(insert, midnight - timedelta(days=400), 4)
        result = await main.cleanup_old_data()
        assert result == {"samples_deleted": 1, "1m_deleted": 0, "1h_deleted": 0}
        assert await connection.fetchval("SELECT count(*) FROM telemetry_samples") == 3
