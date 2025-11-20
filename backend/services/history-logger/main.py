import asyncio
import json
import logging
import signal
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List
import httpx

from fastapi import FastAPI
from prometheus_client import Counter, Histogram, Gauge
from pydantic import BaseModel, Field
from typing import Union
import time

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
    
    # Запуск фоновой задачи обработки очереди и отслеживание для graceful shutdown
    task = asyncio.create_task(process_telemetry_queue())
    background_tasks.append(task)
    
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
    
    # Ждем завершения фоновых задач с таймаутом
    s = get_settings()
    if background_tasks:
        logger.info(f"Waiting for {len(background_tasks)} background tasks to complete...")
        try:
            await asyncio.wait_for(
                asyncio.gather(*background_tasks, return_exceptions=True),
                timeout=s.shutdown_timeout_sec
            )
            logger.info("All background tasks completed")
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for background tasks, forcing shutdown")
            # Отменяем оставшиеся задачи
            for task in background_tasks:
                if not task.done():
                    task.cancel()
    
    # Даем время на обработку оставшихся элементов
    await asyncio.sleep(s.shutdown_wait_sec)
    
    # Закрываем Redis клиент
    await close_redis_client()
    
    logger.info("History Logger service stopped")


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

# Дополнительные метрики для мониторинга
TELEMETRY_QUEUE_SIZE = Gauge("telemetry_queue_size",
                             "Current size of Redis telemetry queue")
TELEMETRY_QUEUE_AGE = Gauge("telemetry_queue_age_seconds",
                           "Age of oldest item in queue in seconds")
TELEMETRY_PROCESSING_DURATION = Histogram("telemetry_processing_duration_seconds",
                                         "Time to process telemetry batch",
                                         buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0])
LARAVEL_API_DURATION = Histogram("laravel_api_request_duration_seconds",
                                "Laravel API request duration",
                                buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0])
REDIS_OPERATION_DURATION = Histogram("redis_operation_duration_seconds",
                                     "Redis operation duration",
                                     buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5])
TELEMETRY_DROPPED = Counter("telemetry_dropped_total",
                           "Total dropped telemetry messages",
                           ["reason"])
DATABASE_ERRORS = Counter("database_errors_total",
                         "Total database errors",
                         ["error_type"])

# Global telemetry queue
telemetry_queue: Optional[TelemetryQueue] = None

# Shutdown event
shutdown_event = asyncio.Event()

# Background tasks для отслеживания при shutdown
background_tasks: List[asyncio.Task] = []


class TelemetryPayloadModel(BaseModel):
    """Model for validating telemetry payload from MQTT."""
    metric_type: str = Field(..., min_length=1, max_length=50, description="Type of metric")
    value: float = Field(..., description="Metric value")
    timestamp: Optional[Union[int, float, str]] = Field(None, description="Timestamp in milliseconds, ISO string, or Unix timestamp")
    channel: Optional[str] = Field(None, max_length=100, description="Channel identifier")
    metric: Optional[str] = Field(None, max_length=50, description="Alternative metric type field (for backward compatibility)")


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


# Максимальный размер MQTT payload (64KB) для защиты от DoS
MAX_PAYLOAD_SIZE = 64 * 1024  # 64KB

# Конфигурация retry логики для Redis
REDIS_PUSH_MAX_RETRIES = 3
REDIS_PUSH_RETRY_BACKOFF_BASE = 2  # exponential backoff: 2^attempt секунд

async def _push_with_retry(queue_item: TelemetryQueueItem, max_retries: int = REDIS_PUSH_MAX_RETRIES) -> bool:
    """
    Добавить элемент в Redis queue с retry логикой и exponential backoff.
    
    Args:
        queue_item: Элемент для добавления в очередь
        max_retries: Максимальное количество попыток
        
    Returns:
        True если успешно добавлен, False если все попытки провалились
    """
    global telemetry_queue
    
    if not telemetry_queue:
        return False
    
    for attempt in range(max_retries):
        try:
            success = await telemetry_queue.push(queue_item)
            if success:
                if attempt > 0:
                    logger.info(f"Successfully pushed to Redis queue after {attempt + 1} attempts")
                return True
            
            # Если очередь переполнена, не повторяем
            if attempt == 0:
                logger.warning(
                    f"Redis queue full, cannot push telemetry: "
                    f"node_uid={queue_item.node_uid}, metric_type={queue_item.metric_type}"
                )
            return False
            
        except Exception as e:
            if attempt < max_retries - 1:
                backoff_seconds = REDIS_PUSH_RETRY_BACKOFF_BASE ** attempt
                logger.warning(
                    f"Failed to push to Redis queue (attempt {attempt + 1}/{max_retries}), "
                    f"retrying in {backoff_seconds}s: {e}"
                )
                await asyncio.sleep(backoff_seconds)
            else:
                logger.error(
                    f"Failed to push to Redis queue after {max_retries} attempts: {e}",
                    exc_info=True
                )
                return False
    
    return False


