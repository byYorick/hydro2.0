import asyncio
import json
import logging
import os
import signal
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List
import httpx

from fastapi import FastAPI, Response, Request, HTTPException, Body
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel, Field
from typing import Union, Dict, Any
from collections import defaultdict
import time

from common.db import execute, fetch, upsert_telemetry_last, create_zone_event
from common.redis_queue import TelemetryQueue, TelemetryQueueItem, close_redis_client
from common.mqtt import MqttClient, AsyncMqttClient, get_mqtt_client
from common.env import get_settings
from common.water_flow import execute_fill_mode, execute_drain_mode, calibrate_flow
from common.service_logs import send_service_log

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager для управления startup и shutdown событиями."""
    # Startup
    global telemetry_queue
    
    logger.info("Starting History Logger service")
    send_service_log(
        service="history-logger",
        level="info",
        message="History Logger service starting",
        context={"stage": "startup"},
    )
    
    # Инициализация Redis queue
    telemetry_queue = TelemetryQueue()
    
    # Запуск фоновой задачи обработки очереди и отслеживание для graceful shutdown
    task = asyncio.create_task(process_telemetry_queue())
    background_tasks.append(task)
    
    # Подключение к MQTT
    mqtt = await get_mqtt_client()
    # Формат топика согласно документации: hydro/{gh}/{zone}/{node}/{channel}/telemetry
    await mqtt.subscribe("hydro/+/+/+/+/telemetry", handle_telemetry)
    await mqtt.subscribe("hydro/+/+/+/heartbeat", handle_heartbeat)
    # Подписка на node_hello для регистрации новых узлов
    await mqtt.subscribe("hydro/node_hello", handle_node_hello)
    await mqtt.subscribe("hydro/+/+/+/node_hello", handle_node_hello)
    # Подписка на config_response для обработки подтверждений установки конфига
    await mqtt.subscribe("hydro/+/+/+/config_response", handle_config_response)
    # Подписка на command_response для обновления статусов команд (уведомления на фронт)
    await mqtt.subscribe("hydro/+/+/+/+/command_response", handle_command_response)
    
    logger.info("History Logger service started")
    logger.info("Subscribed to MQTT topics: hydro/+/+/+/+/telemetry, hydro/+/+/+/heartbeat, hydro/node_hello, hydro/+/+/+/node_hello, hydro/+/+/+/config_response, hydro/+/+/+/+/command_response")
    
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
    send_service_log(
        service="history-logger",
        level="info",
        message="History Logger service stopped",
        context={"stage": "shutdown"},
    )


# FastAPI app
app = FastAPI(title="History Logger", lifespan=lifespan)

# Middleware для логирования всех входящих HTTP запросов
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Логирование всех входящих HTTP запросов для диагностики."""
    start_time = time.time()
    
    # Логируем входящий запрос
    logger.info(
        f"[HTTP_REQUEST] {request.method} {request.url.path} from {request.client.host if request.client else 'unknown'}"
    )
    
    # Логируем заголовки (особенно Authorization для диагностики)
    auth_header = request.headers.get("Authorization", "")
    if auth_header:
        logger.debug(f"[HTTP_REQUEST] Authorization header present: {auth_header[:20]}...")
    else:
        logger.debug(f"[HTTP_REQUEST] No Authorization header")
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(
            f"[HTTP_REQUEST] {request.method} {request.url.path} -> {response.status_code} ({process_time:.3f}s)"
        )
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(
            f"[HTTP_REQUEST] {request.method} {request.url.path} -> ERROR: {e} ({process_time:.3f}s)",
            exc_info=True
        )
        raise


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    metrics_data = generate_latest()
    return Response(content=metrics_data.decode('utf-8') if isinstance(metrics_data, bytes) else metrics_data, media_type=CONTENT_TYPE_LATEST)

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
CONFIG_RESPONSE_RECEIVED = Counter("config_response_received_total",
                                   "Total config_response messages received")
CONFIG_RESPONSE_SUCCESS = Counter("config_response_success_total",
                                 "Total successful config_response messages",
                                 ["node_uid"])
CONFIG_RESPONSE_ERROR = Counter("config_response_error_total",
                               "Total error config_response messages",
                               ["node_uid"])
CONFIG_RESPONSE_PROCESSED = Counter("config_response_processed_total",
                                  "Total config_response messages processed")
COMMAND_RESPONSE_RECEIVED = Counter("command_response_received_total",
                                   "Total command_response messages received")
COMMAND_RESPONSE_ERROR = Counter("command_response_error_total",
                                "Total error command_response messages")

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
INGEST_AUTH_FAILED = Counter("ingest_auth_failed_total",
                             "Total failed authentication attempts for HTTP ingest")
INGEST_RATE_LIMITED = Counter("ingest_rate_limited_total",
                              "Total rate limited requests for HTTP ingest")
INGEST_REQUESTS = Counter("ingest_requests_total",
                          "Total HTTP ingest requests",
                          ["status"])

# Global telemetry queue
telemetry_queue: Optional[TelemetryQueue] = None

# Shutdown event
shutdown_event = asyncio.Event()

# Background tasks для отслеживания при shutdown
background_tasks: List[asyncio.Task] = []

# Rate limiting для HTTP ingest endpoint
# Простой in-memory rate limiter (можно улучшить через Redis для распределенных систем)
_ingest_rate_limiter: Dict[str, List[float]] = defaultdict(list)
# Настройки rate limiting
INGEST_RATE_LIMIT_REQUESTS = 100  # Максимум запросов
INGEST_RATE_LIMIT_WINDOW_SEC = 60  # За окно времени (60 секунд)


class TelemetryPayloadModel(BaseModel):
    """Model for validating telemetry payload from MQTT."""
    model_config = {"extra": "allow"}  # Разрешаем дополнительные поля от прошивок (tds, error_code, temperature, health и т.п.)
    
    metric_type: str = Field(..., min_length=1, max_length=50, description="Type of metric")
    value: float = Field(..., description="Metric value")
    ts: Optional[Union[int, float, str]] = Field(None, description="Timestamp in seconds (Unix timestamp) from firmware")
    channel: Optional[str] = Field(None, max_length=100, description="Channel identifier")
    # Опциональные поля от прошивок
    node_id: Optional[str] = Field(None, max_length=100, description="Node ID (from firmware)")
    raw: Optional[Union[int, float]] = Field(None, description="Raw sensor value (from firmware)")
    stub: Optional[bool] = Field(None, description="Stub flag indicating if value is simulated (from firmware)")
    stable: Optional[bool] = Field(None, description="Stability flag for sensor readings (from firmware)")
    # Дополнительные поля от прошивок (ec_node, ph_node, pump_node и т.п.)
    tds: Optional[Union[int, float]] = Field(None, description="TDS value (from ec_node)")
    error_code: Optional[Union[int, str]] = Field(None, description="Error code (from firmware)")
    temperature: Optional[float] = Field(None, description="Temperature value (from firmware)")
    state: Optional[str] = Field(None, max_length=50, description="State (from firmware)")
    event: Optional[str] = Field(None, max_length=100, description="Event (from firmware)")
    health: Optional[dict] = Field(None, description="Health metrics (from pump_node)")
    zone_uid: Optional[str] = Field(None, max_length=100, description="Zone UID (fallback from payload)")
    node_uid: Optional[str] = Field(None, max_length=100, description="Node UID (fallback from payload)")
    gh_uid: Optional[str] = Field(None, max_length=100, description="Greenhouse UID (for multi-greenhouse zone resolution)")


class TelemetrySampleModel(BaseModel):
    """Model for telemetry sample."""
    node_uid: str
    zone_uid: Optional[str] = None
    zone_id: Optional[int] = None
    gh_uid: Optional[str] = None  # Greenhouse UID для корректного резолва зоны в многотепличной конфигурации
    metric_type: str
    value: float
    ts: Optional[datetime] = None
    raw: Optional[dict] = None
    channel: Optional[str] = None


# Максимальный размер MQTT payload (64KB) для защиты от DoS
MAX_PAYLOAD_SIZE = 64 * 1024  # 64KB

# Максимальное количество samples в HTTP ingest батче для защиты от DoS
MAX_INGEST_SAMPLES = 1000  # Максимум 1000 samples за один запрос

# Максимальный размер raw JSON для защиты от раздувания БД
MAX_RAW_JSON_SIZE = 10 * 1024  # 10KB максимум для raw поля


