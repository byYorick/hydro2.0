import asyncio
import json
import logging
import signal
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List
import httpx

from fastapi import FastAPI
from prometheus_client import Counter, Histogram
from pydantic import BaseModel

from common.db import execute, fetch, upsert_telemetry_last, create_zone_event
from common.redis_queue import TelemetryQueue, TelemetryQueueItem, close_redis_client
from common.mqtt import MqttClient, get_mqtt_client
from common.env import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager для управления startup и shutdown событиями."""
    # Startup
    global telemetry_queue
    
    logger.info("Starting History Logger service")
    
    # Инициализация Redis queue
    telemetry_queue = TelemetryQueue()
    
    # Запуск фоновой задачи обработки очереди
    asyncio.create_task(process_telemetry_queue())
    
    # Подключение к MQTT
    mqtt = await get_mqtt_client()
    await mqtt.subscribe("hydro/+/+/+/telemetry/+", handle_telemetry)
    await mqtt.subscribe("hydro/+/+/+/heartbeat", handle_heartbeat)
    # Подписка на node_hello для регистрации новых узлов
    await mqtt.subscribe("hydro/node_hello", handle_node_hello)
    await mqtt.subscribe("hydro/+/+/+/node_hello", handle_node_hello)
    
    logger.info("History Logger service started")
    logger.info("Subscribed to MQTT topics: hydro/+/+/+/telemetry/+, hydro/+/+/+/heartbeat, hydro/node_hello, hydro/+/+/+/node_hello")
    
    yield
    
    # Shutdown
    logger.info("Shutting down History Logger service")
    
    # Устанавливаем флаг завершения
    shutdown_event.set()
    
    # Даем время на обработку оставшихся элементов
    await asyncio.sleep(2)
    
    # Закрываем Redis клиент
    await close_redis_client()


# FastAPI app
app = FastAPI(title="History Logger", lifespan=lifespan)

TELEM_RECEIVED = Counter("telemetry_received_total",
                         "Total telemetry messages received")
TELEM_PROCESSED = Counter("telemetry_processed_total",
                          "Total telemetry messages processed")
TELEM_BATCH_SIZE = Histogram("telemetry_batch_size",
                            "Size of telemetry batches processed")
HEARTBEAT_RECEIVED = Counter("heartbeat_received_total",
                             "Total heartbeat messages received",
                             ["node_uid"])
NODE_HELLO_RECEIVED = Counter("node_hello_received_total",
                              "Total node_hello messages received")
NODE_HELLO_REGISTERED = Counter("node_hello_registered_total",
                               "Total nodes registered from node_hello")
NODE_HELLO_ERRORS = Counter("node_hello_errors_total",
                           "Total errors processing node_hello",
                           ["error_type"])

# Global telemetry queue
telemetry_queue: Optional[TelemetryQueue] = None

# Shutdown event
shutdown_event = asyncio.Event()


class TelemetrySampleModel(BaseModel):
    """Model for telemetry sample."""
    node_uid: str
    zone_uid: Optional[str] = None
    zone_id: Optional[int] = None
    metric_type: str
    value: float
    ts: Optional[datetime] = None
    raw: Optional[dict] = None
    channel: Optional[str] = None


def _parse_json(payload: bytes) -> Optional[dict]:
    """Parse JSON payload."""
    try:
        return json.loads(payload.decode('utf-8'))
    except Exception as e:
        logger.error(f"Failed to parse JSON: {e}")
        return None


async def handle_telemetry(topic: str, payload: bytes):
    """
    Обработчик телеметрии из MQTT.
    Добавляет данные в Redis queue для последующей обработки.
    """
    global telemetry_queue

    data = _parse_json(payload)
    if not data:
        return
    TELEM_RECEIVED.inc()

    # Извлекаем данные из топика и payload
    zone_uid = _extract_zone_uid(topic)  # expects zn-{id}
    node_uid = _extract_node_uid(topic)

    # Создаём модель для очереди
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

    queue_item = TelemetryQueueItem(
        node_uid=node_uid or "",
        zone_uid=zone_uid,
        metric_type=data.get("metric_type") or data.get("metric", ""),
        value=data.get("value", 0.0),
        ts=ts,
        raw=data,
        channel=data.get("channel")
    )

    # Добавляем в Redis queue
    if telemetry_queue:
        await telemetry_queue.push(queue_item)
    else:
        logger.error("Telemetry queue not initialized, dropping message")


async def process_telemetry_batch(samples: List[TelemetrySampleModel]):
    """
    Обработать батч телеметрии и записать в БД.
    """
    if not samples:
        return

    s = get_settings()
    
    # Получаем zone_id из zone_uid для каждого образца
    zone_uid_to_id: dict[str, int] = {}
    zone_uids = list(set(s.zone_uid for s in samples if s.zone_uid))
    
    if zone_uids:
        # Извлекаем zone_id из zone_uid (формат: zn-{id})
        for zone_uid in zone_uids:
            try:
                if zone_uid.startswith("zn-"):
                    zone_id = int(zone_uid.split("-")[1])
                    zone_uid_to_id[zone_uid] = zone_id
            except (ValueError, IndexError):
                logger.warning(f"Invalid zone_uid format: {zone_uid}")
                continue
    
    # Получаем node_id из node_uid для каждого образца
    node_uid_to_id: dict[str, int] = {}
    node_uids = list(set(s.node_uid for s in samples if s.node_uid))
    
    if node_uids:
        cmd_rows = await fetch(
            """
            SELECT id, uid
            FROM nodes
            WHERE uid = ANY($1::text[])
            """,
            node_uids,
        )
        for row in cmd_rows:
            node_uid_to_id[row["uid"]] = row["id"]
    
    # Группируем по zone_id и metric_type для batch insert
    grouped: dict[tuple[int, str, Optional[int], Optional[str]], list[TelemetrySampleModel]] = {}
    
    for sample in samples:
        zone_id = None
        if sample.zone_uid:
            zone_id = zone_uid_to_id.get(sample.zone_uid)
        
        node_id = None
        if sample.node_uid:
            node_id = node_uid_to_id.get(sample.node_uid)
        
        if not zone_id:
            logger.warning(f"Skipping sample: zone_id not found for zone_uid={sample.zone_uid}")
            continue
        
        key = (zone_id, sample.metric_type, node_id, sample.channel)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(sample)
    
    # Batch insert в telemetry_samples
    for (zone_id, metric_type, node_id, channel), group_samples in grouped.items():
        # Используем TimescaleDB для эффективной вставки
        values_list = []
        params_list = []
        param_index = 1
        
        for sample in group_samples:
            ts = sample.ts or datetime.utcnow()
            value = sample.value
            
            # Исправлено: добавляем ts в плейсхолдеры (6 параметров вместо 5)
            values_list.append(
                f"(${param_index}, ${param_index + 1}, ${param_index + 2}, ${param_index + 3}, ${param_index + 4}, ${param_index + 5})"
            )
            # Исправлено: добавляем ts в параметры
            params_list.extend([zone_id, node_id, metric_type, channel, value, ts])
            param_index += 6
        
        if values_list:
            query = f"""
                INSERT INTO telemetry_samples (zone_id, node_id, metric_type, channel, value, ts)
                VALUES {', '.join(values_list)}
            """
            try:
                await execute(query, *params_list)
            except Exception as e:
                logger.error(f"Failed to insert telemetry batch: {e}", exc_info=True)
        
        # Обновляем telemetry_last
        if group_samples:
            last_sample = group_samples[-1]  # Последний образец
            await upsert_telemetry_last(
                zone_id,
                metric_type,
                node_id,
                channel,
                last_sample.value
            )
    
    TELEM_PROCESSED.inc(len(samples))
    TELEM_BATCH_SIZE.observe(len(samples))


async def process_telemetry_queue():
    """
    Фоновая задача для обработки очереди телеметрии из Redis.
    Обрабатывает батчи данных согласно настройкам.
    """
    global telemetry_queue

    s = get_settings()
    last_flush = datetime.utcnow()

    logger.info("Starting telemetry queue processor")

    while not shutdown_event.is_set():
        try:
            # Проверяем условия для flush
            queue_size = await telemetry_queue.size()
            time_since_flush = (datetime.utcnow() - last_flush).total_seconds() * 1000

            should_flush = (
                queue_size >= s.telemetry_batch_size or
                (time_since_flush >= s.telemetry_flush_ms and queue_size > 0)
            )

            if should_flush:
                # Извлекаем батч из очереди
                batch_size = min(s.telemetry_batch_size, queue_size)
                queue_items = await telemetry_queue.pop_batch(batch_size)

                if queue_items:
                    # Преобразуем в TelemetrySampleModel
                    samples = []
                    for item in queue_items:
                        # Получаем zone_id из zone_uid
                        zone_id = None
                        if item.zone_uid:
                            try:
                                if item.zone_uid.startswith("zn-"):
                                    zone_id = int(item.zone_uid.split("-")[1])
                            except (ValueError, IndexError):
                                pass

                        sample = TelemetrySampleModel(
                            node_uid=item.node_uid,
                            zone_uid=item.zone_uid,
                            zone_id=zone_id,
                            metric_type=item.metric_type,
                            value=item.value,
                            ts=item.ts,
                            raw=item.raw,
                            channel=item.channel
                        )
                        samples.append(sample)

                    # Обрабатываем батч
                    await process_telemetry_batch(samples)
                    last_flush = datetime.utcnow()

            # Небольшая задержка перед следующей проверкой
            await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Error in telemetry queue processor: {e}", exc_info=True)
            await asyncio.sleep(1)

    # При завершении обрабатываем оставшиеся элементы
    logger.info("Shutting down telemetry queue processor, processing remaining items...")
    remaining_items = await telemetry_queue.pop_batch(s.telemetry_batch_size * 10)  # Большой батч для финальной обработки
    if remaining_items:
        samples = []
        for item in remaining_items:
            zone_id = None
            if item.zone_uid:
                try:
                    if item.zone_uid.startswith("zn-"):
                        zone_id = int(item.zone_uid.split("-")[1])
                except (ValueError, IndexError):
                    pass

            sample = TelemetrySampleModel(
                node_uid=item.node_uid,
                zone_uid=item.zone_uid,
                zone_id=zone_id,
                metric_type=item.metric_type,
                value=item.value,
                ts=item.ts,
                raw=item.raw,
                channel=item.channel
            )
            samples.append(sample)
        await process_telemetry_batch(samples)
    logger.info("Telemetry queue processor stopped")


async def handle_node_hello(topic: str, payload: bytes):
    """
    Обработчик node_hello сообщений от узлов ESP32.
    Регистрирует новые узлы через Laravel API.
    """
    try:
        logger.info(f"[NODE_HELLO] Received message on topic {topic}, payload length: {len(payload)}")
        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[NODE_HELLO] Invalid JSON in node_hello from topic {topic}")
            NODE_HELLO_ERRORS.labels(error_type="invalid_json").inc()
            return
        
        # Проверяем, что это действительно node_hello сообщение
        if data.get("message_type") != "node_hello":
            logger.debug(f"[NODE_HELLO] Not a node_hello message, skipping: {data.get('message_type')}")
            return
        
        hardware_id = data.get("hardware_id")
        if not hardware_id:
            logger.warning(f"[NODE_HELLO] Missing hardware_id in node_hello message")
            NODE_HELLO_ERRORS.labels(error_type="missing_hardware_id").inc()
            return
        
        logger.info(f"[NODE_HELLO] Processing node_hello from hardware_id: {hardware_id}")
        NODE_HELLO_RECEIVED.inc()
    except Exception as e:
        logger.error(f"[NODE_HELLO] Error parsing node_hello: {e}", exc_info=True)
        NODE_HELLO_ERRORS.labels(error_type="parse_error").inc()
        return
    
    s = get_settings()
    laravel_url = s.laravel_api_url if hasattr(s, 'laravel_api_url') else None
    laravel_token = s.laravel_api_token if hasattr(s, 'laravel_api_token') else None
    
    if not laravel_url:
        logger.error("[NODE_HELLO] Laravel API URL not configured, cannot register node")
        NODE_HELLO_ERRORS.labels(error_type="config_missing").inc()
        return
    
    try:
        # Подготавливаем данные для Laravel API
        api_data = {
            "message_type": "node_hello",
            "hardware_id": data.get("hardware_id"),
            "node_type": data.get("node_type"),
            "fw_version": data.get("fw_version"),
            "hardware_revision": data.get("hardware_revision"),
            "capabilities": data.get("capabilities"),
            "provisioning_meta": data.get("provisioning_meta"),
        }
        
        # Вызываем Laravel API для регистрации узла
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        # Токен опционален - если он не установлен, Laravel проверит это в своем контроллере
        if laravel_token:
            headers["Authorization"] = f"Bearer {laravel_token}"
        else:
            logger.debug(f"[NODE_HELLO] No API token configured, registering without auth")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    f"{laravel_url}/api/nodes/register",
                    json=api_data,
                    headers=headers,
                )
                
                if response.status_code == 201:
                    response_data = response.json()
                    node_uid = response_data.get("data", {}).get("uid", "unknown")
                    logger.info(
                        f"[NODE_HELLO] Node registered successfully: hardware_id={hardware_id}, "
                        f"node_uid={node_uid}"
                    )
                    NODE_HELLO_REGISTERED.inc()
                elif response.status_code == 200:
                    response_data = response.json()
                    node_uid = response_data.get("data", {}).get("uid", "unknown")
                    logger.info(
                        f"[NODE_HELLO] Node updated successfully: hardware_id={hardware_id}, "
                        f"node_uid={node_uid}"
                    )
                    NODE_HELLO_REGISTERED.inc()
                elif response.status_code == 401:
                    logger.error(
                        f"[NODE_HELLO] Unauthorized: token required or invalid. "
                        f"hardware_id={hardware_id}, "
                        f"response={response.text[:200]}"
                    )
                    NODE_HELLO_ERRORS.labels(error_type="unauthorized").inc()
                else:
                    logger.error(
                        f"[NODE_HELLO] Failed to register node: status={response.status_code}, "
                        f"hardware_id={hardware_id}, "
                        f"response={response.text[:500]}"
                    )
                    NODE_HELLO_ERRORS.labels(error_type=f"http_{response.status_code}").inc()
            except httpx.TimeoutException:
                logger.error(f"[NODE_HELLO] Timeout while registering node: hardware_id={hardware_id}")
                NODE_HELLO_ERRORS.labels(error_type="timeout").inc()
            except httpx.RequestError as e:
                logger.error(
                    f"[NODE_HELLO] Request error while registering node: hardware_id={hardware_id}, "
                    f"error={str(e)}"
                )
                NODE_HELLO_ERRORS.labels(error_type="request_error").inc()
                
    except Exception as e:
        logger.error(
            f"[NODE_HELLO] Unexpected error registering node: hardware_id={hardware_id}, "
            f"error={str(e)}",
            exc_info=True
        )
        NODE_HELLO_ERRORS.labels(error_type="exception").inc()


async def handle_heartbeat(topic: str, payload: bytes):
    """
    Обработчик heartbeat сообщений от узлов ESP32.
    Обновляет статус узла в БД.
    
    Безопасность: использует whitelist для имен полей, все значения передаются через параметры.
    """
    data = _parse_json(payload)
    if not data or not isinstance(data, dict):
        logger.warning(f"Invalid JSON in heartbeat from topic {topic}")
        return
    
    node_uid = _extract_node_uid(topic)
    if not node_uid:
        logger.warning(f"Could not extract node_uid from topic {topic}")
        return
    
    # Whitelist разрешенных полей для обновления (защита от SQL injection)
    ALLOWED_FIELDS = {
        'uptime_seconds': 'uptime',
        'free_heap_bytes': ('free_heap', 'free_heap_bytes'),
        'rssi': 'rssi',
    }
    
    # Извлекаем метрики из payload
    uptime = data.get("uptime")
    free_heap = data.get("free_heap") or data.get("free_heap_bytes")
    rssi = data.get("rssi")
    
    # Обновляем поля в таблице nodes
    # Используем фиксированные имена полей для безопасности
    updates = []
    params = [node_uid]
    param_index = 1
    
    if uptime is not None:
        try:
            uptime_int = int(uptime)
            updates.append(f"uptime_seconds=${param_index + 1}")
            params.append(uptime_int)
            param_index += 1
        except (ValueError, TypeError):
            logger.warning(f"Invalid uptime value: {uptime}")
    
    if free_heap is not None:
        try:
            free_heap_int = int(free_heap)
            updates.append(f"free_heap_bytes=${param_index + 1}")
            params.append(free_heap_int)
            param_index += 1
        except (ValueError, TypeError):
            logger.warning(f"Invalid free_heap value: {free_heap}")
    
    if rssi is not None:
        try:
            rssi_int = int(rssi)
            updates.append(f"rssi=${param_index + 1}")
            params.append(rssi_int)
            param_index += 1
        except (ValueError, TypeError):
            logger.warning(f"Invalid rssi value: {rssi}")
    
    # Всегда обновляем timestamp полей (безопасно, так как не содержат пользовательского ввода)
    updates.append("last_heartbeat_at=NOW()")
    updates.append("updated_at=NOW()")
    updates.append("last_seen_at=NOW()")
    
    # Строим запрос с использованием только разрешенных полей
    if len(updates) > 3:  # Есть хотя бы одно обновляемое поле кроме timestamp
        query = f"UPDATE nodes SET {', '.join(updates)} WHERE uid=$1"
        await execute(query, *params)
    else:
        # Только timestamp обновления
        await execute(
            "UPDATE nodes SET last_heartbeat_at=NOW(), updated_at=NOW(), last_seen_at=NOW() WHERE uid=$1",
            node_uid
        )
    
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
    # Формат: hydro/{gh_uid}/{zone_uid}/{node_uid}/telemetry/{metric_type}
    # или: hydro/{gh_uid}/zn-{zone_id}/{node_uid}/telemetry/{metric_type}
    parts = topic.split("/")
    if len(parts) >= 3:
        zone_part = parts[2]
        if zone_part.startswith("zn-"):
            try:
                return int(zone_part.split("-")[1])
            except (ValueError, IndexError):
                pass
    return None


def _extract_zone_uid(topic: str) -> Optional[str]:
    """Извлечь zone_uid из топика."""
    # Формат: hydro/{gh_uid}/{zone_uid}/{node_uid}/telemetry/{metric_type}
    parts = topic.split("/")
    if len(parts) >= 3:
        return parts[2]
    return None


def _extract_node_uid(topic: str) -> Optional[str]:
    """Извлечь node_uid из топика."""
    # Формат: hydro/{gh_uid}/{zone_uid}/{node_uid}/telemetry/{metric_type}
    parts = topic.split("/")
    if len(parts) >= 4:
        return parts[3]
    return None


# Startup и shutdown события теперь обрабатываются через lifespan handler выше
    
    logger.info("History Logger service stopped")


def setup_signal_handlers():
    """Настройка обработчиков сигналов для graceful shutdown."""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


if __name__ == "__main__":
    setup_signal_handlers()
    import uvicorn
    s = get_settings()
    uvicorn.run(app, host="0.0.0.0", port=s.service_port)
