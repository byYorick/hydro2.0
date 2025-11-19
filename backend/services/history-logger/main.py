import asyncio
import json
import logging
from typing import Optional, List
from datetime import datetime
from time import time as now_ts

import httpx

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from common.db import execute, upsert_telemetry_last, create_zone_event, fetch
from common.mqtt import MqttClient
from common.commands import mark_command_ack, mark_command_failed, mark_timeouts
from common.env import get_settings
from common.telemetry import TelemetrySampleModel, process_telemetry_batch
from common.alerts import create_alert, AlertSource, AlertCode
from prometheus_client import Counter, Histogram, start_http_server

logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="History Logger")

TELEM_RECEIVED = Counter("telemetry_received_total", "Telemetry messages received")
TELEM_INSERTED = Counter("telemetry_inserted_total", "Telemetry rows inserted")
TELEM_LAT = Histogram("telemetry_flush_seconds", "Telemetry batch flush duration seconds")
HEARTBEAT_RECEIVED = Counter("heartbeat_received_total", "Heartbeat messages received", ["node_uid"])


def _parse_json(payload: bytes):
    try:
        return json.loads(payload.decode("utf-8"))
    except Exception:
        return None


async def handle_telemetry(topic: str, payload: bytes):
    """
    Обработчик телеметрии из MQTT.
    Использует общий процессор process_telemetry_batch.
    """
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
    
    # Извлекаем данные из топика и payload
    zone_uid = _extract_zone_uid(topic)  # expects zn-{id}
    node_uid = _extract_node_uid(topic)
    
    # Создаём модель для process_telemetry_batch
    ts = None
    if data.get("timestamp"):
        try:
            # Если timestamp в миллисекундах
            ts_value = data.get("timestamp")
            if isinstance(ts_value, (int, float)):
                ts = datetime.fromtimestamp(ts_value / 1000.0)
            elif isinstance(ts_value, str):
                ts = datetime.fromisoformat(ts_value.replace('Z', '+00:00'))
        except Exception:
            pass
    
    sample = TelemetrySampleModel(
        node_uid=node_uid or "",
        zone_uid=zone_uid,
        metric_type=data.get("metric_type") or data.get("metric", ""),
        value=data.get("value", 0.0),
        ts=ts,
        raw=data,
        channel=data.get("channel")
    )
    
    # Буферизуем
    buf.append(sample)
    
    # Flush conditions
    should_flush = len(buf) >= s.telemetry_batch_size or (now_ts() - last_flush) * 1000 >= s.telemetry_flush_ms
    if should_flush:
        start = now_ts()
        rows = list(buf)
        buf.clear()
        await process_telemetry_batch(rows)
        TELEM_INSERTED.inc(len(rows))
        TELEM_LAT.observe(now_ts() - start)
        handle_telemetry._last_flush = now_ts()  # type: ignore


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
        
        # Обработка overcurrent из command_response
        error_code = data.get("error_code")
        if error_code == "overcurrent":
            # Получаем информацию о команде
            cmd_rows = await fetch(
                """
                SELECT zone_id, cmd, params
                FROM commands
                WHERE id = $1
                """,
                cmd_id,
            )
            
            if cmd_rows:
                zone_id = cmd_rows[0].get("zone_id")
                details = data.get("details", {})
                
                if zone_id:
                    # Создаём alert для overcurrent
                    await create_alert(
                        zone_id=zone_id,
                        source=AlertSource.BIZ.value,
                        code=AlertCode.BIZ_OVERCURRENT.value,
                        type='Overcurrent on pump channel',
                        details={
                            "cmd_id": cmd_id,
                            "cmd": cmd_rows[0].get("cmd"),
                            "params": cmd_rows[0].get("params"),
                            **details
                        }
                    )