def _filter_raw_data(raw_data: Optional[dict]) -> Optional[dict]:
    """
    Фильтрует и ограничивает размер raw данных для сохранения в БД.
    
    Args:
        raw_data: Исходные raw данные из payload
        
    Returns:
        Отфильтрованные raw данные или None если данные слишком большие/невалидные
    """
    if not raw_data or not isinstance(raw_data, dict):
        return raw_data
    
    # Whitelist разрешенных полей для raw (только телеметрические данные)
    ALLOWED_RAW_FIELDS = {
        'metric_type', 'value', 'ts', 'channel', 'node_id', 'raw', 'stub', 'stable',
        'tds', 'error_code', 'temperature', 'state', 'event', 'health',
        'zone_uid', 'node_uid', 'gh_uid'
    }
    
    # Фильтруем только разрешенные поля
    filtered = {
        k: v for k, v in raw_data.items()
        if k in ALLOWED_RAW_FIELDS
    }
    
    # Проверяем размер после сериализации
    try:
        json_str = json.dumps(filtered, default=str)
        if len(json_str.encode('utf-8')) > MAX_RAW_JSON_SIZE:
            # Если слишком большой, оставляем только критичные поля
            minimal = {
                'metric_type': filtered.get('metric_type'),
                'value': filtered.get('value'),
                'ts': filtered.get('ts'),
            }
            json_str = json.dumps(minimal, default=str)
            if len(json_str.encode('utf-8')) > MAX_RAW_JSON_SIZE:
                # Даже минимальный набор слишком большой - возвращаем None
                logger.warning(
                    "Raw data too large even after filtering, dropping",
                    extra={"original_size": len(json.dumps(raw_data, default=str).encode('utf-8'))}
                )
                return None
            return minimal
        return filtered
    except Exception as e:
        logger.warning(f"Failed to filter raw data: {e}")
        return None

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
        logger.warning(f"[TELEMETRY] Failed to parse JSON from topic: {topic}")
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
    # Формат топика: hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/telemetry
    gh_uid = _extract_gh_uid(topic)  # Greenhouse UID для корректного резолва зоны в многотепличной конфигурации
    zone_uid = _extract_zone_uid(topic)  # expects zn-{id}
    node_uid = _extract_node_uid(topic)
    channel = _extract_channel_from_topic(topic)  # Извлекаем channel из топика
    
    # Fallback: используем zone_uid/node_uid из payload если не извлекается из топика
    if not zone_uid and validated_data.zone_uid:
        zone_uid = validated_data.zone_uid
    if not node_uid and validated_data.node_uid:
        node_uid = validated_data.node_uid

    # Создаём модель для очереди
    # Проверка валидности ts: должен быть > 1_000_000_000 (примерно 2001-09-09)
    # Если ts невалиден (аптайм несинхронизированной ноды), используем серверное время
    MIN_VALID_TIMESTAMP = 1_000_000_000  # 2001-09-09 01:46:40 UTC
    ts = None
    if validated_data.ts:
        try:
            ts_value = None
            if isinstance(validated_data.ts, (int, float)):
                ts_value = float(validated_data.ts)
                # Проверяем что ts разумный (не аптайм несинхронизированной ноды)
                if ts_value >= MIN_VALID_TIMESTAMP:
                    ts = datetime.fromtimestamp(ts_value)
                else:
                    logger.warning(
                        "Invalid timestamp from firmware (likely uptime), using server time",
                        extra={
                            "ts": ts_value,
                            "topic": topic,
                            "node_uid": node_uid,
                            "zone_uid": zone_uid
                        }
                    )
            elif isinstance(validated_data.ts, str):
                ts = datetime.fromisoformat(validated_data.ts.replace('Z', '+00:00'))
                # Проверяем что ts разумный
                ts_timestamp = ts.timestamp()
                if ts_timestamp < MIN_VALID_TIMESTAMP:
                    logger.warning(
                        "Invalid timestamp from firmware (likely uptime), using server time",
                        extra={
                            "ts": ts_timestamp,
                            "topic": topic,
                            "node_uid": node_uid,
                            "zone_uid": zone_uid
                        }
                    )
                    ts = None
        except Exception as e:
            logger.warning(
                "Failed to parse timestamp, using server time",
                extra={
                    "ts": validated_data.ts,
                    "error": str(e),
                    "topic": topic,
                    "node_uid": node_uid,
                    "zone_uid": zone_uid
                }
            )
    
    # Если ts невалиден или отсутствует, используем серверное время
    if ts is None:
        ts = datetime.utcnow()

    # Используем metric_type (обязательное поле)
    metric_type = validated_data.metric_type
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

    # Используем channel из топика, если не указан в payload
    channel_name = validated_data.channel or channel
    
    # Фильтруем raw данные для защиты от раздувания БД
    filtered_raw = _filter_raw_data(data)
    
    queue_item = TelemetryQueueItem(
        node_uid=node_uid or "",
        zone_uid=zone_uid,
        gh_uid=gh_uid,  # Greenhouse UID для корректного резолва зоны в многотепличной конфигурации
        metric_type=metric_type,
        value=validated_data.value,
        ts=ts,
        raw=filtered_raw,  # Сохраняем отфильтрованные данные
        channel=channel_name,
        enqueued_at=datetime.utcnow()  # Время добавления в очередь для трекинга возраста
    )

    # Минимальное логирование: телеметрия принята
    logger.info(f"[TELEMETRY] Received: node={node_uid}, metric={metric_type}, value={validated_data.value}")
    
    if telemetry_queue:
        start_time = time.time()
        success = await _push_with_retry(queue_item)
        redis_duration = time.time() - start_time
        REDIS_OPERATION_DURATION.observe(redis_duration)
        
        if not success:
            logger.warning(f"[TELEMETRY] Failed to push to queue: node={node_uid}, metric={metric_type}")
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
        logger.error(f"[TELEMETRY] Queue not initialized: node={node_uid}, metric={metric_type}")
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
    
    # Получаем zone_id из zone_uid с учетом gh_uid для каждого образца
    # Ключ: (zone_uid, gh_uid) -> zone_id
    zone_uid_to_id: dict[tuple[str, Optional[str]], int] = {}
    
    # Группируем samples по (zone_uid, gh_uid) для батчевого резолва
    zone_gh_pairs = list(set(
        (sample.zone_uid, sample.gh_uid) 
        for sample in samples 
        if sample.zone_uid
    ))
    
    if zone_gh_pairs:
        # Батчевый резолв зон с учетом gh_uid
        for zone_uid, gh_uid in zone_gh_pairs:
            zone_id_from_uid = extract_zone_id_from_uid(zone_uid)
            # zone_id_from_uid может быть None для формата zone-{uid}, это нормально - будем искать по UID
            
            # Ищем зону по zone_id И gh_uid (через JOIN с greenhouses)
            if gh_uid:
                # Резолв с учетом greenhouse
                if zone_id_from_uid is not None:
                    # Числовой ID (формат zn-{id})
                    zone_rows = await fetch(
                        """
                        SELECT z.id
                        FROM zones z
                        JOIN greenhouses g ON g.id = z.greenhouse_id
                        WHERE z.id = $1 AND g.uid = $2
                        """,
                        zone_id_from_uid,
                        gh_uid
                    )
                else:
                    # UID формат (zone-{uid}) - ищем по uid зоны
                    zone_rows = await fetch(
                        """
                        SELECT z.id
                        FROM zones z
                        JOIN greenhouses g ON g.id = z.greenhouse_id
                        WHERE z.uid = $1 AND g.uid = $2
                        """,
                        zone_uid,
                        gh_uid
                    )
                
                if zone_rows and len(zone_rows) > 0:
                    zone_uid_to_id[(zone_uid, gh_uid)] = zone_rows[0]["id"]
                else:
                    logger.warning(
                        f"Zone not found: zone_uid={zone_uid}, gh_uid={gh_uid}",
                        extra={"zone_uid": zone_uid, "gh_uid": gh_uid}
                    )
            else:
                # Fallback: если gh_uid не указан, используем простое извлечение (для обратной совместимости)
                # Но это может привести к проблемам в многотепличной конфигурации
                if zone_id_from_uid is not None:
                    zone_uid_to_id[(zone_uid, None)] = zone_id_from_uid
                else:
                    # Ищем по UID без greenhouse
                    zone_rows = await fetch(
                        """
                        SELECT id
                        FROM zones
                        WHERE uid = $1
                        """,
                        zone_uid
                    )
                    if zone_rows and len(zone_rows) > 0:
                        zone_uid_to_id[(zone_uid, None)] = zone_rows[0]["id"]
                    else:
                        logger.warning(
                            f"Zone not found by UID: zone_uid={zone_uid}",
                            extra={"zone_uid": zone_uid}
                        )
    
    # Получаем node_id из node_uid с учетом gh_uid для каждого образца
    # Ключ: (node_uid, gh_uid) -> (node_id, zone_id) - сохраняем zone_id узла для проверки соответствия
    node_uid_to_info: dict[tuple[str, Optional[str]], tuple[int, int]] = {}
    
    # Группируем samples по (node_uid, gh_uid) для батчевого резолва
    node_gh_pairs = list(set(
        (s.node_uid, s.gh_uid)
        for s in samples
        if s.node_uid
    ))
    
    if node_gh_pairs:
        # Батчевый резолв узлов с учетом gh_uid (через zones и greenhouses)
        # Важно: получаем и node_id, и zone_id узла для проверки соответствия
        for node_uid, gh_uid in node_gh_pairs:
            if gh_uid:
                # Резолв с учетом greenhouse (через zones)
                # Получаем node_id И zone_id узла для проверки соответствия
                # Сначала ищем ноду, привязанную к зоне в этом greenhouse
                node_rows = await fetch(
                    """
                    SELECT n.id, n.uid, n.zone_id
                    FROM nodes n
                    JOIN zones z ON z.id = n.zone_id
                    JOIN greenhouses g ON g.id = z.greenhouse_id
                    WHERE n.uid = $1 AND g.uid = $2
                    """,
                    node_uid,
                    gh_uid
                )
                if node_rows and len(node_rows) > 0:
                    node_id = node_rows[0]["id"]
                    node_zone_id = node_rows[0]["zone_id"]
                    node_uid_to_info[(node_uid, gh_uid)] = (node_id, node_zone_id)
                else:
                    # Если нода не найдена через зону, ищем ноду без привязки к зоне
                    # (нода может быть еще не привязана к зоне)
                    node_rows = await fetch(
                        """
                        SELECT n.id, n.uid, n.zone_id
                        FROM nodes n
                        WHERE n.uid = $1
                        """,
                        node_uid
                    )
                    if node_rows and len(node_rows) > 0:
                        node_id = node_rows[0]["id"]
                        node_zone_id = node_rows[0]["zone_id"]
                        node_uid_to_info[(node_uid, gh_uid)] = (node_id, node_zone_id)
                    else:
                        logger.warning(
                            f"Node not found: node_uid={node_uid}, gh_uid={gh_uid}",
                            extra={"node_uid": node_uid, "gh_uid": gh_uid}
                        )
            else:
                # Fallback: если gh_uid не указан, используем простое извлечение (для обратной совместимости)
                # Но это может привести к проблемам в многотепличной конфигурации
                logger.warning(
                    f"gh_uid not provided for node_uid={node_uid}, using simple node_id resolution (may cause conflicts in multi-greenhouse setup)",
                    extra={"node_uid": node_uid}
                )
                node_rows = await fetch(
                    """
                    SELECT id, uid, zone_id
                    FROM nodes
                    WHERE uid = $1
                    """,
                    node_uid,
                )
                if node_rows and len(node_rows) > 0:
                    node_id = node_rows[0]["id"]
                    node_zone_id = node_rows[0]["zone_id"]
                    node_uid_to_info[(node_uid, None)] = (node_id, node_zone_id)
    
    # Группируем по zone_id и metric_type для batch insert
    grouped: dict[tuple[int, str, Optional[int], Optional[str]], list[TelemetrySampleModel]] = {}
    
    for sample in samples:
        zone_id = None
        if sample.zone_uid:
            # Ищем zone_id с учетом gh_uid
            zone_id = zone_uid_to_id.get((sample.zone_uid, sample.gh_uid))
            # Fallback: если не найдено с gh_uid, пробуем без него (для обратной совместимости)
            if zone_id is None and sample.gh_uid:
                zone_id = zone_uid_to_id.get((sample.zone_uid, None))
        
        node_id = None
        node_zone_id = None  # zone_id, к которому привязан узел (для проверки соответствия)
        if sample.node_uid:
            # Ищем node_id с учетом gh_uid
            node_info = node_uid_to_info.get((sample.node_uid, sample.gh_uid))
            # Fallback: если не найдено с gh_uid, пробуем без него (для обратной совместимости)
            if node_info is None and sample.gh_uid:
                node_info = node_uid_to_info.get((sample.node_uid, None))
            
            if node_info:
                node_id, node_zone_id = node_info
        
        if not zone_id:
            # Логируем более детально для диагностики
            if not sample.zone_uid:
                logger.warning(
                    "Skipping sample: zone_uid missing",
                    extra={
                        "zone_uid": sample.zone_uid,
                        "node_uid": sample.node_uid,
                        "metric_type": sample.metric_type
                    }
                )
            else:
                # zone_uid есть, но zone_id не найден (возможно невалидный формат или не существует в БД)
                logger.warning(
                    "Skipping sample: zone_id not found for zone_uid",
                    extra={
                        "zone_uid": sample.zone_uid,
                        "node_uid": sample.node_uid,
                        "metric_type": sample.metric_type,
                        "zone_uid_format_valid": sample.zone_uid.startswith("zn-") if sample.zone_uid else False
                    }
                )
            TELEMETRY_DROPPED.labels(reason="zone_id_not_found").inc()
            continue
        
        # КРИТИЧЕСКАЯ ПРОВЕРКА БЕЗОПАСНОСТИ: проверяем соответствие node_id → zone_id
        # Предотвращает подмену данных зон через HTTP ingest с неправильным zone_id
        if node_id and node_zone_id is not None:
            if node_zone_id != zone_id:
                logger.warning(
                    "Security: node_uid does not belong to zone_id, dropping sample",
                    extra={
                        "node_uid": sample.node_uid,
                        "node_id": node_id,
                        "node_zone_id": node_zone_id,  # Реальная зона узла
                        "requested_zone_id": zone_id,  # Запрошенная зона из payload
                        "zone_uid": sample.zone_uid,
                        "gh_uid": sample.gh_uid,
                        "metric_type": sample.metric_type
                    }
                )
                TELEMETRY_DROPPED.labels(reason="node_zone_mismatch").inc()
                continue
        
        key = (zone_id, sample.metric_type, node_id, sample.channel)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(sample)
    
    # Batch insert в telemetry_samples
    # Считаем реально вставленные сэмплы (не пропущенные из-за отсутствия zone_id)
    processed_count = 0
    
    for (zone_id, metric_type, node_id, channel), group_samples in grouped.items():
        logger.info(f"[BROADCAST] Processing group: zone_id={zone_id}, node_id={node_id}, metric={metric_type}, samples={len(group_samples)}")
        # Используем TimescaleDB для эффективной вставки
        values_list = []
        params_list = []
        param_index = 1
        
        for sample in group_samples:
            ts = sample.ts or datetime.utcnow()
            value = sample.value
            
            # Добавляем ts в плейсхолдеры (6 параметров: zone_id, node_id, metric_type, channel, value, ts)
            values_list.append(
                f"(${param_index}, ${param_index + 1}, ${param_index + 2}, ${param_index + 3}, ${param_index + 4}, ${param_index + 5})"
            )
            # Добавляем ts в параметры
            params_list.extend([zone_id, node_id, metric_type, channel, value, ts])
            param_index += 6
        
        if values_list:
            query = f"""
                INSERT INTO telemetry_samples (zone_id, node_id, metric_type, channel, value, ts)
                VALUES {', '.join(values_list)}
            """
            try:
                await execute(query, *params_list)
                # Успешно вставлено - считаем все сэмплы из этой группы
                processed_count += len(group_samples)
                
                # Минимальное логирование: телеметрия записана
                logger.info(f"[TELEMETRY] Written: zone_id={zone_id}, node_id={node_id}, metric={metric_type}, count={len(group_samples)}")
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
                # При ошибке вставки сэмплы не считаются как обработанные
        
        # Обновляем telemetry_last
        # Выбираем сэмпл с максимальным ts (самый свежий), а не просто последний в батче
        # Это важно, так как телеметрия может приходить вне порядка (MQTT/очереди/ретраи)
        logger.info(f"[BROADCAST] Before upsert check: group_samples={len(group_samples) if group_samples else 0}, node_id={node_id}")
        if group_samples:
            # Находим сэмпл с максимальным ts
            latest_sample = max(
                group_samples,
                key=lambda s: s.ts if s.ts else datetime.min.replace(tzinfo=None)
            )
            await upsert_telemetry_last(
                zone_id,
                metric_type,
                node_id,
                channel,
                latest_sample.value
            )
            
            # Broadcast телеметрии через Laravel WebSocket для real-time обновления графиков.
            # Проверяем shutdown перед созданием задачи, чтобы не создавать задачи после начала shutdown.
            logger.info(f"[BROADCAST] After upsert: node_id={node_id}, shutdown={shutdown_event.is_set()}, group_samples={len(group_samples)}")
            if node_id and not shutdown_event.is_set():
                logger.info(f"[BROADCAST] Scheduling broadcast for node_id={node_id}, metric={metric_type}, value={latest_sample.value}")
                # Используем безопасное создание задачи с обработкой ошибок.
                # Не добавляем задачи в background_tasks, так как их очень много и они завершаются быстро.
                # Это fire-and-forget задачи для неблокирующей отправки broadcast.
                try:
                    task = asyncio.create_task(_broadcast_telemetry_to_laravel(
                        node_id=node_id,
                        channel=channel or '',
                        metric_type=metric_type,
                        value=latest_sample.value,
                        timestamp=latest_sample.ts or datetime.utcnow()
                    ))
                    # Добавляем callback для логирования критических ошибок (не exceptions, которые уже обработаны).
                    def log_task_error(t):
                        try:
                            if t.done() and t.exception():
                                exc = t.exception()
                                # Логируем только необработанные исключения (которые не были перехвачены в функции)
                                if not isinstance(exc, (httpx.TimeoutException, httpx.RequestError)):
                                    logger.warning(f"[BROADCAST] Unhandled exception in broadcast task: {exc}", exc_info=True)
                        except Exception:
                            pass  # Игнорируем ошибки при проверке задачи
                    task.add_done_callback(log_task_error)
                except RuntimeError as e:
                    # Event loop закрыт или недоступен - игнорируем, так как это нормально при shutdown
                    logger.debug(f"[BROADCAST] Cannot create task (event loop may be closed): {e}")
                except Exception as e:
                    logger.warning(f"[BROADCAST] Failed to create broadcast task: {e}", exc_info=True)
    
    processing_duration = time.time() - start_time
    TELEMETRY_PROCESSING_DURATION.observe(processing_duration)
    # Считаем метрики по реально вставленным сэмплам, а не по входному списку
    TELEM_PROCESSED.inc(processed_count)
    TELEM_BATCH_SIZE.observe(processed_count)