def _parse_json(payload: bytes) -> Optional[dict]:
    """Parse JSON payload with size validation."""
    try:
        # Проверяем размер payload для защиты от DoS
        if len(payload) > MAX_PAYLOAD_SIZE:
            logger.error(f"Payload too large: {len(payload)} bytes (max: {MAX_PAYLOAD_SIZE})")
            return None
        
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
    
    # Валидация данных через Pydantic
    try:
        validated_data = TelemetryPayloadModel(**data)
    except Exception as e:
        logger.warning(
            "Invalid telemetry payload",
            extra={
                "error": str(e),
                "topic": topic,
                "payload_keys": list(data.keys()) if isinstance(data, dict) else None,
                "payload_size": len(payload)
            }
        )
        TELEMETRY_DROPPED.labels(reason="validation_failed").inc()
        return
    
    TELEM_RECEIVED.inc()

    # Извлекаем данные из топика и payload
    zone_uid = _extract_zone_uid(topic)  # expects zn-{id}
    node_uid = _extract_node_uid(topic)

    # Создаём модель для очереди
    ts = None
    if validated_data.timestamp:
        try:
            # Если timestamp в миллисекундах
            ts_value = validated_data.timestamp
            if isinstance(ts_value, (int, float)):
                ts = datetime.fromtimestamp(ts_value / 1000.0)
            elif isinstance(ts_value, str):
                ts = datetime.fromisoformat(ts_value.replace('Z', '+00:00'))
        except Exception:
            pass

    # Используем metric_type или metric (для обратной совместимости)
    metric_type = validated_data.metric_type or validated_data.metric or ""
    if not metric_type:
        logger.warning(
            "Missing metric_type in telemetry payload",
            extra={
                "topic": topic,
                "node_uid": node_uid,
                "zone_uid": zone_uid,
                "payload_keys": list(data.keys()) if isinstance(data, dict) else None
            }
        )
        TELEMETRY_DROPPED.labels(reason="missing_metric_type").inc()
        return

    queue_item = TelemetryQueueItem(
        node_uid=node_uid or "",
        zone_uid=zone_uid,
        metric_type=metric_type,
        value=validated_data.value,
        ts=ts,
        raw=data,
        channel=validated_data.channel
    )

    # Добавляем в Redis queue с retry логикой
    if telemetry_queue:
        start_time = time.time()
        success = await _push_with_retry(queue_item)
        redis_duration = time.time() - start_time
        REDIS_OPERATION_DURATION.observe(redis_duration)
        
        if not success:
            TELEMETRY_DROPPED.labels(reason="queue_push_failed").inc()
            logger.error(
                "Failed to push telemetry to queue after retries, dropping message",
                extra={
                    "node_uid": node_uid,
                    "zone_uid": zone_uid,
                    "metric_type": queue_item.metric_type,
                    "topic": topic
                }
            )
    else:
        TELEMETRY_DROPPED.labels(reason="queue_not_initialized").inc()
        logger.error(
            "Telemetry queue not initialized, dropping message",
            extra={
                "node_uid": node_uid,
                "zone_uid": zone_uid,
                "metric_type": metric_type,
                "topic": topic
            }
        )