async def handle_status(topic: str, payload: bytes):
    # hydro/{gh}/{zone}/{node}/status  payload: {"status":"ONLINE","ts":...}
    data = _parse_json(payload)
    node_uid = _extract_node_uid(topic)
    if not node_uid:
        return
    new_status = (data or {}).get("status", "online").lower()
    
    # Получаем старый статус для определения перехода
    rows = await fetch(
        "SELECT status, zone_id FROM nodes WHERE uid=$1",
        node_uid,
    )
    
    old_status = None
    zone_id = None
    if rows:
        old_status = rows[0]["status"]
        zone_id = rows[0]["zone_id"]
    
    await execute(
        "UPDATE nodes SET status=$1, last_seen_at=NOW(), updated_at=NOW() WHERE uid=$2",
        new_status, node_uid,
    )
    
    # Создаем событие при переходе в ONLINE
    if zone_id and new_status == "online" and old_status != "online":
        await create_zone_event(
            zone_id,
            'DEVICE_ONLINE',
            {'node_uid': node_uid}
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
        await create_alert(
            zone_id=zone_id,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NODE_OFFLINE.value,
            type='Node offline',
            details={'node_uid': node_uid}
        )
        # Create zone events for NODE_OFFLINE
        await create_zone_event(
            zone_id,
            'DEVICE_OFFLINE',
            {'node_uid': node_uid}
        )
        # Also create NODE_OFFLINE for compatibility
        await create_zone_event(
            zone_id,
            'NODE_OFFLINE',
            {'node_uid': node_uid}
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
            await create_alert(
                zone_id=zone_id,
                source=AlertSource.BIZ.value,
                code=AlertCode.BIZ_CONFIG_ERROR.value,
                type='Config error',
                details={
                    'node_uid': node_uid,
                    'error': data.get('error'),
                    'version': data.get('version'),
                    'hash': data.get('hash')
                }
            )


async def handle_node_hello(topic: str, payload: bytes):
    """
    Обработчик сообщения node_hello от узла при первом подключении.
    
    Топики:
    - hydro/node_hello (для начальной регистрации, когда узел не знает gh/zone/node)
    - hydro/{gh}/{zone}/{node}/node_hello (если узел уже знает свои параметры)
    
    Payload:
    {
        "message_type": "node_hello",
        "hardware_id": "esp32-ABCD1234",
        "node_type": "ph",
        "fw_version": "2.0.1",
        "capabilities": ["ph", "temperature"],
        "provisioning_meta": {
            "greenhouse_token": "gh-123",
            "zone_id": null,
            "node_name": null
        }
    }
    """
    logger.info(f"handle_node_hello called: topic={topic}, payload_len={len(payload)}")
    print(f"handle_node_hello called: topic={topic}, payload_len={len(payload)}", flush=True)
    data = _parse_json(payload)
    if not data:
        logger.warning(f"Invalid JSON in node_hello from topic {topic}, payload preview: {payload[:200] if payload else 'empty'}")
        print(f"ERROR: Invalid JSON in node_hello from topic {topic}", flush=True)
        return
    
    logger.info(f"Parsed node_hello JSON: {data}")
    print(f"Parsed node_hello JSON: {data}", flush=True)
    
    # Проверяем, что это действительно node_hello
    if data.get("message_type") != "node_hello":
        logger.warning(f"Not a node_hello message, message_type={data.get('message_type')}")
        return
    
    hardware_id = data.get("hardware_id")
    if not hardware_id:
        logger.warning(f"Missing hardware_id in node_hello from topic {topic}")
        return
    
    logger.info(f"Processing node_hello for hardware_id={hardware_id}")
    
    # Извлекаем параметры из топика (если они есть)
    zone_uid = _extract_zone_uid(topic)
    node_uid = _extract_node_uid(topic)
    
    # Формируем данные для регистрации в формате node_hello
    # Laravel ожидает message_type="node_hello" для обработки через registerNodeFromHello
    provisioning_meta = data.get("provisioning_meta") or {}
    register_data = {
        "message_type": "node_hello",  # Важно: указываем message_type для обработки node_hello
        "hardware_id": hardware_id,
        "node_type": data.get("node_type"),
        "fw_version": data.get("fw_version"),
        "hardware_revision": data.get("hardware_revision"),
        "capabilities": data.get("capabilities", []),
        "provisioning_meta": {
            "node_name": provisioning_meta.get("node_name"),
            "greenhouse_token": provisioning_meta.get("greenhouse_token"),
            "zone_id": zone_uid or provisioning_meta.get("zone_id"),
        }
    }
    
    # Вызываем Laravel API для регистрации
    s = get_settings()
    url = f"{s.laravel_api_url}/api/nodes/register"
    logger.info(f"Preparing to call Laravel API for node_hello registration", {
        "hardware_id": hardware_id,
        "url": url,
        "laravel_api_url": s.laravel_api_url,
        "has_token": bool(s.laravel_api_token),
    })
    print(f"Preparing to call Laravel API for node_hello registration: hardware_id={hardware_id}, url={url}", flush=True)
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {}
            if s.laravel_api_token:
                headers["Authorization"] = f"Bearer {s.laravel_api_token}"
                headers["X-API-TOKEN"] = s.laravel_api_token
            
            logger.info(f"Calling Laravel API for node_hello registration", {
                "hardware_id": hardware_id,
                "url": url,
                "headers": list(headers.keys()),
                "data": register_data,
            })
            response = await client.post(url, json=register_data, headers=headers)
            
            logger.info(f"Laravel API response received", {
                "hardware_id": hardware_id,
                "status_code": response.status_code,
            })
            
            if response.status_code == 201:
                result = response.json()
                node_data = result.get("data", {})
                logger.info(f"Node registered via node_hello successfully", {
                    "hardware_id": hardware_id,
                    "node_id": node_data.get("id"),
                    "uid": node_data.get("uid"),
                    "node_type": node_data.get("type"),
                })
            elif response.status_code == 422:
                # Ошибка валидации - возможно, узел уже зарегистрирован
                try:
                    error_data = response.json()
                    logger.warning(f"Node registration validation error", {
                        "hardware_id": hardware_id,
                        "status_code": response.status_code,
                        "errors": error_data.get("errors"),
                    })
                except Exception:
                    logger.warning(f"Node registration validation error (could not parse response)", {
                        "hardware_id": hardware_id,
                        "status_code": response.status_code,
                        "response": response.text[:500],
                    })
            else:
                try:
                    error_data = response.json()
                    logger.error(f"Failed to register node via node_hello", {
                        "hardware_id": hardware_id,
                        "status_code": response.status_code,
                        "error": error_data,
                    })
                except Exception:
                    logger.error(f"Failed to register node via node_hello", {
                        "hardware_id": hardware_id,
                        "status_code": response.status_code,
                        "response": response.text[:500],
                    })
    except httpx.TimeoutException as e:
        logger.error(f"Timeout calling Laravel API for node_hello", {
            "hardware_id": hardware_id,
            "url": url,
            "error": str(e),
        })
    except httpx.ConnectError as e:
        logger.error(f"Connection error calling Laravel API for node_hello", {
            "hardware_id": hardware_id,
            "url": url,
            "error": str(e),
        })
    except Exception as e:
        logger.error(f"Error handling node_hello", {
            "hardware_id": hardware_id,
            "url": url,
            "error": str(e),
            "error_type": type(e).__name__,
        }, exc_info=True)


async def handle_heartbeat(topic: str, payload: bytes):
    """
    Обработчик heartbeat сообщений от узлов.
    
    Топик: hydro/{gh}/{zone}/{node}/heartbeat
    Payload:
    {
        "uptime": 88000,
        "free_heap": 111000,
        "rssi": -55,
        "ts": 1234567890
    }
    """
    data = _parse_json(payload)
    if not data or not isinstance(data, dict):
        logger.warning(f"Invalid JSON in heartbeat from topic {topic}")
        return
    
    node_uid = _extract_node_uid(topic)
    if not node_uid:
        logger.warning(f"Could not extract node_uid from topic {topic}")
        return
    
    # Извлекаем метрики из payload
    uptime = data.get("uptime")
    free_heap = data.get("free_heap") or data.get("free_heap_bytes")
    rssi = data.get("rssi")
    
    # Обновляем поля в таблице nodes
    updates = ["last_heartbeat_at=NOW()", "updated_at=NOW()"]
    params = [node_uid]
    param_index = 1
    
    if uptime is not None:
        updates.append(f"uptime_seconds=${param_index + 1}")
        params.append(int(uptime))
        param_index += 1
    
    if free_heap is not None:
        updates.append(f"free_heap_bytes=${param_index + 1}")
        params.append(int(free_heap))
        param_index += 1
    
    if rssi is not None:
        updates.append(f"rssi=${param_index + 1}")
        params.append(int(rssi))
        param_index += 1
    
    # Обновляем также last_seen_at при получении heartbeat
    updates.append("last_seen_at=NOW()")
    
    query = f"UPDATE nodes SET {', '.join(updates)} WHERE uid=$1"
    await execute(query, *params)
    
    HEARTBEAT_RECEIVED.labels(node_uid=node_uid).inc()
    
    logger.debug(
        "Node heartbeat received",
        extra={
            "node_uid": node_uid,
            "uptime": uptime,
            "free_heap": free_heap,
            "rssi": rssi,
        }
    )


def _extract_zone_id(topic: str) -> Optional[int]:
    """Извлечь zone_id (int) из топика (для обратной совместимости)."""
    zone_uid = _extract_zone_uid(topic)
    if zone_uid:
        try:
            return int(zone_uid.replace("zn-", ""))
        except Exception:
            return None
    return None


def _extract_zone_uid(topic: str) -> Optional[str]:
    """Извлечь zone_uid из топика."""
    # hydro/{gh}/{zone}/{node}/{channel}/telemetry
    parts = topic.split("/")
    if len(parts) >= 3:
        zone_part = parts[2]
        if zone_part.startswith("zn-"):
            return zone_part
    return None


def _extract_node_uid(topic: str) -> Optional[str]:
    parts = topic.split("/")
    if len(parts) >= 4:
        return parts[3]
    return None


# HTTP API endpoints
class IngestRequest(BaseModel):
    samples: List[dict]


@app.post("/ingest/telemetry")
async def ingest_telemetry_endpoint(req: IngestRequest):
    """HTTP endpoint для приёма телеметрии."""
    try:
        samples = []
        for s in req.samples:
            # Преобразуем timestamp если есть
            ts = None
            if s.get("ts"):
                ts_value = s["ts"]
                if isinstance(ts_value, str):
                    try:
                        ts = datetime.fromisoformat(ts_value.replace('Z', '+00:00'))
                    except Exception:
                        pass
                elif isinstance(ts_value, (int, float)):
                    ts = datetime.fromtimestamp(ts_value / 1000.0 if ts_value > 1e10 else ts_value)
            
            sample = TelemetrySampleModel(
                node_uid=s.get("node_uid", ""),
                zone_uid=s.get("zone_uid"),
                zone_id=s.get("zone_id"),  # Поддержка zone_id напрямую
                metric_type=s.get("metric_type", ""),
                value=s.get("value", 0.0),
                ts=ts,
                raw=s.get("raw"),
                channel=s.get("channel")
            )
            samples.append(sample)
        
        await process_telemetry_batch(samples)
        return JSONResponse(content={"status": "ok", "count": len(samples)})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok"}


async def run_mqtt_listener():
    """Запустить MQTT-слушатель в фоне."""
    loop = asyncio.get_running_loop()
    mqtt = MqttClient(client_id_suffix="-logger")
    logger.info("Starting MQTT client...")
    mqtt.start()
    logger.info("MQTT client started, waiting for connection...")
    # Даем время на подключение
    await asyncio.sleep(2)
    logger.info("Setting up MQTT subscriptions...")
    print("Setting up MQTT subscriptions...", flush=True)
    start_http_server(9301)

    def telemetry_cb(topic: str, payload: bytes):
        asyncio.run_coroutine_threadsafe(handle_telemetry(topic, payload), loop)

    def cmd_resp_cb(topic: str, payload: bytes):
        asyncio.run_coroutine_threadsafe(handle_command_response(topic, payload), loop)

    def status_cb(topic: str, payload: bytes):
        asyncio.run_coroutine_threadsafe(handle_status(topic, payload), loop)

    def lwt_cb(topic: str, payload: bytes):
        asyncio.run_coroutine_threadsafe(handle_lwt(topic, payload), loop)

    def node_hello_cb(topic: str, payload: bytes):
        logger.info(f"node_hello_cb called: topic={topic}, payload_len={len(payload)}")
        print(f"node_hello_cb called: topic={topic}, payload_len={len(payload)}", flush=True)
        asyncio.run_coroutine_threadsafe(handle_node_hello(topic, payload), loop)

    def heartbeat_cb(topic: str, payload: bytes):
        asyncio.run_coroutine_threadsafe(handle_heartbeat(topic, payload), loop)

    mqtt.subscribe("hydro/+/+/+/+/telemetry", telemetry_cb, qos=1)
    logger.info("Subscribed to hydro/+/+/+/+/telemetry")
    mqtt.subscribe("hydro/+/+/+/+/command_response", cmd_resp_cb, qos=1)
    mqtt.subscribe("hydro/+/+/+/status", status_cb, qos=1)
    mqtt.subscribe("hydro/+/+/+/lwt", lwt_cb, qos=1)
    mqtt.subscribe("hydro/+/+/+/config_response", lambda t, p: asyncio.run_coroutine_threadsafe(handle_config_response(t, p), loop), qos=1)
    # Подписка на node_hello: общий топик для начальной регистрации и топик с параметрами
    logger.info("Subscribing to node_hello topics...")
    print("Subscribing to node_hello topics...", flush=True)
    mqtt.subscribe("hydro/node_hello", node_hello_cb, qos=1)
    logger.info("Subscribed to hydro/node_hello")
    print("Subscribed to hydro/node_hello", flush=True)
    mqtt.subscribe("hydro/+/+/+/node_hello", node_hello_cb, qos=1)
    logger.info("Subscribed to hydro/+/+/+/node_hello")
    print("Subscribed to hydro/+/+/+/node_hello", flush=True)
    logger.info("All node_hello subscriptions completed")
    # Подписка на heartbeat
    mqtt.subscribe("hydro/+/+/+/heartbeat", heartbeat_cb, qos=1)

    # keep alive and timeout loop
    while True:
        await mark_timeouts(30)
        await asyncio.sleep(5)


async def start_background_tasks():
    """Запустить MQTT-слушатель в фоне."""
    await run_mqtt_listener()


@app.on_event("startup")
async def startup_event():
    """Запустить фоновые задачи при старте FastAPI."""
    asyncio.create_task(start_background_tasks())


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    # Запускаем uvicorn для HTTP API
    uvicorn.run(app, host="0.0.0.0", port=9300)