async def _broadcast_telemetry_to_laravel(
    node_id: int,
    channel: str,
    metric_type: str,
    value: float,
    timestamp: datetime
):
    """
    Вызывает Laravel API для broadcast телеметрии через WebSocket.
    Выполняется асинхронно в фоне, чтобы не блокировать основной процесс.
    """
    # Проверяем shutdown в начале функции, чтобы быстро выйти если shutdown начался.
    if shutdown_event.is_set():
        logger.debug("[BROADCAST] Shutdown in progress, skipping telemetry broadcast")
        return
    
    s = get_settings()
    laravel_url = s.laravel_api_url if hasattr(s, 'laravel_api_url') else None
    ingest_token = s.history_logger_api_token if hasattr(s, 'history_logger_api_token') and s.history_logger_api_token else (s.ingest_token if hasattr(s, 'ingest_token') and s.ingest_token else None)
    
    if not laravel_url:
        logger.warning("[BROADCAST] Laravel API URL not configured, skipping telemetry broadcast. Set LARAVEL_API_URL environment variable.")
        return
    
    if not ingest_token:
        logger.warning("[BROADCAST] Ingest token not configured, skipping telemetry broadcast. Set HISTORY_LOGGER_API_TOKEN or PY_INGEST_TOKEN environment variable.")
        return
    
    logger.info(f"[BROADCAST] Starting broadcast: node_id={node_id}, metric={metric_type}, url={laravel_url}")
    
    try:
        # Конвертируем timestamp в миллисекунды с правильной обработкой timezone.
        # datetime.utcnow() создает naive datetime, но timestamp() требует aware datetime.
        if isinstance(timestamp, datetime):
            # Если datetime naive (без timezone), считаем его UTC.
            if timestamp.tzinfo is None:
                # Используем UTC timezone для naive datetime.
                from datetime import timezone
                timestamp_utc = timestamp.replace(tzinfo=timezone.utc)
                timestamp_ms = int(timestamp_utc.timestamp() * 1000)
            else:
                timestamp_ms = int(timestamp.timestamp() * 1000)
        else:
            # Если это уже число (timestamp в секундах)
            timestamp_ms = int(timestamp * 1000)
        
        api_data = {
            'node_id': node_id,
            'channel': channel,
            'metric_type': metric_type,
            'value': value,
            'timestamp': timestamp_ms,
        }
        
        API_TIMEOUT = s.laravel_api_timeout_sec if hasattr(s, 'laravel_api_timeout_sec') else 5.0
        
        # Проверяем shutdown перед HTTP запросом, чтобы не делать запросы после shutdown.
        if shutdown_event.is_set():
            logger.debug("[BROADCAST] Shutdown in progress, skipping HTTP request")
            return
        
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            api_start = time.time()
            response = await client.post(
                f"{laravel_url}/api/python/broadcast/telemetry",
                json=api_data,
                headers={
                    'Authorization': f'Bearer {ingest_token}',
                    'Content-Type': 'application/json',
                }
            )
            api_duration = time.time() - api_start
            LARAVEL_API_DURATION.observe(api_duration)
            
            if response.status_code == 200:
                logger.info(f"[BROADCAST] Telemetry broadcasted successfully: node_id={node_id}, metric={metric_type}, value={value}")
            else:
                logger.warning(
                    f"[BROADCAST] Failed to broadcast telemetry: status={response.status_code}",
                    extra={
                        'node_id': node_id,
                        'metric_type': metric_type,
                        'status_code': response.status_code,
                        'response': response.text[:200]
                    }
                )
    except httpx.TimeoutException as e:
        logger.warning(f"[BROADCAST] Timeout broadcasting telemetry: {e}", extra={'node_id': node_id})
    except Exception as e:
        logger.warning(f"[BROADCAST] Error broadcasting telemetry: {e}", extra={'node_id': node_id}, exc_info=True)


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
            
            # Обновляем метрику возраста самого старого элемента в очереди
            queue_age_start_time = time.time()
            queue_age = await telemetry_queue.get_oldest_age_seconds()
            queue_age_duration = time.time() - queue_age_start_time
            REDIS_OPERATION_DURATION.observe(queue_age_duration)
            
            if queue_age is not None:
                TELEMETRY_QUEUE_AGE.set(queue_age)
            else:
                # Если очередь пуста или элементы не имеют enqueued_at, устанавливаем 0
                TELEMETRY_QUEUE_AGE.set(0.0)
            
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
                        # zone_id будет резолвлен в process_telemetry_batch с учетом gh_uid
                        sample = TelemetrySampleModel(
                            node_uid=item.node_uid,
                            zone_uid=item.zone_uid,
                            zone_id=None,  # Будет резолвлен в process_telemetry_batch с учетом gh_uid
                            gh_uid=getattr(item, 'gh_uid', None),  # Поддержка старых элементов без gh_uid
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
            # zone_id будет резолвлен в process_telemetry_batch с учетом gh_uid
            sample = TelemetrySampleModel(
                node_uid=item.node_uid,
                zone_uid=item.zone_uid,
                zone_id=None,  # Будет резолвлен в process_telemetry_batch с учетом gh_uid
                gh_uid=getattr(item, 'gh_uid', None),  # Поддержка старых элементов без gh_uid
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
    # Детальное логирование для диагностики
    logger.info(f"[NODE_HELLO] ===== START processing node_hello =====")
    logger.info(f"[NODE_HELLO] Topic: {topic}, payload length: {len(payload)}")
    
    try:
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
        logger.info(f"[NODE_HELLO] Full payload data: {data}")
        NODE_HELLO_RECEIVED.inc()
    except Exception as e:
        logger.error(f"[NODE_HELLO] Error parsing node_hello: {e}", exc_info=True)
        NODE_HELLO_ERRORS.labels(error_type="parse_error").inc()
        return
    
    s = get_settings()
    laravel_url = s.laravel_api_url if hasattr(s, 'laravel_api_url') else None
    # Используем ingest_token для регистрации нод (PY_INGEST_TOKEN или HISTORY_LOGGER_API_TOKEN)
    # Это соответствует требованиям NodeController::register
    ingest_token = s.history_logger_api_token if hasattr(s, 'history_logger_api_token') and s.history_logger_api_token else (s.ingest_token if hasattr(s, 'ingest_token') and s.ingest_token else None)
    
    if not laravel_url:
        logger.error("[NODE_HELLO] Laravel API URL not configured, cannot register node")
        NODE_HELLO_ERRORS.labels(error_type="config_missing").inc()
        return
    
    # В production токен обязателен
    app_env = os.getenv("APP_ENV", "").lower().strip()
    is_prod = app_env in ("production", "prod") and app_env != ""
    
    if is_prod and not ingest_token:
        logger.error("[NODE_HELLO] Ingest token (PY_INGEST_TOKEN or HISTORY_LOGGER_API_TOKEN) must be set in production for node registration")
        NODE_HELLO_ERRORS.labels(error_type="token_missing").inc()
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
        
        # Токен обязателен в production, в dev может быть опционален
        if ingest_token:
            headers["Authorization"] = f"Bearer {ingest_token}"
        elif is_prod:
            logger.error("[NODE_HELLO] Cannot register node without ingest token in production")
            NODE_HELLO_ERRORS.labels(error_type="token_missing").inc()
            return
        else:
            logger.warning(f"[NODE_HELLO] No ingest token configured, registering without auth (dev mode only)")
        
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
    # Детальное логирование для диагностики
    logger.info(f"[HEARTBEAT] ===== START processing heartbeat =====")
    logger.info(f"[HEARTBEAT] Topic: {topic}, payload length: {len(payload)}")
    
    data = _parse_json(payload)
    if not data or not isinstance(data, dict):
        logger.warning(f"[HEARTBEAT] Invalid JSON in heartbeat from topic {topic}")
        return
    
    node_uid = _extract_node_uid(topic)
    if not node_uid:
        logger.warning(f"[HEARTBEAT] Could not extract node_uid from topic {topic}")
        return
    
    logger.info(f"[HEARTBEAT] Processing heartbeat for node_uid: {node_uid}, data: {data}")
    
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
            # Прошивки отправляют uptime в миллисекундах (esp_timer_get_time() / 1000)
            # Конвертируем в секунды для поля uptime_seconds
            uptime_ms = float(uptime)
            uptime_seconds = int(uptime_ms / 1000.0)
            updates.append(f"uptime_seconds=${param_index + 1}")
            params.append(uptime_seconds)
            param_index += 1
        except (ValueError, TypeError) as e:
            logger.warning(
                f"Invalid uptime value: {uptime}",
                extra={"error": str(e), "node_uid": node_uid}
            )
    
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
    
    # Всегда обновляем timestamp полей и status=online (безопасно, так как не содержат пользовательского ввода)
    updates.append("last_heartbeat_at=NOW()")
    updates.append("updated_at=NOW()")
    updates.append("last_seen_at=NOW()")
    updates.append("status='online'")  # Узел онлайн, если отправляет heartbeat
    
    # Строим запрос с использованием только разрешенных полей
    if len(updates) > 4:  # Есть хотя бы одно обновляемое поле кроме timestamp и status
        query = f"UPDATE nodes SET {', '.join(updates)} WHERE uid=$1"
        await execute(query, *params)
    else:
        # Только timestamp и status обновления
        await execute(
            "UPDATE nodes SET last_heartbeat_at=NOW(), updated_at=NOW(), last_seen_at=NOW(), status='online' WHERE uid=$1",
            node_uid
        )
    
    HEARTBEAT_RECEIVED.labels(node_uid=node_uid).inc()
    
    # Вычисляем uptime_seconds для логирования (если uptime был обработан)
    logged_uptime = None
    if uptime is not None:
        try:
            uptime_ms = float(uptime)
            logged_uptime = int(uptime_ms / 1000.0)
        except (ValueError, TypeError):
            logged_uptime = uptime  # Оставляем оригинальное значение если не удалось конвертировать
    
    logger.info(
        f"[HEARTBEAT] Node heartbeat processed successfully: node_uid={node_uid}, "
        f"uptime_seconds={logged_uptime}, free_heap={free_heap}, rssi={rssi}"
    )


async def handle_config_response(topic: str, payload: bytes):
    """
    Обработчик config_response сообщений от узлов ESP32.
    Переводит ноду в ASSIGNED_TO_ZONE после успешной установки конфига.
    """
    try:
        logger.info(f"[CONFIG_RESPONSE] Received message on topic {topic}, payload length: {len(payload)}")
        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[CONFIG_RESPONSE] Invalid JSON in config_response from topic {topic}")
            CONFIG_RESPONSE_ERROR.labels(node_uid="unknown").inc()
            return
        
        node_uid = _extract_node_uid(topic)
        if not node_uid:
            logger.warning(f"[CONFIG_RESPONSE] Could not extract node_uid from topic {topic}")
            CONFIG_RESPONSE_ERROR.labels(node_uid="unknown").inc()
            return
        
        CONFIG_RESPONSE_RECEIVED.inc()
        
        status = data.get("status", "").upper()
        cmd_id = data.get("cmd_id")  # ID команды для проверки соответствия
        config_version = data.get("config_version")  # Версия конфига для проверки свежести
        
        # Ожидаем только "ACK" от прошивок
        if status == "ACK":
            # КРИТИЧЕСКАЯ ПРОВЕРКА БЕЗОПАСНОСТИ: проверяем cmd_id и свежесть конфига
            # Предотвращает подмену ACK от старых/чужих команд
            validation_passed = True
            validation_errors = []
            
            # Получаем информацию о ноде и последнем конфиге
            try:
                # Получаем hardware_id для очистки retained сообщения на временном топике после привязки
        node_rows = await fetch(
            """
            SELECT n.id,
                   n.uid,
                   n.lifecycle_state,
                   n.zone_id,
                   n.pending_zone_id,
                   n.config,
                   n.hardware_id,
                   z.uid AS zone_uid,
                   gh.uid AS gh_uid
            FROM nodes n
            LEFT JOIN zones z ON z.id = n.zone_id
            LEFT JOIN greenhouses gh ON gh.id = z.greenhouse_id
            WHERE n.uid = $1
            """,
            node_uid
        )
                
                if not node_rows or len(node_rows) == 0:
                    logger.warning(f"[CONFIG_RESPONSE] Node {node_uid} not found in database, ignoring ACK")
                    CONFIG_RESPONSE_ERROR.labels(node_uid=node_uid).inc()
                    return
                
                node = node_rows[0]
                node_config = node.get("config") or {}
                
                # Проверяем cmd_id если он указан в payload
                if cmd_id:
                    last_cmd_id = node_config.get("last_cmd_id")
                    if last_cmd_id and last_cmd_id != cmd_id:
                        validation_passed = False
                        validation_errors.append(f"cmd_id mismatch: expected {last_cmd_id}, got {cmd_id}")
                
                # Проверяем версию конфига если она указана
                if config_version is not None:
                    stored_config_version = node_config.get("version")
                    if stored_config_version is not None and stored_config_version != config_version:
                        validation_passed = False
                        validation_errors.append(f"config_version mismatch: expected {stored_config_version}, got {config_version}")
                
                if not validation_passed:
                    logger.warning(
                        f"[CONFIG_RESPONSE] ACK validation failed for node {node_uid}: {', '.join(validation_errors)}. "
                        f"Ignoring potentially stale or mismatched ACK."
                    )
                    CONFIG_RESPONSE_ERROR.labels(node_uid=node_uid).inc()
                    return
                
            except Exception as validation_e:
                logger.error(
                    f"[CONFIG_RESPONSE] Error validating ACK for node {node_uid}: {validation_e}",
                    exc_info=True
                )
                # В случае ошибки валидации лучше не доверять ACK
                CONFIG_RESPONSE_ERROR.labels(node_uid=node_uid).inc()
                return
            
            # Успешная установка конфига - переводим ноду в ASSIGNED_TO_ZONE
            logger.info(
                f"[CONFIG_RESPONSE] Config successfully installed for node {node_uid} "
                f"(cmd_id={cmd_id}, config_version={config_version})"
            )
            CONFIG_RESPONSE_SUCCESS.labels(node_uid=node_uid).inc()
            
            # Вызываем Laravel API для перевода ноды в ASSIGNED_TO_ZONE
            s = get_settings()
            laravel_url = s.laravel_api_url if hasattr(s, 'laravel_api_url') else None
            # Используем тот же токен, что и для регистрации нод (history_logger_api_token или ingest_token)
            ingest_token = s.history_logger_api_token if hasattr(s, 'history_logger_api_token') and s.history_logger_api_token else (s.ingest_token if hasattr(s, 'ingest_token') and s.ingest_token else None)
            
            if not laravel_url:
                logger.error("[CONFIG_RESPONSE] Laravel API URL not configured, cannot update node lifecycle")
                return
            
            try:
                # Получаем информацию о ноде
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }
                if ingest_token:
                    headers["Authorization"] = f"Bearer {ingest_token}"
                
                # Получаем информацию о ноде через БД напрямую (уже получено при валидации)
                # Используем данные из предыдущего запроса
                node_id = node.get("id")
                lifecycle_state = node.get("lifecycle_state")
                zone_id = node.get("zone_id")
                pending_zone_id = node.get("pending_zone_id")
                
                # Переводим в ASSIGNED_TO_ZONE только если:
                # 1. Нода в состоянии REGISTERED_BACKEND
                # 2. Нода привязана к зоне (zone_id не null) ИЛИ есть pending_zone_id
                target_zone_id = zone_id or pending_zone_id
                if lifecycle_state == "REGISTERED_BACKEND" and target_zone_id:
                    logger.info(
                        f"[CONFIG_RESPONSE] Preparing node {node_uid} (id={node_id}) transition to ASSIGNED_TO_ZONE "
                        f"after successful config installation"
                    )
                    
                    # ВАЖНО: Если есть pending_zone_id, СНАЧАЛА обновляем zone_id, ЗАТЕМ делаем transition
                    if pending_zone_id and not zone_id:
                        logger.info(f"[CONFIG_RESPONSE] Step 1/2: Updating zone_id from pending_zone_id={pending_zone_id}")
                        # Обновляем zone_id из pending_zone_id через service endpoint
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            update_response = await client.patch(
                                f"{laravel_url}/api/nodes/{node_id}/service-update",
                                headers=headers,
                                json={
                                    "zone_id": pending_zone_id,
                                    "pending_zone_id": None  # Очищаем pending_zone_id
                                }
                            )
                            
                            if update_response.status_code == 200:
                                logger.info(
                                    f"[CONFIG_RESPONSE] Step 1/2 SUCCESS: Node {node_uid} (id={node_id}) zone_id updated from pending_zone_id={pending_zone_id}"
                                )
                                # Обновляем zone_id для дальнейшей проверки
                                zone_id = pending_zone_id
                                
                                # Очищаем retained сообщение на временном топике после успешной привязки.
                                # Это предотвращает автоматическую доставку конфига при переподключении.
                                # Используем node.get() для получения hardware_id из результата запроса к БД.
                                hardware_id = node.get("hardware_id")
                                if hardware_id:
                                    temp_topic = f"hydro/gh-temp/zn-temp/{hardware_id}/config"
                                    logger.info(f"[CONFIG_RESPONSE] Clearing retained message on temp topic: {temp_topic}")
                                    try:
                                        mqtt = await get_mqtt_client()
                                        base_client = mqtt._client
                                        # Публикуем пустое сообщение с retain=True для очистки retained сообщения
                                        result = base_client._client.publish(temp_topic, "", qos=1, retain=True)
                                        if result.rc == 0:
                                            logger.info(f"[CONFIG_RESPONSE] Retained message cleared on temp topic: {temp_topic}")
                                        else:
                                            logger.warning(f"[CONFIG_RESPONSE] Failed to clear retained message on temp topic {temp_topic}: rc={result.rc}")
                                    except Exception as clear_err:
                                        logger.warning(f"[CONFIG_RESPONSE] Error clearing retained message on temp topic {temp_topic}: {clear_err}")
                                
                            else:
                                logger.warning(
                                    f"[CONFIG_RESPONSE] Step 1/2 FAILED: Failed to update zone_id for node {node_uid} (id={node_id}): "
                                    f"{update_response.status_code} {update_response.text}"
                                )
                                # Если не удалось обновить zone_id, не переводим в ASSIGNED_TO_ZONE
                                return

                    # Очищаем retained на основном топике конфига, чтобы не слать конфиг заново при переподключениях
                    gh_uid = node_config.get("gh_uid") or node.get("gh_uid")
                    zone_segment = node_config.get("zone_uid") or (f"zn-{zone_id}" if zone_id else None)
                    if gh_uid and zone_segment:
                        main_topic = f"hydro/{gh_uid}/{zone_segment}/{node_uid}/config"
                        logger.info(f"[CONFIG_RESPONSE] Clearing retained message on main config topic: {main_topic}")
                        try:
                            mqtt = await get_mqtt_client()
                            base_client = mqtt._client
                            result = base_client._client.publish(main_topic, "", qos=1, retain=True)
                            if result.rc == 0:
                                logger.info(f"[CONFIG_RESPONSE] Retained message cleared on main topic: {main_topic}")
                            else:
                                logger.warning(f"[CONFIG_RESPONSE] Failed to clear retained message on main topic {main_topic}: rc={result.rc}")
                        except Exception as clear_err:
                            logger.warning(f"[CONFIG_RESPONSE] Error clearing retained message on main topic {main_topic}: {clear_err}")
                    
                    # Step 2: Переводим через service lifecycle API
                    logger.info(f"[CONFIG_RESPONSE] Step 2/2: Transitioning to ASSIGNED_TO_ZONE")
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        transition_response = await client.post(
                            f"{laravel_url}/api/nodes/{node_id}/lifecycle/service-transition",
                            headers=headers,
                            json={
                                "target_state": "ASSIGNED_TO_ZONE",
                                "reason": "Config successfully installed and confirmed by node"
                            }
                        )
                        
                        if transition_response.status_code == 200:
                            logger.info(
                                f"[CONFIG_RESPONSE] Node {node_uid} (id={node_id}) successfully transitioned to ASSIGNED_TO_ZONE"
                            )
                            CONFIG_RESPONSE_PROCESSED.inc()
                        elif transition_response.status_code == 404:
                            logger.warning(
                                f"[CONFIG_RESPONSE] Node {node_uid} (id={node_id}) not found during transition - "
                                f"node may have been deleted"
                            )
                        elif transition_response.status_code == 400:
                            # Возможно, нода уже в другом состоянии или zone_id был удален
                            # Проверяем текущее состояние ноды
                            try:
                                check_rows = await fetch(
                                    """
                                    SELECT id, uid, lifecycle_state, zone_id
                                    FROM nodes
                                    WHERE uid = $1
                                    """,
                                    node_uid
                                )
                                if check_rows and len(check_rows) > 0:
                                    check_node = check_rows[0]
                                    logger.warning(
                                        f"[CONFIG_RESPONSE] Transition failed for node {node_uid}: "
                                        f"current_state={check_node.get('lifecycle_state')}, "
                                        f"zone_id={check_node.get('zone_id')}, "
                                        f"response={transition_response.text}"
                                    )
                                else:
                                    logger.warning(
                                        f"[CONFIG_RESPONSE] Node {node_uid} not found after transition failure"
                                    )
                            except Exception as check_e:
                                logger.error(
                                    f"[CONFIG_RESPONSE] Error checking node state after transition failure: {check_e}"
                                )
                            logger.error(
                                f"[CONFIG_RESPONSE] Failed to transition node {node_uid} (id={node_id}) to ASSIGNED_TO_ZONE: "
                                f"{transition_response.status_code} {transition_response.text}"
                            )
                        else:
                            logger.error(
                                f"[CONFIG_RESPONSE] Failed to transition node {node_uid} (id={node_id}) to ASSIGNED_TO_ZONE: "
                                f"{transition_response.status_code} {transition_response.text}"
                            )
                elif lifecycle_state == "ASSIGNED_TO_ZONE":
                    # Нода уже в ASSIGNED_TO_ZONE - возможно, это повторный config_response
                    # (например, при повторной публикации конфига)
                    logger.debug(
                        f"[CONFIG_RESPONSE] Node {node_uid} already in ASSIGNED_TO_ZONE, "
                        f"skipping transition (may be duplicate config_response)"
                    )
                else:
                    logger.debug(
                        f"[CONFIG_RESPONSE] Node {node_uid} not in REGISTERED_BACKEND or not assigned to zone, "
                        f"skipping transition. lifecycle_state={lifecycle_state}, zone_id={zone_id}"
                    )
            except Exception as e:
                logger.error(
                    f"[CONFIG_RESPONSE] Error processing config_response for node {node_uid}: {e}",
                    exc_info=True
                )
        elif status == "ERROR":
            # Ошибка установки конфига
            error_msg = data.get("error", "Unknown error")
            logger.warning(
                f"[CONFIG_RESPONSE] Config installation failed for node {node_uid}: {error_msg}"
            )
            CONFIG_RESPONSE_ERROR.labels(node_uid=node_uid).inc()
        else:
            logger.warning(
                f"[CONFIG_RESPONSE] Unknown status in config_response from node {node_uid}: {status}"
            )
            CONFIG_RESPONSE_ERROR.labels(node_uid=node_uid).inc()
            
    except Exception as e:
        logger.error(f"[CONFIG_RESPONSE] Unexpected error processing config_response: {e}", exc_info=True)
        CONFIG_RESPONSE_ERROR.labels(node_uid="unknown").inc()


def extract_zone_id_from_uid(zone_uid: Optional[str]) -> Optional[int]:
    """
    Извлечь zone_id из zone_uid (формат: zn-{id} или zone-{uid}).
    
    Args:
        zone_uid: zone_uid в формате "zn-{id}" или "zone-{uid}" или None
        
    Returns:
        zone_id как int или None если формат неверный
    """
    if not zone_uid:
        return None
    
    # Поддержка формата zn-{id} (числовой ID)
    if zone_uid.startswith("zn-"):
        try:
            return int(zone_uid.split("-")[1])
        except (ValueError, IndexError):
            return None
    
    # Формат zone-{uid} не является числовым ID, возвращаем None
    # (будет искаться по UID в БД)
    return None


def _extract_zone_id(topic: str) -> Optional[int]:
    """Извлечь zone_id (int) из топика (для обратной совместимости)."""
    # Формат: hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/telemetry
    # или: hydro/{gh_uid}/zn-{zone_id}/{node_uid}/{channel}/telemetry
    parts = topic.split("/")
    if len(parts) >= 3:
        zone_part = parts[2]
        return extract_zone_id_from_uid(zone_part)
    return None


def _extract_zone_uid(topic: str) -> Optional[str]:
    """Извлечь zone_uid из топика."""
    # Формат: hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/telemetry
    parts = topic.split("/")
    if len(parts) >= 3:
        return parts[2]
    return None


def _extract_node_uid(topic: str) -> Optional[str]:
    """Извлечь node_uid из топика."""
    # Формат: hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/telemetry
    parts = topic.split("/")
    if len(parts) >= 4:
        return parts[3]
    return None


def _extract_gh_uid(topic: str) -> Optional[str]:
    """Извлечь gh_uid (greenhouse UID) из топика."""
    # Формат: hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/telemetry
    parts = topic.split("/")
    if len(parts) >= 2:
        return parts[1]
    return None


def _extract_channel_from_topic(topic: str) -> Optional[str]:
    """Извлечь channel из топика телеметрии."""
    # Формат: hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/telemetry
    parts = topic.split("/")
    if len(parts) >= 5:
        return parts[4]
    return None


# Startup и shutdown события теперь обрабатываются через lifespan handler выше


def _auth_ingest(request: Request):
    """
    Проверка токена аутентификации для HTTP ingest endpoint.
    Использует HISTORY_LOGGER_API_TOKEN или PY_INGEST_TOKEN (через get_settings).
    В production токен обязателен всегда.
    """
    s = get_settings()
    
    # Проверяем окружение
    app_env = os.getenv("APP_ENV", "").lower().strip()
    is_prod = app_env in ("production", "prod") and app_env != ""
    
    # В production токен обязателен всегда
    if is_prod:
        if not s.history_logger_api_token:
            logger.error("HISTORY_LOGGER_API_TOKEN or PY_INGEST_TOKEN must be set in production environment")
            INGEST_AUTH_FAILED.inc()
            raise HTTPException(
                status_code=500,
                detail="Server configuration error: ingest token not configured"
            )
        
        token = request.headers.get("Authorization", "")
        expected_token = f"Bearer {s.history_logger_api_token}"
        
        if token != expected_token:
            client_ip = request.client.host if request.client else "unknown"
            logger.warning(
                f"Invalid or missing token for HTTP ingest in production: token_present={bool(token)}, "
                f"client_ip={client_ip}"
            )
            INGEST_AUTH_FAILED.inc()
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: token required in production"
            )
        return