async def process_telemetry_batch(samples: List[TelemetrySampleModel]):
    """
    Обработать батч телеметрии и записать в БД.
    """
    if not samples:
        return

    start_time = time.time()
    s = get_settings()
    
    # Получаем zone_id из zone_uid для каждого образца
    zone_uid_to_id: dict[str, int] = {}
    zone_uids = list(set(sample.zone_uid for sample in samples if sample.zone_uid))
    
    if zone_uids:
        # Извлекаем zone_id из zone_uid (формат: zn-{id})
        for zone_uid in zone_uids:
            zone_id = extract_zone_id_from_uid(zone_uid)
            if zone_id is not None:
                zone_uid_to_id[zone_uid] = zone_id
            else:
                logger.warning(f"Invalid zone_uid format: {zone_uid}")
    
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
            logger.warning(
                "Skipping sample: zone_id not found",
                extra={
                    "zone_uid": sample.zone_uid,
                    "node_uid": sample.node_uid,
                    "metric_type": sample.metric_type
                }
            )
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
                error_type = type(e).__name__
                DATABASE_ERRORS.labels(error_type=error_type).inc()
                logger.error(
                    "Failed to insert telemetry batch",
                    extra={
                        "error_type": error_type,
                        "error": str(e),
                        "zone_id": zone_id,
                        "metric_type": metric_type,
                        "samples_count": len(group_samples)
                    },
                    exc_info=True
                )
        
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
    
    processing_duration = time.time() - start_time
    TELEMETRY_PROCESSING_DURATION.observe(processing_duration)
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
            queue_start_time = time.time()
            queue_size = await telemetry_queue.size()
            queue_duration = time.time() - queue_start_time
            REDIS_OPERATION_DURATION.observe(queue_duration)
            
            # Обновляем метрики размера очереди
            TELEMETRY_QUEUE_SIZE.set(queue_size)
            
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
                        zone_id = extract_zone_id_from_uid(item.zone_uid)

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
            await asyncio.sleep(s.queue_check_interval_sec)

        except Exception as e:
            logger.error(f"Error in telemetry queue processor: {e}", exc_info=True)
            await asyncio.sleep(s.queue_error_retry_delay_sec)

    # При завершении обрабатываем оставшиеся элементы
    logger.info("Shutting down telemetry queue processor, processing remaining items...")
    remaining_items = await telemetry_queue.pop_batch(s.telemetry_batch_size * s.final_batch_multiplier)
    if remaining_items:
        samples = []
        for item in remaining_items:
            zone_id = extract_zone_id_from_uid(item.zone_uid)

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
        
        # Retry логика для Laravel API с exponential backoff
        MAX_API_RETRIES = 3
        API_RETRY_BACKOFF_BASE = 2  # exponential backoff: 2^attempt секунд
        API_TIMEOUT = s.laravel_api_timeout_sec
        
        last_error = None
        for attempt in range(MAX_API_RETRIES):
            try:
                api_start_time = time.time()
                async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
                    response = await client.post(
                        f"{laravel_url}/api/nodes/register",
                        json=api_data,
                        headers=headers,
                    )
                api_duration = time.time() - api_start_time
                LARAVEL_API_DURATION.observe(api_duration)
                
                if response.status_code == 201:
                    response_data = response.json()
                    node_uid = response_data.get("data", {}).get("uid", "unknown")
                    logger.info(
                        f"[NODE_HELLO] Node registered successfully: hardware_id={hardware_id}, "
                        f"node_uid={node_uid}, attempts={attempt + 1}"
                    )
                    NODE_HELLO_REGISTERED.inc()
                    return  # Успешно зарегистрирован, выходим
                elif response.status_code == 200:
                    response_data = response.json()
                    node_uid = response_data.get("data", {}).get("uid", "unknown")
                    logger.info(
                        f"[NODE_HELLO] Node updated successfully: hardware_id={hardware_id}, "
                        f"node_uid={node_uid}, attempts={attempt + 1}"
                    )
                    NODE_HELLO_REGISTERED.inc()
                    return  # Успешно обновлен, выходим
                elif response.status_code == 401:
                    # Неавторизован - не повторяем (токен неверный)
                    logger.error(
                        f"[NODE_HELLO] Unauthorized: token required or invalid. "
                        f"hardware_id={hardware_id}, "
                        f"response={response.text[:200]}"
                    )
                    NODE_HELLO_ERRORS.labels(error_type="unauthorized").inc()
                    return
                elif response.status_code >= 500:
                    # Серверная ошибка - можно повторить
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                    if attempt < MAX_API_RETRIES - 1:
                        backoff_seconds = API_RETRY_BACKOFF_BASE ** attempt
                        logger.warning(
                            f"[NODE_HELLO] Server error {response.status_code} (attempt {attempt + 1}/{MAX_API_RETRIES}), "
                            f"retrying in {backoff_seconds}s: hardware_id={hardware_id}"
                        )
                        await asyncio.sleep(backoff_seconds)
                        continue
                    else:
                        logger.error(
                            f"[NODE_HELLO] Failed to register node after {MAX_API_RETRIES} attempts: "
                            f"status={response.status_code}, hardware_id={hardware_id}, "
                            f"response={response.text[:500]}"
                        )
                        NODE_HELLO_ERRORS.labels(error_type=f"http_{response.status_code}").inc()
                        return
                else:
                    # Клиентская ошибка (4xx) - не повторяем
                    logger.error(
                        f"[NODE_HELLO] Failed to register node: status={response.status_code}, "
                        f"hardware_id={hardware_id}, "
                        f"response={response.text[:500]}"
                    )
                    NODE_HELLO_ERRORS.labels(error_type=f"http_{response.status_code}").inc()
                    return
                        
            except httpx.TimeoutException as e:
                last_error = f"Timeout: {str(e)}"
                if attempt < MAX_API_RETRIES - 1:
                    backoff_seconds = API_RETRY_BACKOFF_BASE ** attempt
                    logger.warning(
                        f"[NODE_HELLO] Timeout (attempt {attempt + 1}/{MAX_API_RETRIES}), "
                        f"retrying in {backoff_seconds}s: hardware_id={hardware_id}"
                    )
                    await asyncio.sleep(backoff_seconds)
                else:
                    logger.error(
                        f"[NODE_HELLO] Timeout while registering node after {MAX_API_RETRIES} attempts: "
                        f"hardware_id={hardware_id}"
                    )
                    NODE_HELLO_ERRORS.labels(error_type="timeout").inc()
                    return
            except httpx.RequestError as e:
                last_error = f"Request error: {str(e)}"
                if attempt < MAX_API_RETRIES - 1:
                    backoff_seconds = API_RETRY_BACKOFF_BASE ** attempt
                    logger.warning(
                        f"[NODE_HELLO] Request error (attempt {attempt + 1}/{MAX_API_RETRIES}), "
                        f"retrying in {backoff_seconds}s: hardware_id={hardware_id}, error={str(e)}"
                    )
                    await asyncio.sleep(backoff_seconds)
                else:
                    logger.error(
                        f"[NODE_HELLO] Request error while registering node after {MAX_API_RETRIES} attempts: "
                        f"hardware_id={hardware_id}, error={str(e)}"
                    )
                    NODE_HELLO_ERRORS.labels(error_type="request_error").inc()
                    return
        
        # Если дошли сюда, все попытки провалились
        if last_error:
            logger.error(
                f"[NODE_HELLO] Failed to register node after {MAX_API_RETRIES} attempts: "
                f"hardware_id={hardware_id}, last_error={last_error}"
            )
            NODE_HELLO_ERRORS.labels(error_type="max_retries_exceeded").inc()
                
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


