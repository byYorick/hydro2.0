"""Real PostgreSQL coverage of the irrigation decision read path (no devices)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from _test_support_runtime_plan import make_runtime_plan
from ae3lite.domain.services.irrigation_decision_controller import IrrigationDecisionController
from ae3lite.infrastructure.read_models import PgZoneRuntimeMonitor
from common.db import execute, fetch
from test_ae3lite_zone_runtime_monitor_integration import _cleanup, _insert_greenhouse, _insert_zone


async def sensor(gh, zone, *, label, unit='%', kind='SOIL_MOISTURE'):
    row = await fetch(
        """INSERT INTO sensors (greenhouse_id, zone_id, scope, type, label, unit, is_active, created_at, updated_at)
        VALUES ($1,$2,'inside',$3,$4,$5,true,NOW(),NOW()) RETURNING id""",
        gh,
        zone,
        kind,
        label,
        unit,
    )
    return int(row[0]['id'])


async def latest(sensor_id, now, *, quality='GOOD', value=30):
    await execute(
        """INSERT INTO telemetry_last (sensor_id,last_value,last_ts,last_quality,updated_at)
        VALUES ($1,$2,$3,$4,NOW())""",
        sensor_id,
        value,
        now,
        quality,
    )


@pytest.mark.asyncio
async def test_sql_filters_quality_future_and_stub_before_latest_sample_limit():
    prefix = 'irrig-audit-' + uuid4().hex[:10]
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    try:
        gh = await _insert_greenhouse(prefix)
        zone = await _insert_zone(prefix, greenhouse_id=gh)
        sid = await sensor(gh, zone, label='soil')
        await latest(sid, now, value=70)
        for offset, value, quality, metadata in [
            (-20, 70, 'GOOD', {}),
            (-1, 0, 'BAD', {}),
            (60, 0, 'GOOD', {}),
            (-2, 0, 'GOOD', {'stub': True}),
        ]:
            await execute(
                """INSERT INTO telemetry_samples (sensor_id,zone_id,ts,value,quality,metadata,created_at)
                VALUES ($1,$2,$3,$4,$5,$6::jsonb,NOW())""",
                sid,
                zone,
                now + timedelta(seconds=offset),
                value,
                quality,
                metadata,
            )
        monitor = PgZoneRuntimeMonitor()
        window = await monitor.read_metric_windows(
            zone_id=zone,
            sensor_type='SOIL_MOISTURE',
            since_ts=now - timedelta(minutes=30),
            until_ts=now,
            telemetry_max_age_sec=600,
            limit_per_sensor=1,
        )
        assert window['is_stale'] is False
        assert [point['value'] for point in window['sensor_windows'][0]['samples']] == [70]
        runtime = make_runtime_plan(
            irrigation_decision={'strategy': 'smart_soil_v1'}, soil_moisture_target={'min': 40, 'max': 50}
        )
        decision = await IrrigationDecisionController().evaluate(
            zone_id=zone, runtime_monitor=monitor, runtime=runtime, mode='normal', requested_duration_sec=120, now=now
        )
        assert decision.outcome == 'skip'
        assert decision.reason_code.endswith('above_max')
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_bad_current_sensor_and_missing_peer_cannot_authorize_from_old_dry_history():
    prefix = 'irrig-audit-' + uuid4().hex[:10]
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    try:
        gh = await _insert_greenhouse(prefix)
        zone = await _insert_zone(prefix, greenhouse_id=gh)
        sid = await sensor(gh, zone, label='dry-broken')
        await latest(sid, now, quality='BAD')
        await sensor(gh, zone, label='no-telemetry')
        await execute(
            """INSERT INTO telemetry_samples (sensor_id,zone_id,ts,value,quality,created_at)
            VALUES ($1,$2,$3,20,'GOOD',NOW())""",
            sid,
            zone,
            now,
        )
        monitor = PgZoneRuntimeMonitor()
        window = await monitor.read_metric_windows(
            zone_id=zone,
            sensor_type='SOIL_MOISTURE',
            since_ts=now - timedelta(minutes=30),
            until_ts=now,
            telemetry_max_age_sec=600,
        )
        assert window['is_stale'] is True
        assert len(window['sensor_windows']) == 2
        runtime = make_runtime_plan(
            irrigation_decision={'strategy': 'smart_soil_v1'}, soil_moisture_target={'min': 40, 'max': 50}
        )
        result = await IrrigationDecisionController().evaluate(
            zone_id=zone, runtime_monitor=monitor, runtime=runtime, mode='normal', requested_duration_sec=120, now=now
        )
        assert result.outcome == 'skip'
        assert result.reason_code == 'smart_soil_telemetry_missing_or_stale'
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_temperature_hold_reads_anchor_and_rejects_faulted_or_truncated_history():
    from ae3lite.domain.services.solution_temp_irrigation_guard import evaluate_solution_temp_hold

    prefix = 'irrig-temp-audit-' + uuid4().hex[:10]
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    try:
        gh = await _insert_greenhouse(prefix)
        zone = await _insert_zone(prefix, greenhouse_id=gh)
        sid = await sensor(gh, zone, label='solution_temp_c', kind='TEMPERATURE', unit='C')
        await latest(sid, now, value=33)
        for offset in (-610, -300, 0):
            await execute(
                """INSERT INTO telemetry_samples (sensor_id,zone_id,ts,value,quality,created_at)
                VALUES ($1,$2,$3,33,'GOOD',NOW())""",
                sid,
                zone,
                now + timedelta(seconds=offset),
            )
        monitor = PgZoneRuntimeMonitor()
        reading = await monitor.read_solution_temp_window(
            zone_id=zone, since_ts=now - timedelta(seconds=600), until_ts=now
        )
        assert reading['samples'][0]['ts'] == now - timedelta(seconds=610)
        result = evaluate_solution_temp_hold(min_c=18, max_c=24, hold_sec=600, stale_sec=600, now=now, reading=reading)
        assert result.reason_code == 'solution_temp_hot_stop'
        assert result.details['hold_covered'] is True
        limited = await monitor.read_solution_temp_window(
            zone_id=zone, since_ts=now - timedelta(seconds=600), until_ts=now, limit=1
        )
        assert limited['history_truncated'] is True
        result = evaluate_solution_temp_hold(min_c=18, max_c=24, hold_sec=600, stale_sec=600, now=now, reading=limited)
        assert result.blocks_irrigation is False
        await execute(
            """INSERT INTO telemetry_samples (sensor_id,zone_id,ts,value,quality,created_at)
            VALUES ($1,$2,$3,33,'BAD',NOW())""",
            sid,
            zone,
            now - timedelta(seconds=200),
        )
        reading = await monitor.read_solution_temp_window(
            zone_id=zone, since_ts=now - timedelta(seconds=600), until_ts=now
        )
        assert reading['invalid_samples'] == 1
        result = evaluate_solution_temp_hold(min_c=18, max_c=24, hold_sec=600, stale_sec=600, now=now, reading=reading)
        assert result.blocks_irrigation is False
        assert result.details['hold_covered'] is False
    finally:
        await _cleanup(prefix)