async def handle_command_response(topic: str, payload: bytes):
    """
    Обработчик command_response сообщений от узлов.
    Обновляет статус команды через Laravel API, чтобы фронт получил уведомление (CommandFailed/CommandStatusUpdated).
    """
    try:
        logger.info(f"[COMMAND_RESPONSE] Received message on topic {topic}, payload length: {len(payload)}")
        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[COMMAND_RESPONSE] Invalid JSON in command_response from topic {topic}")
            COMMAND_RESPONSE_ERROR.inc()
            return

        cmd_id = data.get("cmd_id")
        raw_status = str(data.get("status", "")).upper()
        node_uid = _extract_node_uid(topic)
        channel = _extract_channel_from_topic(topic)
        gh_uid = _extract_gh_uid(topic)

        if not cmd_id or not raw_status:
            logger.warning(f"[COMMAND_RESPONSE] Missing cmd_id or status in payload: {data}")
            COMMAND_RESPONSE_ERROR.inc()
            return

        # Маппинг статусов прошивки -> статус в Laravel
        if raw_status in ("ACK", "ACCEPTED"):
            mapped_status = "accepted"
        elif raw_status in ("COMPLETED", "OK", "SUCCESS", "DONE"):
            mapped_status = "completed"
        elif raw_status in ("ERROR", "FAILED"):
            mapped_status = "failed"
        else:
            logger.warning(f"[COMMAND_RESPONSE] Unknown status '{raw_status}' for cmd_id={cmd_id}")
            COMMAND_RESPONSE_ERROR.inc()
            return

        COMMAND_RESPONSE_RECEIVED.inc()

        s = get_settings()
        laravel_url = s.laravel_api_url if hasattr(s, 'laravel_api_url') else None
        ingest_token = s.history_logger_api_token if hasattr(s, 'history_logger_api_token') and s.history_logger_api_token else (s.ingest_token if hasattr(s, 'ingest_token') and s.ingest_token else None)

        if not laravel_url:
            logger.error("[COMMAND_RESPONSE] Laravel API URL not configured, cannot update command status")
            COMMAND_RESPONSE_ERROR.inc()
            return

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if ingest_token:
            headers["Authorization"] = f"Bearer {ingest_token}"

        details = {
            "error_code": data.get("error_code"),
            "error_message": data.get("error_message"),
            "raw_status": raw_status,
            "node_uid": node_uid,
            "channel": channel,
            "gh_uid": gh_uid,
        }
        # Убираем None значения
        details = {k: v for k, v in details.items() if v is not None}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{laravel_url}/api/python/commands/ack",
                    headers=headers,
                    json={
                        "cmd_id": cmd_id,
                        "status": mapped_status,
                        "details": details or None,
                    },
                )

            if resp.status_code != 200:
                logger.warning(f"[COMMAND_RESPONSE] Laravel responded with {resp.status_code}: {resp.text[:200]}")
                COMMAND_RESPONSE_ERROR.inc()
            else:
                logger.info(
                    f"[COMMAND_RESPONSE] Status '{mapped_status}' pushed to Laravel for cmd_id={cmd_id}, node_uid={node_uid}, channel={channel}"
                )
        except Exception as e:
            logger.error(f"[COMMAND_RESPONSE] Error sending status to Laravel: {e}", exc_info=True)
            COMMAND_RESPONSE_ERROR.inc()
    except Exception as e:
        logger.error(f"[COMMAND_RESPONSE] Unexpected error processing message: {e}", exc_info=True)
        COMMAND_RESPONSE_ERROR.inc()
    # В dev окружении: если токен настроен, он обязателен
    if s.history_logger_api_token:
        token = request.headers.get("Authorization", "")
        expected_token = f"Bearer {s.history_logger_api_token}"
        
        if token != expected_token:
            client_ip = request.client.host if request.client else "unknown"
            logger.warning(
                f"Invalid or missing token for HTTP ingest: token_present={bool(token)}, "
                f"client_ip={client_ip}"
            )
            INGEST_AUTH_FAILED.inc()
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: invalid or missing token"
            )
        return
    
    # Dev окружение без токена: разрешаем только localhost
    client_ip = request.client.host if request.client else ""
    is_localhost = client_ip in ["127.0.0.1", "::1", "localhost"]
    
    if not is_localhost:
        logger.warning(
            f"Rejecting non-localhost request without token: client_ip={client_ip}. "
            f"Token is required in production. Set HISTORY_LOGGER_API_TOKEN or PY_INGEST_TOKEN environment variable."
        )
        INGEST_AUTH_FAILED.inc()
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: token required. Set HISTORY_LOGGER_API_TOKEN or PY_INGEST_TOKEN environment variable."
        )
    
    logger.debug(f"Allowing localhost request without token (dev mode): client_ip={client_ip}")


