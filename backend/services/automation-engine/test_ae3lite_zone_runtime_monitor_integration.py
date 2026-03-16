from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from ae3lite.infrastructure.read_models import PgZoneRuntimeMonitor
from common.db import execute, fetch


async def _insert_greenhouse(prefix: str) -> int:
    rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        f"gh-{uuid4().hex[:20]}",
        f"{prefix}-gh",
        f"pt-{uuid4().hex[:20]}",
    )
    return int(rows[0]["id"])


async def _insert_zone(prefix: str, *, greenhouse_id: int) -> int:
    rows = await fetch(
        """
        INSERT INTO zones (greenhouse_id, name, uid, status, automation_runtime, created_at, updated_at)
        VALUES ($1, $2, $3, 'online', 'ae3', NOW(), NOW())
        RETURNING id
        """,
        greenhouse_id,
        prefix,
        f"zn-{uuid4().hex[:20]}",
    )
    return int(rows[0]["id"])


async def _cleanup(prefix: str) -> None:
    await execute("DELETE FROM zones WHERE name LIKE $1", f"{prefix}%")
    await execute("DELETE FROM greenhouses WHERE name LIKE $1", f"{prefix}%")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_read_latest_irr_state_filters_by_expected_cmd_id() -> None:
    prefix = f"ae3-irr-monitor-{uuid4().hex[:8]}"
    monitor = PgZoneRuntimeMonitor()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)

        await execute(
            """
            INSERT INTO zone_events (zone_id, type, payload_json, details, created_at)
            VALUES
                (
                    $1,
                    'IRR_STATE_SNAPSHOT',
                    '{"cmd_id":"older-probe","snapshot":{"pump_main":false}}'::jsonb,
                    '{"cmd_id":"older-probe","snapshot":{"pump_main":false}}'::jsonb,
                    NOW() - INTERVAL '2 seconds'
                ),
                (
                    $1,
                    'IRR_STATE_SNAPSHOT',
                    '{"cmd_id":"probe-cmd-77","snapshot":{"pump_main":true}}'::jsonb,
                    '{"cmd_id":"probe-cmd-77","snapshot":{"pump_main":true}}'::jsonb,
                    NOW()
                )
            """,
            zone_id,
        )

        older = await monitor.read_latest_irr_state(
            zone_id=zone_id,
            max_age_sec=60,
            expected_cmd_id="older-probe",
        )
        assert older["has_snapshot"] is True
        assert older["cmd_id"] == "older-probe"
        assert older["snapshot"]["pump_main"] is False

        current = await monitor.read_latest_irr_state(
            zone_id=zone_id,
            max_age_sec=60,
            expected_cmd_id="probe-cmd-77",
        )
        assert current["has_snapshot"] is True
        assert current["cmd_id"] == "probe-cmd-77"
        assert current["snapshot"]["pump_main"] is True
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_read_metric_window_returns_recent_samples_for_sensor() -> None:
    prefix = f"ae3-metric-window-{uuid4().hex[:8]}"
    monitor = PgZoneRuntimeMonitor()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)

        sensor_rows = await fetch(
            """
            INSERT INTO sensors (
                greenhouse_id, zone_id, scope, type, label, unit, is_active, created_at, updated_at
            )
            VALUES ($1, $2, 'inside', 'EC', 'ec', 'mS/cm', TRUE, NOW(), NOW())
            RETURNING id
            """,
            greenhouse_id,
            zone_id,
        )
        sensor_id = int(sensor_rows[0]["id"])

        await execute(
            """
            INSERT INTO telemetry_samples (sensor_id, ts, zone_id, value, quality, created_at)
            VALUES
                ($1, NOW() - INTERVAL '6 seconds', $2, 1.10, 'GOOD', NOW()),
                ($1, NOW() - INTERVAL '4 seconds', $2, 1.25, 'GOOD', NOW()),
                ($1, NOW() - INTERVAL '2 seconds', $2, 1.40, 'GOOD', NOW())
            """,
            sensor_id,
            zone_id,
        )
        await execute(
            """
            INSERT INTO telemetry_last (sensor_id, last_value, last_ts, last_quality, updated_at)
            VALUES ($1, 1.40, NOW() - INTERVAL '2 seconds', 'GOOD', NOW())
            ON CONFLICT (sensor_id)
            DO UPDATE SET
                last_value = EXCLUDED.last_value,
                last_ts = EXCLUDED.last_ts,
                last_quality = EXCLUDED.last_quality,
                updated_at = EXCLUDED.updated_at
            """,
            sensor_id,
        )

        result = await monitor.read_metric_window(
            zone_id=zone_id,
            sensor_type="EC",
            since_ts=datetime.utcnow() - timedelta(seconds=5),
            telemetry_max_age_sec=10,
        )

        assert result["has_sensor"] is True
        assert result["has_samples"] is True
        assert result["is_stale"] is False
        assert len(result["samples"]) == 2
        assert [round(sample["value"], 2) for sample in result["samples"]] == [1.25, 1.40]
    finally:
        await _cleanup(prefix)