def extract_zone_id_from_uid(zone_uid: Optional[str]) -> Optional[int]:
    """
    Извлечь zone_id из zone_uid (формат: zn-{id}).
    
    Args:
        zone_uid: zone_uid в формате "zn-{id}" или None
        
    Returns:
        zone_id как int или None если формат неверный
    """
    if not zone_uid or not zone_uid.startswith("zn-"):
        return None
    try:
        return int(zone_uid.split("-")[1])
    except (ValueError, IndexError):
        return None


def _extract_zone_id(topic: str) -> Optional[int]:
    """Извлечь zone_id (int) из топика (для обратной совместимости)."""
    # Формат: hydro/{gh_uid}/{zone_uid}/{node_uid}/telemetry/{metric_type}
    # или: hydro/{gh_uid}/zn-{zone_id}/{node_uid}/telemetry/{metric_type}
    parts = topic.split("/")
    if len(parts) >= 3:
        zone_part = parts[2]
        return extract_zone_id_from_uid(zone_part)
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


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/ingest/telemetry")
async def ingest_telemetry(payload: dict):
    """
    HTTP endpoint для приема телеметрии.
    Принимает JSON с массивом samples и обрабатывает их батчем.
    """
    samples_data = payload.get("samples", [])
    if not samples_data:
        return {"status": "ok", "count": 0}
    
    # Преобразуем в TelemetrySampleModel
    samples = []
    for sample_data in samples_data:
        # Преобразуем timestamp если есть
        ts = None
        if sample_data.get("ts"):
            ts_value = sample_data.get("ts")
            if isinstance(ts_value, str):
                try:
                    ts = datetime.fromisoformat(ts_value.replace('Z', '+00:00'))
                except Exception:
                    pass
            elif isinstance(ts_value, (int, float)):
                try:
                    ts = datetime.fromtimestamp(ts_value / 1000.0)
                except Exception:
                    pass
        elif sample_data.get("timestamp"):
            ts_value = sample_data.get("timestamp")
            if isinstance(ts_value, str):
                try:
                    ts = datetime.fromisoformat(ts_value.replace('Z', '+00:00'))
                except Exception:
                    pass
            elif isinstance(ts_value, (int, float)):
                try:
                    ts = datetime.fromtimestamp(ts_value / 1000.0)
                except Exception:
                    pass
        
        # Извлекаем zone_id из zone_uid если нужно
        zone_id = sample_data.get("zone_id")
        if not zone_id and sample_data.get("zone_uid"):
            zone_uid = sample_data.get("zone_uid")
            zone_id = extract_zone_id_from_uid(zone_uid)
        
        sample = TelemetrySampleModel(
            node_uid=sample_data.get("node_uid", ""),
            zone_uid=sample_data.get("zone_uid"),
            zone_id=zone_id,
            metric_type=sample_data.get("metric_type", ""),
            value=sample_data.get("value", 0.0),
            ts=ts,
            raw=sample_data,
            channel=sample_data.get("channel")
        )
        samples.append(sample)
    
    # Обрабатываем батч
    await process_telemetry_batch(samples)
    
    return {"status": "ok", "count": len(samples)}


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