def _check_rate_limit(client_id: str) -> bool:
    """
    Проверка rate limit для клиента.
    
    Args:
        client_id: Идентификатор клиента (IP адрес)
        
    Returns:
        True если запрос разрешен, False если превышен лимит
    """
    current_time = time.time()
    
    # Очищаем старые записи (старше окна)
    window_start = current_time - INGEST_RATE_LIMIT_WINDOW_SEC
    _ingest_rate_limiter[client_id] = [
        ts for ts in _ingest_rate_limiter[client_id] if ts > window_start
    ]
    
    # Проверяем лимит
    if len(_ingest_rate_limiter[client_id]) >= INGEST_RATE_LIMIT_REQUESTS:
        return False
    
    # Добавляем текущий запрос
    _ingest_rate_limiter[client_id].append(current_time)
    return True


async def publish_node_config_mqtt(
    mqtt_client: AsyncMqttClient,
    gh_uid: str,
    zone_id: int,
    node_uid: str,
    config: Dict[str, Any],
    hardware_id: Optional[str] = None
):
    """
    Публиковать NodeConfig в MQTT.
    
    Топик: hydro/{gh_uid}/{zone_segment}/{node_uid}/config
    QoS: 1
    Retain: true (чтобы узел получил конфигурацию при подписке)
    
    Также публикуем на временный топик (gh-temp/zn-temp/{hardware_id}/config), 
    если узел еще не получил конфигурацию и подписан на временные идентификаторы.
    Используем hardware_id для временного топика, чтобы избежать конфликтов при одинаковом node_uid.
    """
    try:
        # Проверяем подключение
        if not mqtt_client.is_connected():
            logger.warning("MQTT client not connected, attempting to reconnect...")
            await mqtt_client.start()
            if not mqtt_client.is_connected():
                raise ConnectionError("MQTT client is not connected and reconnection failed")
        
        s = get_settings()
        zone_segment = f"zn-{zone_id}"  # id by default
        if hasattr(s, 'mqtt_zone_format') and s.mqtt_zone_format == "uid" and config.get("zone_uid"):
            zone_segment = config["zone_uid"]
        
        # Публикуем на правильный топик с retain=true
        topic = f"hydro/{gh_uid}/{zone_segment}/{node_uid}/config"
        logger.info(f"Publishing config to topic: {topic}, node_uid: {node_uid}, zone_id: {zone_id}")
        
        # Используем базовый MQTT клиент для публикации
        base_client = mqtt_client._client
        import json as json_lib
        config_json = json_lib.dumps(config, separators=(",", ":"))
        result = base_client._client.publish(topic, config_json, qos=1, retain=True)
        if result.rc != 0:
            raise RuntimeError(f"MQTT publish failed with rc={result.rc} for topic {topic}")
        logger.info(f"[PUBLISH_CONFIG_MQTT] Config published successfully to {topic}")
        
        # Публикуем на временный топик ТОЛЬКО при привязке узла (когда hardware_id передан).
        # Если hardware_id не передан, узел уже привязан и временный топик больше не нужен.
        # После успешной привязки retained сообщения на временных топиках должны быть очищены.
        if hardware_id:
            temp_topic = f"hydro/gh-temp/zn-temp/{hardware_id}/config"
            logger.info(f"[PUBLISH_CONFIG_MQTT] Publishing config to temp topic: {temp_topic} (node binding in progress, using hardware_id)")
            result = base_client._client.publish(temp_topic, config_json, qos=1, retain=True)
            if result.rc != 0:
                logger.error(f"[PUBLISH_CONFIG_MQTT] MQTT publish failed with rc={result.rc} for temp topic {temp_topic}")
                raise RuntimeError(f"MQTT publish failed with rc={result.rc} for topic {temp_topic}")
            logger.info(f"[PUBLISH_CONFIG_MQTT] Config published successfully to {temp_topic}")
        else:
            # hardware_id не передан - это значит узел уже привязан
            # НЕ публикуем на временный топик, так как узел больше не должен получать конфиги на временные топики
            logger.info(f"[PUBLISH_CONFIG_MQTT] Skipping temp topic publish: node already bound (hardware_id not provided)")
    except Exception as e:
        logger.error(f"[PUBLISH_CONFIG_MQTT] Error publishing config for node {node_uid}: {e}", exc_info=True)
        raise


