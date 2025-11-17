import asyncio
import json
from typing import Optional
from time import time as now_ts

from common.db import execute, upsert_telemetry_last
from common.mqtt import MqttClient
from common.commands import mark_command_ack, mark_command_failed, mark_timeouts
from common.env import get_settings
from prometheus_client import Counter, Histogram, start_http_server

TELEM_RECEIVED = Counter("telemetry_received_total", "Telemetry messages received")
TELEM_INSERTED = Counter("telemetry_inserted_total", "Telemetry rows inserted")
TELEM_LAT = Histogram("telemetry_flush_seconds", "Telemetry batch flush duration seconds")


def _parse_json(payload: bytes):
    try:
        return json.loads(payload.decode("utf-8"))
    except Exception:
        return None


async def handle_telemetry(topic: str, payload: bytes):
    s = get_settings()
    if not hasattr(handle_telemetry, "_buf"):
        handle_telemetry._buf = []  # type: ignore
        handle_telemetry._last_flush = 0.0  # type: ignore
    buf = handle_telemetry._buf  # type: ignore
    last_flush = handle_telemetry._last_flush  # type: ignore
    data = _parse_json(payload)
    if not data:
        return
    TELEM_RECEIVED.inc()
    zone_id = _extract_zone_id(topic)  # expects zn-{id}
    node_uid = _extract_node_uid(topic)
    node_id = None
    # if payload carries numeric node id in "node_id" like "nd-ph-1" we keep behavior
    try:
        node_id = int(str(data.get("node_id", "")).split("-")[-1])
    except Exception:
        pass
    channel = data.get("channel")
    metric_type = data.get("metric_type")
    value = data.get("value")
    ts = data.get("timestamp")
    # buffer row
    buf.append((zone_id, node_id, channel, metric_type, value, json.dumps(data), ts))
    # flush conditions
    should_flush = len(buf) >= s.telemetry_batch_size or (now_ts() - last_flush) * 1000 >= s.telemetry_flush_ms
    if should_flush:
        start = now_ts()
        rows = list(buf)
        buf.clear()
        for z, n, ch, mt, val, raw, tsv in rows:
            if tsv is not None:
                await execute(
                    """
                    INSERT INTO telemetry_samples (zone_id, node_id, channel, metric_type, value, raw, ts, created_at)
                    VALUES ($1,$2,$3,$4,$5,$6, to_timestamp($7), NOW())
                    """,
                    z, n, ch, mt, val, raw, tsv,
                )
            else:
                await execute(
                    """
                    INSERT INTO telemetry_samples (zone_id, node_id, channel, metric_type, value, raw, ts, created_at)
                    VALUES ($1,$2,$3,$4,$5,$6, NOW(), NOW())
                    """,
                    z, n, ch, mt, val, raw,
                )
        TELEM_INSERTED.inc(len(rows))
        TELEM_LAT.observe(now_ts() - start)
        handle_telemetry._last_flush = now_ts()  # type: ignore
    # upsert last
    await upsert_telemetry_last(zone_id, metric_type, node_id, channel, value)


async def handle_command_response(topic: str, payload: bytes):
    data = _parse_json(payload)
    if not data:
        return
    cmd_id = data.get("cmd_id")
    status = data.get("status")
    if not cmd_id or not status:
        return
    if status == "ACK":
        await mark_command_ack(cmd_id)
    elif status in ("ERROR", "TIMEOUT"):
        await mark_command_failed(cmd_id)


async def handle_status(topic: str, payload: bytes):
    # hydro/{gh}/{zone}/{node}/status  payload: {"status":"ONLINE","ts":...}
    data = _parse_json(payload)
    node_uid = _extract_node_uid(topic)
    if not node_uid:
        return
    await execute(
        "UPDATE nodes SET status=$1, last_seen_at=NOW(), updated_at=NOW() WHERE uid=$2",
        (data or {}).get("status", "online").lower(), node_uid,
    )


async def handle_lwt(topic: str, payload: bytes):
    # hydro/{gh}/{zone}/{node}/lwt payload: "offline"
    node_uid = _extract_node_uid(topic)
    if not node_uid:
        return
    zone_id = _extract_zone_id(topic)
    await execute(
        "UPDATE nodes SET status='offline', updated_at=NOW() WHERE uid=$1",
        node_uid,
    )
    # create alert for OFFLINE
    if zone_id:
        await execute(
            """
            INSERT INTO alerts (zone_id, type, details, status, created_at)
            VALUES ($1, $2, $3, 'ACTIVE', NOW())
            """,
            zone_id, 'node_offline', json.dumps({'node_uid': node_uid}),
        )


async def handle_config_response(topic: str, payload: bytes):
    # hydro/{gh}/{zone}/{node}/config_response
    data = _parse_json(payload)
    if not data:
        return
    status = (data.get("status") or "").upper()
    if status == "ERROR":
        zone_id = _extract_zone_id(topic)
        node_uid = _extract_node_uid(topic)
        if zone_id:
            await execute(
                """
                INSERT INTO alerts (zone_id, type, details, status, created_at)
                VALUES ($1, $2, $3, 'ACTIVE', NOW())
                """,
                zone_id, 'config_error', json.dumps({'node_uid': node_uid, 'error': data.get('error'), 'version': data.get('version'), 'hash': data.get('hash')}),
            )


def _extract_zone_id(topic: str) -> Optional[int]:
    # hydro/{gh}/{zone}/{node}/{channel}/telemetry
    parts = topic.split("/")
    if len(parts) >= 3:
        zone_part = parts[2]
        if zone_part.startswith("zn-"):
            try:
                return int(zone_part[3:])
            except Exception:
                return None
    return None


def _extract_node_uid(topic: str) -> Optional[str]:
    parts = topic.split("/")
    if len(parts) >= 4:
        return parts[3]
    return None


async def main():
    loop = asyncio.get_running_loop()
    mqtt = MqttClient(client_id_suffix="-logger")
    mqtt.start()
    start_http_server(9301)

    def telemetry_cb(topic: str, payload: bytes):
        asyncio.run_coroutine_threadsafe(handle_telemetry(topic, payload), loop)

    def cmd_resp_cb(topic: str, payload: bytes):
        asyncio.run_coroutine_threadsafe(handle_command_response(topic, payload), loop)

    def status_cb(topic: str, payload: bytes):
        asyncio.run_coroutine_threadsafe(handle_status(topic, payload), loop)

    def lwt_cb(topic: str, payload: bytes):
        asyncio.run_coroutine_threadsafe(handle_lwt(topic, payload), loop)

    mqtt.subscribe("hydro/+/+/+/+/telemetry", telemetry_cb, qos=1)
    mqtt.subscribe("hydro/+/+/+/+/command_response", cmd_resp_cb, qos=1)
    mqtt.subscribe("hydro/+/+/+/status", status_cb, qos=1)
    mqtt.subscribe("hydro/+/+/+/lwt", lwt_cb, qos=1)
    mqtt.subscribe("hydro/+/+/+/config_response", lambda t, p: asyncio.run_coroutine_threadsafe(handle_config_response(t, p), loop), qos=1)

    # keep alive and timeout loop
    while True:
        await mark_timeouts(30)
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())


