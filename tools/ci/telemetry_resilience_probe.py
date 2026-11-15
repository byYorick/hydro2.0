"""Measure the real MQTT -> Redis -> PostgreSQL path in an isolated test stack.

Run inside the Python service test image. Requires a Laravel-created fixture
JSON with zone_id/zone_uid/node_id/node_uid/greenhouse_uid and no real devices.
The external controller may restart dependencies while this probe publishes.
No schema changes, credentials in reports, or device commands are issued.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import threading
import time

import asyncpg
import httpx
import paho.mqtt.client as mqtt
import redis.asyncio as redis


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * fraction) - 1)], 3)


async def run(args: argparse.Namespace) -> None:
    if os.environ.get('HYDRO_RESILIENCE_TEST') != '1':
        raise RuntimeError('Explicit HYDRO_RESILIENCE_TEST=1 is required')
    database = os.environ.get('PG_DB', '')
    if database != 'hydro_test' and not database.startswith('hydro_resilience_test'):
        raise RuntimeError('A dedicated resilience test database is required')
    fixtures = json.loads(args.fixtures.read_text())
    if not fixtures or any(
        not row['node_uid'].startswith('nd-resilience-')
        or not row['zone_uid'].startswith('zn-resilience-')
        or row['greenhouse_uid'] != 'gh-resilience'
        for row in fixtures
    ):
        raise RuntimeError('Only the synthetic resilience fixture is accepted')
    zone_ids = [int(row['zone_id']) for row in fixtures]
    # Wait for the consumer before the first publish. Broker PUBACK cannot
    # preserve messages published before a persistent subscription exists.
    async with httpx.AsyncClient(timeout=4, trust_env=False) as http:
        deadline = time.monotonic() + 45
        while True:
            try:
                response = await http.get(args.hl_url.rstrip('/') + '/health/ready')
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError('HL did not become ready before the test')
            await asyncio.sleep(1)
    await asyncio.sleep(0.5)
    connection_options = dict(
        host=os.environ.get('PG_HOST', 'db'),
        database=database,
        user=os.environ['PG_USER'],
        password=os.environ['PG_PASS'],
        port=int(os.environ.get('PG_PORT', '5432')),
        timeout=3,
        command_timeout=3,
    )
    connection = await asyncpg.connect(**connection_options)
    for row in fixtures:
        valid = await connection.fetchval(
            '''SELECT EXISTS (
            SELECT 1 FROM nodes n JOIN zones z ON z.id=n.zone_id
            JOIN greenhouses g ON g.id=z.greenhouse_id
            WHERE n.id=$1 AND n.uid=$2 AND z.id=$3 AND z.uid=$4 AND g.uid=$5)''',
            row['node_id'],
            row['node_uid'],
            row['zone_id'],
            row['zone_uid'],
            row['greenhouse_uid'],
        )
        if not valid:
            raise RuntimeError('Fixture does not match the target test database')
    if await connection.fetchval('SELECT EXISTS (SELECT 1 FROM ae_tasks WHERE zone_id=ANY($1::bigint[]))', zone_ids):
        raise RuntimeError('Fixture must have no automation tasks')
    start_seq = (
        int(
            await connection.fetchval(
                '''SELECT COALESCE(MAX((metadata->'raw'->>'raw')::bigint),0)
        FROM telemetry_samples WHERE zone_id=ANY($1::bigint[])''',
                zone_ids,
            )
        )
        + 1
    )
    await connection.close()
    connection = None

    redis_client = redis.Redis(
        host=os.environ.get('REDIS_HOST', 'redis'),
        port=int(os.environ.get('REDIS_PORT', '6379')),
        password=os.environ.get('REDIS_PASSWORD') or None,
        socket_timeout=3,
        socket_connect_timeout=3,
    )
    connected = threading.Event()
    ack_lock = threading.Lock()
    acknowledged = 0

    def on_publish(_client, _userdata, _mid):
        nonlocal acknowledged
        with ack_lock:
            acknowledged += 1

    client = mqtt.Client(client_id='hydro-resilience-probe', clean_session=True)
    if os.environ.get('MQTT_USER'):
        client.username_pw_set(os.environ['MQTT_USER'], os.environ.get('MQTT_PASS'))
    client.on_connect = lambda *_: connected.set()
    client.on_publish = on_publish
    client.connect(os.environ.get('MQTT_HOST', 'mqtt'), int(os.environ.get('MQTT_PORT', '1883')))
    client.loop_start()
    if not await asyncio.to_thread(connected.wait, 10):
        raise RuntimeError('Test MQTT connection failed')

    sent: dict[int, float] = {}
    observed: set[int] = set()
    latencies: list[float] = []
    history = []
    start = time.monotonic()
    published_done = False
    report = {
        'scope': 'synthetic telemetry integration, no hardware',
        'rate': args.rate,
        'duration_seconds': args.duration,
        'start_seq': start_seq,
    }

    async def publish() -> None:
        nonlocal published_done
        for index in range(round(args.duration * args.rate)):
            delay = start + index / args.rate - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            fixture = fixtures[(index // args.channels) % len(fixtures)]
            channel = 'ph_' + str(index % args.channels)
            seq = start_seq + index
            payload = dict(metric_type='ph', value=6 + (seq % 10000) / 100000, ts=time.time(), channel=channel, raw=seq)
            topic = '/'.join(
                ['hydro', fixture['greenhouse_uid'], fixture['zone_uid'], fixture['node_uid'], channel, 'telemetry']
            )
            sent[seq] = time.monotonic()
            info = client.publish(topic, json.dumps(payload), qos=1)
            if info.rc not in (mqtt.MQTT_ERR_SUCCESS, mqtt.MQTT_ERR_NO_CONN):
                raise RuntimeError('MQTT publish rejected by the client')
        # Publisher PUBACK proves broker acceptance, not database persistence.
        # An offline-queued QoS1 MessageInfo retains rc=NO_CONN even after Paho
        # reconnects; wait_for_publish() raises for that rc. Observe actual ACKs.
        deadline = time.monotonic() + args.recovery_timeout
        while True:
            with ack_lock:
                complete = acknowledged == len(sent)
            if complete:
                break
            if time.monotonic() > deadline:
                raise RuntimeError('MQTT publisher PUBACK timeout')
            await asyncio.sleep(0.1)
        published_done = True

    try:
        publisher = asyncio.create_task(publish())
        async with httpx.AsyncClient(timeout=4, trust_env=False) as http:
            while True:
                point = {'elapsed': round(time.monotonic() - start, 3), 'sent': len(sent)}
                try:
                    if connection is None or connection.is_closed():
                        connection = await asyncpg.connect(**connection_options)
                    rows = await connection.fetch(
                        '''SELECT (metadata->'raw'->>'raw')::bigint AS seq
                        FROM telemetry_samples WHERE zone_id=ANY($1::bigint[])
                        AND (metadata->'raw'->>'raw')::bigint >= $2
                        AND (metadata->'raw'->>'raw')::bigint < $3''',
                        zone_ids,
                        start_seq,
                        start_seq + round(args.duration * args.rate),
                    )
                    ids = {int(row['seq']) for row in rows}
                    now = time.monotonic()
                    for seq in ids - observed:
                        if seq in sent:
                            latencies.append((now - sent[seq]) * 1000)
                    observed.update(ids)
                    point.update(rows=len(rows), unique=len(ids), duplicates=len(rows) - len(ids))
                except (asyncpg.PostgresError, OSError, asyncio.TimeoutError):
                    if connection is not None:
                        connection.terminate()
                    connection = None
                    point['db'] = 'unavailable'
                try:
                    point.update(
                        zip(
                            ['queued', 'processing', 'dead'],
                            await asyncio.gather(
                                *[
                                    redis_client.llen('hydro:telemetry:' + key)
                                    for key in ['queue', 'processing', 'dead']
                                ]
                            ),
                        )
                    )
                    memory = await redis_client.info('memory')
                    stats = await redis_client.info('stats')
                    point.update(redis_used_bytes=memory['used_memory'], evicted_keys=stats['evicted_keys'])
                except redis.RedisError:
                    point['redis'] = 'unavailable'
                try:
                    response = await http.get(args.hl_url.rstrip('/') + '/health/ready')
                    point['ready_status'] = response.status_code
                except httpx.HTTPError:
                    point['ready_status'] = 'unreachable'
                history.append(point)
                report.update(
                    sent=len(sent),
                    observed_unique=len(observed),
                    latest=point,
                    latency_observation_ms={
                        'p50': percentile(latencies, 0.50),
                        'p95': percentile(latencies, 0.95),
                        'p99': percentile(latencies, 0.99),
                    },
                    history=history,
                )
                temp = args.output.with_suffix('.tmp')
                temp.write_text(json.dumps(report, indent=2))
                temp.replace(args.output)
                if publisher.done():
                    await publisher
                if published_done and len(observed) == len(sent):
                    if point.get('queued') == 0 and point.get('processing') == 0:
                        break
                if time.monotonic() - start > args.duration + args.recovery_timeout:
                    raise RuntimeError('Not all published samples reached PostgreSQL before deadline')
                await asyncio.sleep(1)
        assert connection is not None
        mismatches = await connection.fetchval(
            '''SELECT count(*) FROM telemetry_last l
            JOIN sensors s ON s.id=l.sensor_id WHERE s.zone_id=ANY($1::bigint[])
            AND l.last_ts IS DISTINCT FROM
              (SELECT max(t.ts) FROM telemetry_samples t WHERE t.sensor_id=s.id)''',
            zone_ids,
        )
        if mismatches or history[-1].get('dead', 0) or history[-1].get('evicted_keys', 0):
            raise RuntimeError('Projection, DLQ or eviction invariant failed')
        report.update(
            success=True,
            elapsed_seconds=round(time.monotonic() - start, 3),
            publisher_pubacks=acknowledged,
            projection_mismatches=mismatches,
            duplicate_rows=history[-1].get('duplicates', 0),
        )
        args.output.write_text(json.dumps(report, indent=2))
        print(json.dumps({key: value for key, value in report.items() if key != 'history'}))
    finally:
        if not publisher.done():
            publisher.cancel()
            await asyncio.gather(publisher, return_exceptions=True)
        client.disconnect()
        await asyncio.to_thread(client.loop_stop)
        await redis_client.aclose()
        if connection is not None:
            await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rate', type=float, default=40)
    parser.add_argument('--duration', type=float, default=300)
    parser.add_argument('--channels', type=int, default=10)
    parser.add_argument('--recovery-timeout', type=float, default=120)
    parser.add_argument('--hl-url', default='http://history-logger:9300')
    args = parser.parse_args()
    if min(args.rate, args.duration, args.channels, args.recovery_timeout) <= 0:
        parser.error('Rate, duration, channels and recovery timeout must be positive')
    if not all(math.isfinite(value) for value in (args.rate, args.duration, args.recovery_timeout)):
        parser.error('Load parameters must be finite')
    if args.output.exists():
        parser.error('Use a new output path; existing evidence is never overwritten')
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