class NodeConfigRequest(BaseModel):
    """Request model for publishing node config."""
    node_uid: str = Field(..., min_length=1, max_length=128)
    hardware_id: Optional[str] = Field(None, max_length=128)  # Для временного топика
    zone_id: Optional[int] = Field(None, ge=1)
    greenhouse_uid: Optional[str] = Field(None, max_length=128)
    config: Dict[str, Any]  # Конфиг как dict


@app.post("/nodes/{node_uid}/config")
async def publish_node_config(
    request: Request,
    node_uid: str,
    req: NodeConfigRequest = Body(...),
):
    """
    Публиковать NodeConfig в MQTT через history-logger.
    Все общение бэка с нодами должно происходить через history-logger.
    """
    # Детальное логирование входящего запроса
    logger.info(f"[PUBLISH_CONFIG] ===== START processing config publish request =====")
    logger.info(f"[PUBLISH_CONFIG] Node UID: {node_uid}")
    logger.info(f"[PUBLISH_CONFIG] Request data: zone_id={req.zone_id}, greenhouse_uid={req.greenhouse_uid}, hardware_id={req.hardware_id}")
    logger.info(f"[PUBLISH_CONFIG] Config keys: {list(req.config.keys()) if req.config else 'empty'}")
    
    # Аутентификация (используем тот же механизм, что и для ingest)
    _auth_ingest(request)
    
    logger.info(f"[PUBLISH_CONFIG] Authentication passed for node: {node_uid}")
    
    # Получаем zone_id и gh_uid из запроса или из БД
    zone_id = req.zone_id
    gh_uid = req.greenhouse_uid
    
    # Если не указаны, пытаемся получить из БД
    if not zone_id or not gh_uid:
        rows = await fetch(
            """
            SELECT n.zone_id, g.uid as gh_uid
            FROM nodes n
            LEFT JOIN zones z ON n.zone_id = z.id
            LEFT JOIN greenhouses g ON z.greenhouse_id = g.id
            WHERE n.uid = $1
            """,
            node_uid,
        )
        if rows and len(rows) > 0:
            if not zone_id:
                zone_id = rows[0].get("zone_id")
            if not gh_uid:
                gh_uid = rows[0].get("gh_uid")
    
    if not zone_id:
        raise HTTPException(status_code=400, detail="zone_id is required (node must be assigned to a zone)")
    if not gh_uid:
        raise HTTPException(status_code=400, detail="greenhouse_uid is required (zone must have a greenhouse)")
    
    # Получаем MQTT клиент
    mqtt = await get_mqtt_client()
    
    logger.info(f"[PUBLISH_CONFIG] MQTT client obtained, is_connected: {mqtt.is_connected()}")
    
    try:
        logger.info(f"[PUBLISH_CONFIG] Publishing config for node {node_uid}, zone_id: {zone_id}, gh_uid: {gh_uid}, hardware_id: {req.hardware_id}")
        await publish_node_config_mqtt(
            mqtt,
            gh_uid,
            zone_id,
            node_uid,
            req.config,
            hardware_id=req.hardware_id
        )
        logger.info(f"[PUBLISH_CONFIG] Config published successfully for node {node_uid}")
        return {"status": "ok", "data": {"published": True, "topic": f"hydro/{gh_uid}/zn-{zone_id}/{node_uid}/config"}}
    except Exception as e:
        logger.error(f"[PUBLISH_CONFIG] Failed to publish config for node {node_uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to publish config: {str(e)}")


async def publish_command_mqtt(
    mqtt_client: AsyncMqttClient,
    gh_uid: str,
    zone_id: int,
    node_uid: str,
    channel: str,
    payload: Dict[str, Any],
    hardware_id: Optional[str] = None,
    zone_uid: Optional[str] = None
):
    """
    Публиковать команду в MQTT.
    
    Топик: hydro/{gh_uid}/{zone_segment}/{node_uid}/{channel}/command
    QoS: 1
    Retain: false
    
    Также публикуем на временный топик (gh-temp/zn-temp/{hardware_id}/{channel}/command),
    если узел еще не получил конфигурацию и подписан на временные идентификаторы.
    Используем hardware_id для временного топика, чтобы избежать конфликтов при одинаковом node_uid.
    """
    try:
        # Проверяем подключение
        if not mqtt_client.is_connected():
            logger.warning("MQTT client not connected, attempting to reconnect...")
            await mqtt_client.start()
            if not mqtt_client.is_connected():
                raise ConnectionError("MQTT client is not connected and reconnection failed")
        
        s = get_settings()
        zone_segment = f"zn-{zone_id}"  # id by default
        if hasattr(s, 'mqtt_zone_format') and s.mqtt_zone_format == "uid" and zone_uid:
            zone_segment = zone_uid
        elif hasattr(s, 'mqtt_zone_format') and s.mqtt_zone_format == "uid":
            logger.warning(f"mqtt_zone_format=uid but zone_uid not provided, using zn-{zone_id} (may cause mismatch with node subscription)")
        
        # Публикуем на правильный топик
        topic = f"hydro/{gh_uid}/{zone_segment}/{node_uid}/{channel}/command"
        logger.info(f"Publishing command to topic: {topic}, node_uid: {node_uid}, channel: {channel}, zone_id: {zone_id}, zone_segment: {zone_segment}")
        
        # Используем базовый MQTT клиент для публикации
        base_client = mqtt_client._client
        import json as json_lib
        command_json = json_lib.dumps(payload, separators=(",", ":"))
        result = base_client._client.publish(topic, command_json, qos=1, retain=False)
        if result.rc != 0:
            raise RuntimeError(f"MQTT publish failed with rc={result.rc} for topic {topic}")
        logger.info(f"Command published successfully to {topic}")
        
        # Также публикуем на временный топик для узлов, которые еще не получили конфигурацию
        # Узел может быть подписан на временные идентификаторы до получения первой конфигурации
        # Используем hardware_id для временного топика, чтобы избежать конфликтов при одинаковом node_uid
        if hardware_id:
            temp_topic = f"hydro/gh-temp/zn-temp/{hardware_id}/{channel}/command"
            logger.info(f"Publishing command to temp topic: {temp_topic} (using hardware_id)")
            result = base_client._client.publish(temp_topic, command_json, qos=1, retain=False)
            if result.rc != 0:
                raise RuntimeError(f"MQTT publish failed with rc={result.rc} for topic {temp_topic}")
            logger.info(f"Command published successfully to {temp_topic}")
        else:
            # Fallback: используем node_uid, если hardware_id не указан (для обратной совместимости)
            temp_topic = f"hydro/gh-temp/zn-temp/{node_uid}/{channel}/command"
            logger.warning(f"hardware_id not provided, using node_uid for temp topic: {temp_topic} (may cause conflicts)")
            result = base_client._client.publish(temp_topic, command_json, qos=1, retain=False)
            if result.rc != 0:
                raise RuntimeError(f"MQTT publish failed with rc={result.rc} for topic {temp_topic}")
            logger.info(f"Command published successfully to {temp_topic}")
    except Exception as e:
        logger.error(f"Error publishing command for node {node_uid}: {e}", exc_info=True)
        raise


class CommandRequest(BaseModel):
    """Request model for publishing commands."""
    type: str = Field(..., max_length=64, description="Command type")
    params: Dict[str, Any] = Field(default_factory=dict, description="Command parameters")
    node_uid: Optional[str] = Field(None, max_length=128, description="Node UID")
    channel: Optional[str] = Field(None, max_length=64, description="Channel name")
    greenhouse_uid: Optional[str] = Field(None, max_length=128, description="Greenhouse UID")
    zone_id: Optional[int] = Field(None, ge=1, description="Zone ID")
    zone_uid: Optional[str] = Field(None, max_length=128, description="Zone UID")
    hardware_id: Optional[str] = Field(None, max_length=128, description="Hardware ID for temporary topic")
    cmd_id: Optional[str] = Field(None, max_length=64, description="Command ID from Laravel")


@app.post("/zones/{zone_id}/commands")
async def publish_zone_command(
    request: Request,
    zone_id: int,
    req: CommandRequest = Body(...),
):
    """
    Публиковать команду для зоны через history-logger.
    Все общение бэка с нодами должно происходить через history-logger.
    """
    # Аутентификация
    _auth_ingest(request)
    
    if not (req.greenhouse_uid and req.node_uid and req.channel):
        raise HTTPException(status_code=400, detail="greenhouse_uid, node_uid and channel are required")
    
    # Получаем zone_uid из БД, если mqtt_zone_format="uid"
    zone_uid = None
    s = get_settings()
    if hasattr(s, 'mqtt_zone_format') and s.mqtt_zone_format == "uid":
        rows = await fetch(
            """
            SELECT uid
            FROM zones
            WHERE id = $1
            """,
            zone_id,
        )
        if rows and len(rows) > 0:
            zone_uid = rows[0].get("uid")
            if not zone_uid:
                logger.warning(f"Zone {zone_id} has no uid, using zn-{zone_id} as fallback")
        else:
            logger.warning(f"Zone {zone_id} not found, using zn-{zone_id} as fallback")
    
    # Генерируем cmd_id, если не указан
    import uuid
    cmd_id = req.cmd_id or str(uuid.uuid4())
    payload = {"cmd": req.type, "cmd_id": cmd_id, **({"params": req.params} if req.params else {})}
    
    # Получаем MQTT клиент
    mqtt = await get_mqtt_client()
    
    try:
        logger.info(f"Publishing command for zone {zone_id}, node {req.node_uid}, channel {req.channel}, cmd_id: {cmd_id}")
        await publish_command_mqtt(
            mqtt,
            req.greenhouse_uid,
            zone_id,
            req.node_uid,
            req.channel,
            payload,
            hardware_id=req.hardware_id,
            zone_uid=zone_uid
        )
        logger.info(f"Command published successfully for zone {zone_id}, node {req.node_uid}")
        return {"status": "ok", "data": {"command_id": cmd_id}}
    except Exception as e:
        logger.error(f"Failed to publish command for zone {zone_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to publish command: {str(e)}")


@app.post("/nodes/{node_uid}/commands")
async def publish_node_command(
    request: Request,
    node_uid: str,
    req: CommandRequest = Body(...),
):
    """
    Публиковать команду для ноды через history-logger.
    Все общение бэка с нодами должно происходить через history-logger.
    """
    # Аутентификация
    _auth_ingest(request)
    
    if not (req.greenhouse_uid and req.zone_id and req.channel):
        raise HTTPException(status_code=400, detail="greenhouse_uid, zone_id and channel are required")
    
    # Получаем zone_uid из БД, если mqtt_zone_format="uid"
    zone_uid = None
    s = get_settings()
    if hasattr(s, 'mqtt_zone_format') and s.mqtt_zone_format == "uid" and req.zone_id:
        rows = await fetch(
            """
            SELECT uid
            FROM zones
            WHERE id = $1
            """,
            req.zone_id,
        )
        if rows and len(rows) > 0:
            zone_uid = rows[0].get("uid")
            if not zone_uid:
                logger.warning(f"Zone {req.zone_id} has no uid, using zn-{req.zone_id} as fallback")
        else:
            logger.warning(f"Zone {req.zone_id} not found, using zn-{req.zone_id} as fallback")
    
    # Генерируем cmd_id, если не указан
    import uuid
    cmd_id = req.cmd_id or str(uuid.uuid4())
    payload = {"cmd": req.type, "cmd_id": cmd_id, **({"params": req.params} if req.params else {})}
    
    # Получаем MQTT клиент
    mqtt = await get_mqtt_client()
    
    try:
        logger.info(f"Publishing command for node {node_uid}, zone {req.zone_id}, channel {req.channel}, cmd_id: {cmd_id}")
        await publish_command_mqtt(
            mqtt,
            req.greenhouse_uid,
            req.zone_id,
            node_uid,
            req.channel,
            payload,
            hardware_id=req.hardware_id,
            zone_uid=zone_uid
        )
        logger.info(f"Command published successfully for node {node_uid}")
        return {"status": "ok", "data": {"command_id": cmd_id}}
    except Exception as e:
        logger.error(f"Failed to publish command for node {node_uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to publish command: {str(e)}")


class FillDrainRequest(BaseModel):
    """Request model for fill/drain operations."""
    target_level: float = Field(..., ge=0.0, le=1.0, description="Target water level (0.0-1.0)")
    max_duration_sec: Optional[int] = Field(300, ge=1, le=600, description="Maximum operation duration in seconds")


class CalibrateFlowRequest(BaseModel):
    """Request model for flow calibration."""
    node_id: int = Field(..., ge=1, description="Node ID with flow sensor")
    channel: str = Field(..., min_length=1, max_length=64, description="Flow sensor channel name")
    pump_duration_sec: Optional[int] = Field(10, ge=1, le=60, description="Pump duration for calibration")


@app.post("/zones/{zone_id}/fill")
async def zone_fill(
    request: Request,
    zone_id: int,
    req: FillDrainRequest = Body(...),
):
    """
    Выполнить режим наполнения (Fill Mode) через history-logger.
    Все общение бэка с нодами должно происходить через history-logger.
    """
    # Аутентификация
    _auth_ingest(request)
    
    # Validate target_level
    if not (0.1 <= req.target_level <= 1.0):
        raise HTTPException(status_code=400, detail="target_level must be between 0.1 and 1.0")
    
    # Get greenhouse uid
    rows = await fetch(
        """
        SELECT g.uid
        FROM zones z
        JOIN greenhouses g ON g.id = z.greenhouse_id
        WHERE z.id = $1
        """,
        zone_id,
    )
    if not rows or len(rows) == 0:
        raise HTTPException(status_code=404, detail="Zone not found or has no greenhouse")
    
    gh_uid = rows[0]["uid"]
    
    # Create MQTT client for fill operation
    # Используем синхронный MqttClient, так как water_flow функции ожидают его
    mqtt = MqttClient(client_id_suffix="-fill")
    mqtt.start()
    
    try:
        # Execute fill mode (async, but we wait for it)
        result = await execute_fill_mode(
            zone_id,
            req.target_level,
            mqtt,
            gh_uid,
            req.max_duration_sec
        )
        return {"status": "ok", "data": result}
    except Exception as e:
        logger.error(f"Failed to execute fill mode for zone {zone_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Закрываем соединение MQTT для предотвращения утечек
        mqtt.stop()


@app.post("/zones/{zone_id}/drain")
async def zone_drain(
    request: Request,
    zone_id: int,
    req: FillDrainRequest = Body(...),
):
    """
    Выполнить режим слива (Drain Mode) через history-logger.
    Все общение бэка с нодами должно происходить через history-logger.
    """
    # Аутентификация
    _auth_ingest(request)
    
    # Validate target_level
    if not (0.0 <= req.target_level <= 0.9):
        raise HTTPException(status_code=400, detail="target_level must be between 0.0 and 0.9")
    
    # Get greenhouse uid
    rows = await fetch(
        """
        SELECT g.uid
        FROM zones z
        JOIN greenhouses g ON g.id = z.greenhouse_id
        WHERE z.id = $1
        """,
        zone_id,
    )
    if not rows or len(rows) == 0:
        raise HTTPException(status_code=404, detail="Zone not found or has no greenhouse")
    
    gh_uid = rows[0]["uid"]
    
    # Create MQTT client for drain operation
    # Используем синхронный MqttClient, так как water_flow функции ожидают его
    mqtt = MqttClient(client_id_suffix="-drain")
    mqtt.start()
    
    try:
        # Execute drain mode (async, but we wait for it)
        result = await execute_drain_mode(
            zone_id,
            req.target_level,
            mqtt,
            gh_uid,
            req.max_duration_sec
        )
        return {"status": "ok", "data": result}
    except Exception as e:
        logger.error(f"Failed to execute drain mode for zone {zone_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Закрываем соединение MQTT для предотвращения утечек
        mqtt.stop()


@app.post("/zones/{zone_id}/calibrate-flow")
async def zone_calibrate_flow(
    request: Request,
    zone_id: int,
    req: CalibrateFlowRequest = Body(...),
):
    """
    Выполнить калибровку расхода воды (Flow Calibration) через history-logger.
    Все общение бэка с нодами должно происходить через history-logger.
    """
    # Аутентификация
    _auth_ingest(request)
    
    # Get greenhouse uid
    rows = await fetch(
        """
        SELECT g.uid
        FROM zones z
        JOIN greenhouses g ON g.id = z.greenhouse_id
        WHERE z.id = $1
        """,
        zone_id,
    )
    if not rows or len(rows) == 0:
        raise HTTPException(status_code=404, detail="Zone not found or has no greenhouse")
    
    gh_uid = rows[0]["uid"]
    
    # Create MQTT client for calibration operation
    # Используем синхронный MqttClient, так как water_flow функции ожидают его
    mqtt = MqttClient(client_id_suffix="-calibrate")
    mqtt.start()
    
    try:
        # Execute flow calibration (async, but we wait for it)
        result = await calibrate_flow(
            zone_id,
            req.node_id,
            req.channel,
            mqtt,
            gh_uid,
            req.pump_duration_sec
        )
        return {"status": "ok", "data": result}
    except Exception as e:
        logger.error(f"Failed to calibrate flow for zone {zone_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Закрываем соединение MQTT для предотвращения утечек
        mqtt.stop()


@app.post("/ingest/telemetry")
async def ingest_telemetry(request: Request):
    """
    HTTP endpoint для приема телеметрии.
    Принимает JSON с массивом samples и обрабатывает их батчем.
    
    Безопасность:
    - Аутентификация через токен (обязательна для внешних запросов)
    - Rate limiting (максимум INGEST_RATE_LIMIT_REQUESTS запросов за INGEST_RATE_LIMIT_WINDOW_SEC секунд)
    - Проверка размера payload (максимум MAX_PAYLOAD_SIZE)
    - Лимит на количество samples (максимум MAX_INGEST_SAMPLES)
    - Валидация каждого sample через TelemetryPayloadModel
    - Дроп некорректных записей с логированием
    """
    # Аутентификация
    _auth_ingest(request)
    
    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        logger.warning(
            f"Rate limit exceeded for HTTP ingest: client_ip={client_ip}",
            extra={"client_ip": client_ip}
        )
        INGEST_RATE_LIMITED.inc()
        INGEST_REQUESTS.labels(status="rate_limited").inc()
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: maximum {INGEST_RATE_LIMIT_REQUESTS} requests per {INGEST_RATE_LIMIT_WINDOW_SEC} seconds"
        )
    
    # Проверка размера payload для защиты от DoS
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            size = int(content_length)
            if size > MAX_PAYLOAD_SIZE:
                logger.warning(
                    f"HTTP ingest payload too large: {size} bytes (max: {MAX_PAYLOAD_SIZE})",
                    extra={"content_length": size}
                )
                raise HTTPException(
                    status_code=413,
                    detail=f"Payload too large: {size} bytes (max: {MAX_PAYLOAD_SIZE} bytes)"
                )
        except ValueError:
            pass  # Игнорируем невалидный content-length
    
    # Парсим JSON payload
    try:
        body = await request.body()
        # Дополнительная проверка размера после чтения
        if len(body) > MAX_PAYLOAD_SIZE:
            logger.warning(
                f"HTTP ingest payload too large: {len(body)} bytes (max: {MAX_PAYLOAD_SIZE})",
                extra={"payload_size": len(body)}
            )
            raise HTTPException(
                status_code=413,
                detail=f"Payload too large: {len(body)} bytes (max: {MAX_PAYLOAD_SIZE} bytes)"
            )
        
        payload = json.loads(body.decode('utf-8'))
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in HTTP ingest: {e}")
        INGEST_REQUESTS.labels(status="invalid_json").inc()
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        logger.error(f"Error parsing HTTP ingest payload: {e}", exc_info=True)
        INGEST_REQUESTS.labels(status="parse_error").inc()
        raise HTTPException(status_code=400, detail="Failed to parse payload")
    
    samples_data = payload.get("samples", [])
    if not samples_data:
        return {"status": "ok", "count": 0, "dropped": 0}
    
    # Проверка лимита на количество samples
    if len(samples_data) > MAX_INGEST_SAMPLES:
        logger.warning(
            f"HTTP ingest too many samples: {len(samples_data)} (max: {MAX_INGEST_SAMPLES})",
            extra={"samples_count": len(samples_data)}
        )
        raise HTTPException(
            status_code=400,
            detail=f"Too many samples: {len(samples_data)} (max: {MAX_INGEST_SAMPLES})"
        )
    
    # Преобразуем в TelemetrySampleModel с валидацией
    samples = []
    dropped_count = 0
    # Проверка валидности ts: должен быть > 1_000_000_000 (примерно 2001-09-09)
    # Если ts невалиден (аптайм несинхронизированной ноды), используем серверное время
    MIN_VALID_TIMESTAMP = 1_000_000_000  # 2001-09-09 01:46:40 UTC
    
    for idx, sample_data in enumerate(samples_data):
        # Валидация через TelemetryPayloadModel (как в MQTT пути)
        if not isinstance(sample_data, dict):
            logger.warning(
                f"Invalid sample type in HTTP ingest (not a dict), dropping",
                extra={"sample_index": idx, "sample_type": type(sample_data).__name__}
            )
            TELEMETRY_DROPPED.labels(reason="invalid_sample_type").inc()
            dropped_count += 1
            continue
        
        try:
            # Валидируем через TelemetryPayloadModel
            validated_data = TelemetryPayloadModel(**sample_data)
        except Exception as e:
            logger.warning(
                "Invalid telemetry sample in HTTP ingest, dropping",
                extra={
                    "error": str(e),
                    "sample_index": idx,
                    "sample_keys": list(sample_data.keys()) if isinstance(sample_data, dict) else None
                }
            )
            TELEMETRY_DROPPED.labels(reason="validation_failed").inc()
            dropped_count += 1
            continue
        
        # Проверяем обязательные поля
        if not validated_data.metric_type:
            logger.warning(
                "Missing metric_type in HTTP ingest sample, dropping",
                extra={"sample_index": idx, "sample_keys": list(sample_data.keys())}
            )
            TELEMETRY_DROPPED.labels(reason="missing_metric_type").inc()
            dropped_count += 1
            continue
        # Обрабатываем timestamp (используем validated_data)
        ts = None
        if validated_data.ts:
            try:
                ts_value = None
                if isinstance(validated_data.ts, (int, float)):
                    ts_value = float(validated_data.ts)
                    # Проверяем что ts разумный (не аптайм несинхронизированной ноды)
                    if ts_value >= MIN_VALID_TIMESTAMP:
                        ts = datetime.fromtimestamp(ts_value)
                    else:
                        logger.warning(
                            "Invalid timestamp in HTTP ingest (likely uptime), using server time",
                            extra={
                                "ts": ts_value,
                                "node_uid": validated_data.node_uid,
                                "zone_uid": validated_data.zone_uid,
                                "sample_index": idx
                            }
                        )
                elif isinstance(validated_data.ts, str):
                    ts = datetime.fromisoformat(validated_data.ts.replace('Z', '+00:00'))
                    # Проверяем что ts разумный
                    ts_timestamp = ts.timestamp()
                    if ts_timestamp < MIN_VALID_TIMESTAMP:
                        logger.warning(
                            "Invalid timestamp in HTTP ingest (likely uptime), using server time",
                            extra={
                                "ts": ts_timestamp,
                                "node_uid": validated_data.node_uid,
                                "zone_uid": validated_data.zone_uid,
                                "sample_index": idx
                            }
                        )
                        ts = None
            except Exception as e:
                logger.warning(
                    "Failed to parse timestamp in HTTP ingest, using server time",
                    extra={
                        "ts": validated_data.ts,
                        "error": str(e),
                        "node_uid": validated_data.node_uid,
                        "zone_uid": validated_data.zone_uid,
                        "sample_index": idx
                    }
                )
        
        # Если ts невалиден или отсутствует, используем серверное время
        if ts is None:
            ts = datetime.utcnow()
        
        # Извлекаем zone_id из zone_uid если нужно (будет резолвлен в process_telemetry_batch с учетом gh_uid)
        zone_uid = validated_data.zone_uid
        zone_id = None  # Будет резолвлен в process_telemetry_batch с учетом gh_uid
        
        # Используем node_uid из validated_data (fallback из payload)
        node_uid = validated_data.node_uid or ""
        
        # Используем gh_uid из validated_data (для корректного резолва зоны)
        gh_uid = validated_data.gh_uid
        
        # Используем channel из validated_data
        channel = validated_data.channel
        
        # Фильтруем raw данные для защиты от раздувания БД
        filtered_raw = _filter_raw_data(sample_data)
        
        sample = TelemetrySampleModel(
            node_uid=node_uid,
            zone_uid=zone_uid,
            zone_id=zone_id,  # Будет резолвлен в process_telemetry_batch с учетом gh_uid
            gh_uid=gh_uid,  # Greenhouse UID для корректного резолва зоны
            metric_type=validated_data.metric_type,
            value=validated_data.value,
            ts=ts,
            raw=filtered_raw,  # Сохраняем отфильтрованные данные
            channel=channel
        )
        samples.append(sample)
    
    # Обрабатываем батч
    if samples:
        await process_telemetry_batch(samples)
    
    # Метрики успешного запроса
    INGEST_REQUESTS.labels(status="success").inc()
    
    return {
        "status": "ok",
        "count": len(samples),
        "dropped": dropped_count,
        "total": len(samples_data)
    }


def setup_signal_handlers():
    """Настройка обработчиков сигналов для graceful shutdown."""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


if __name__ == "__main__":
    # Настройка логирования для детального вывода в stdout
    import sys
    import os
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_level_value = getattr(logging, log_level, logging.INFO)
    logging.basicConfig(
        level=log_level_value,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)  # Явно указываем stdout
        ],
        force=True  # Переопределяем существующую конфигурацию
    )
    # Устанавливаем уровень логирования для всех модулей
    logging.getLogger().setLevel(log_level_value)
    logging.getLogger('__main__').setLevel(log_level_value)
    logging.getLogger('main').setLevel(log_level_value)
    logging.getLogger('common.mqtt').setLevel(log_level_value)
    
    setup_signal_handlers()
    import uvicorn
    s = get_settings()
    
    # Настройка uvicorn для детального логирования
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "level": "INFO",
            "handlers": ["default"],
        },
        "loggers": {
            "uvicorn": {"level": "INFO"},
            "uvicorn.access": {"level": "INFO"},
            "main": {"level": "INFO"},
            "common.mqtt": {"level": "INFO"},
        },
    }
    
    uvicorn.run(app, host="0.0.0.0", port=s.service_port, log_config=log_config)
