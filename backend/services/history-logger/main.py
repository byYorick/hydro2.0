import asyncio
import hashlib
import hmac
import json
import logging
import os
import signal
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from common.utils.time import utcnow
from typing import Optional, List, Union, Dict, Any
import httpx

from fastapi import FastAPI, Response, Request, HTTPException, Body
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel, Field
from collections import defaultdict
import time

from common.db import execute, fetch, upsert_telemetry_last, create_zone_event, upsert_unassigned_node_error, get_pool
from common.commands import mark_command_sent, mark_command_send_failed
from common.redis_queue import TelemetryQueue, TelemetryQueueItem, close_redis_client
from common.mqtt import MqttClient, AsyncMqttClient, get_mqtt_client
from common.env import get_settings
from common.water_flow import execute_fill_mode, execute_drain_mode, calibrate_flow
from common.service_logs import send_service_log
from common.error_handler import get_error_handler
from common.command_status_queue import (
    normalize_status,
    send_status_to_laravel,
    retry_worker as command_retry_worker,
    get_status_queue,
)
from common.alert_queue import (
    retry_worker as alert_retry_worker,
    get_alert_queue,
)
from common.pipeline_metrics import (
    update_queue_metrics,
    update_mqtt_health,
    update_db_health,
    update_queue_health,
)
from common.infra_monitor import (
    check_mqtt_health,
    check_db_health,
    check_service_health,
)
from common.http_client_pool import (
    close_http_client as close_unified_http_client,
)

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
    
    # Запуск воркера для ретраев статусов команд
    command_retry_task = asyncio.create_task(command_retry_worker(interval=30.0, shutdown_event=shutdown_event))
    background_tasks.append(command_retry_task)
    
    # Запуск воркера для ретраев алертов
    alert_retry_task = asyncio.create_task(alert_retry_worker(interval=30.0, shutdown_event=shutdown_event))
    background_tasks.append(alert_retry_task)
    
    # Подключение к MQTT
    mqtt = await get_mqtt_client()
    # Формат топика согласно документации: hydro/{gh}/{zone}/{node}/{channel}/telemetry
    await mqtt.subscribe("hydro/+/+/+/+/telemetry", handle_telemetry)
    await mqtt.subscribe("hydro/+/+/+/heartbeat", handle_heartbeat)
    # Подписка на status для обработки статуса узлов (ONLINE/OFFLINE)
    await mqtt.subscribe("hydro/+/+/+/status", handle_status)
    # Подписка на diagnostics для обработки метрик ошибок
    await mqtt.subscribe("hydro/+/+/+/diagnostics", handle_diagnostics)
    # Подписка на error для обработки немедленных ошибок
    await mqtt.subscribe("hydro/+/+/+/error", handle_error)
    # Подписка на node_hello для регистрации новых узлов
    await mqtt.subscribe("hydro/node_hello", handle_node_hello)
    await mqtt.subscribe("hydro/+/+/+/node_hello", handle_node_hello)
    # Подписка на config_response для обработки подтверждений установки конфига
    await mqtt.subscribe("hydro/+/+/+/config_response", handle_config_response)
    # Подписка на command_response для обновления статусов команд (уведомления на фронт)
    await mqtt.subscribe("hydro/+/+/+/+/command_response", handle_command_response)
    # Подписка на time_request для синхронизации времени устройств
    await mqtt.subscribe("hydro/time/request", handle_time_request)
    
    logger.info("History Logger service started")
    logger.info("Subscribed to MQTT topics: hydro/+/+/+/+/telemetry, hydro/+/+/+/heartbeat, hydro/+/+/+/status, hydro/+/+/+/diagnostics, hydro/+/+/+/error, hydro/node_hello, hydro/+/+/+/node_hello, hydro/+/+/+/config_response, hydro/+/+/+/+/command_response")
    
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
    
    # Закрываем единый HTTP клиент
    await close_unified_http_client()
    
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
    
    # Логируем входящий запрос с полной информацией
    client_ip = request.client.host if request.client else 'unknown'
    full_url = str(request.url)
    logger.info(
        f"[HTTP_REQUEST] {request.method} {request.url.path} from {client_ip}, full_url={full_url}, "
        f"headers_count={len(request.headers)}, has_body={request.headers.get('content-length', '0') != '0'}"
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
    """
    Health check endpoint с проверкой компонентов.
    
    Returns:
        Статус здоровья сервиса и его компонентов
    """
    health_status = {
        "status": "ok",
        "components": {}
    }
    
    # Проверка БД
    db_ok = False
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_ok = True
        update_db_health(True)
        await check_db_health(True)
    except Exception as e:
        logger.warning(f"DB health check failed: {e}")
        update_db_health(False)
        await check_db_health(False)
        health_status["status"] = "degraded"
    
    health_status["components"]["db"] = "ok" if db_ok else "fail"
    
    # Проверка MQTT
    mqtt_ok = False
    try:
        mqtt = await get_mqtt_client()
        if mqtt and hasattr(mqtt, 'is_connected') and mqtt.is_connected():
            mqtt_ok = True
            update_mqtt_health(True)
            await check_mqtt_health(True)
        else:
            update_mqtt_health(False)
            await check_mqtt_health(False)
            health_status["status"] = "degraded"
    except Exception as e:
        logger.warning(f"MQTT health check failed: {e}")
        update_mqtt_health(False)
        await check_mqtt_health(False)
        health_status["status"] = "degraded"
    
    health_status["components"]["mqtt"] = "ok" if mqtt_ok else "fail"
    
    # Проверка очередей
    try:
        # Метрики очереди алертов
        alert_queue = await get_alert_queue()
        alert_metrics = await alert_queue.get_queue_metrics()
        update_queue_metrics('alerts', alert_metrics['size'], alert_metrics['oldest_age_seconds'])
        
        # Проверяем здоровье очереди алертов (здорова если размер < 1000 и возраст < 1 часа)
        alerts_healthy = alert_metrics['size'] < 1000 and alert_metrics['oldest_age_seconds'] < 3600
        update_queue_health('alerts', alerts_healthy)
        health_status["components"]["queue_alerts"] = {
            "status": "ok" if alerts_healthy else "degraded",
            "size": alert_metrics['size'],
            "oldest_age_seconds": alert_metrics['oldest_age_seconds'],
            "dlq_size": alert_metrics.get('dlq_size', 0),
            "success_rate": alert_metrics.get('success_rate', 1.0),
        }
        
        # Метрики очереди статусов
        status_queue = await get_status_queue()
        status_metrics = await status_queue.get_queue_metrics()
        update_queue_metrics('status_updates', status_metrics['size'], status_metrics['oldest_age_seconds'])
        
        # Проверяем здоровье очереди статусов
        status_healthy = status_metrics['size'] < 1000 and status_metrics['oldest_age_seconds'] < 3600
        update_queue_health('status_updates', status_healthy)
        health_status["components"]["queue_status_updates"] = {
            "status": "ok" if status_healthy else "degraded",
            "size": status_metrics['size'],
            "oldest_age_seconds": status_metrics['oldest_age_seconds'],
            "dlq_size": status_metrics.get('dlq_size', 0),
            "success_rate": status_metrics.get('success_rate', 1.0),
        }
        
        if not alerts_healthy or not status_healthy:
            health_status["status"] = "degraded"
    except Exception as e:
        logger.warning(f"Queue health check failed: {e}")
        health_status["components"]["queue_alerts"] = "unknown"
        health_status["components"]["queue_status_updates"] = "unknown"
        health_status["status"] = "degraded"
    
    return health_status


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    metrics_data = generate_latest()
    return Response(content=metrics_data.decode('utf-8') if isinstance(metrics_data, bytes) else metrics_data, media_type=CONTENT_TYPE_LATEST)


# DLQ Management Endpoints

@app.get("/api/dlq/alerts")
async def list_alerts_dlq(limit: int = 100, offset: int = 0):
    """
    Получить список элементов из DLQ алертов.
    
    Args:
        limit: Максимальное количество записей (по умолчанию 100)
        offset: Смещение для пагинации (по умолчанию 0)
        
    Returns:
        Список элементов DLQ с метаданными
    """
    try:
        alert_queue = await get_alert_queue()
        items = await alert_queue.list_dlq(limit=limit, offset=offset)
        metrics = await alert_queue.get_queue_metrics()
        
        return {
            "items": items,
            "total": metrics.get('dlq_size', 0),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Failed to list alerts DLQ: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/dlq/alerts/{dlq_id}/replay")
async def replay_alert_dlq(dlq_id: int):
    """
    Переместить элемент из DLQ алертов обратно в очередь для повторной попытки.
    
    Args:
        dlq_id: ID элемента в DLQ
        
    Returns:
        Результат операции
    """
    try:
        alert_queue = await get_alert_queue()
        success = await alert_queue.replay_dlq_item(dlq_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"DLQ item {dlq_id} not found")
        
        return {"success": True, "message": f"Alert DLQ item {dlq_id} replayed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to replay alert DLQ item {dlq_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/dlq/alerts/{dlq_id}")
async def purge_alert_dlq_item(dlq_id: int):
    """
    Удалить элемент из DLQ алертов.
    
    Args:
        dlq_id: ID элемента в DLQ
        
    Returns:
        Результат операции
    """
    try:
        alert_queue = await get_alert_queue()
        success = await alert_queue.purge_dlq_item(dlq_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"DLQ item {dlq_id} not found")
        
        return {"success": True, "message": f"Alert DLQ item {dlq_id} purged successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to purge alert DLQ item {dlq_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/dlq/alerts")
async def purge_all_alerts_dlq():
    """
    Удалить все элементы из DLQ алертов.
    
    Returns:
        Количество удаленных элементов
    """
    try:
        alert_queue = await get_alert_queue()
        count = await alert_queue.purge_dlq_all()
        
        return {"success": True, "message": f"Purged {count} alert DLQ items"}
    except Exception as e:
        logger.error(f"Failed to purge all alerts DLQ: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dlq/status-updates")
async def list_status_updates_dlq(limit: int = 100, offset: int = 0):
    """
    Получить список элементов из DLQ статусов команд.
    
    Args:
        limit: Максимальное количество записей (по умолчанию 100)
        offset: Смещение для пагинации (по умолчанию 0)
        
    Returns:
        Список элементов DLQ с метаданными
    """
    try:
        status_queue = await get_status_queue()
        items = await status_queue.list_dlq(limit=limit, offset=offset)
        metrics = await status_queue.get_queue_metrics()
        
        return {
            "items": items,
            "total": metrics.get('dlq_size', 0),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Failed to list status updates DLQ: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/dlq/status-updates/{dlq_id}/replay")
async def replay_status_update_dlq(dlq_id: int):
    """
    Переместить элемент из DLQ статусов команд обратно в очередь для повторной попытки.
    
    Args:
        dlq_id: ID элемента в DLQ
        
    Returns:
        Результат операции
    """
    try:
        status_queue = await get_status_queue()
        success = await status_queue.replay_dlq_item(dlq_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"DLQ item {dlq_id} not found")
        
        return {"success": True, "message": f"Status update DLQ item {dlq_id} replayed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to replay status update DLQ item {dlq_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/dlq/status-updates/{dlq_id}")
async def purge_status_update_dlq_item(dlq_id: int):
    """
    Удалить элемент из DLQ статусов команд.
    
    Args:
        dlq_id: ID элемента в DLQ
        
    Returns:
        Результат операции
    """
    try:
        status_queue = await get_status_queue()
        success = await status_queue.purge_dlq_item(dlq_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"DLQ item {dlq_id} not found")
        
        return {"success": True, "message": f"Status update DLQ item {dlq_id} purged successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to purge status update DLQ item {dlq_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/dlq/status-updates")
async def purge_all_status_updates_dlq():
    """
    Удалить все элементы из DLQ статусов команд.
    
    Returns:
        Количество удаленных элементов
    """
    try:
        status_queue = await get_status_queue()
        count = await status_queue.purge_dlq_all()
        
        return {"success": True, "message": f"Purged {count} status update DLQ items"}
    except Exception as e:
        logger.error(f"Failed to purge all status updates DLQ: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dlq/metrics")
async def get_dlq_metrics():
    """
    Получить метрики всех DLQ очередей.
    
    Returns:
        Метрики для всех очередей: oldest_age, size, dlq_size, success_rate
    """
    try:
        alert_queue = await get_alert_queue()
        status_queue = await get_status_queue()
        
        alert_metrics = await alert_queue.get_queue_metrics()
        status_metrics = await status_queue.get_queue_metrics()
        
        return {
            "alerts": {
                "size": alert_metrics.get('size', 0),
                "oldest_age_seconds": alert_metrics.get('oldest_age_seconds', 0.0),
                "dlq_size": alert_metrics.get('dlq_size', 0),
                "success_rate": alert_metrics.get('success_rate', 1.0),
            },
            "status_updates": {
                "size": status_metrics.get('size', 0),
                "oldest_age_seconds": status_metrics.get('oldest_age_seconds', 0.0),
                "dlq_size": status_metrics.get('dlq_size', 0),
                "success_rate": status_metrics.get('success_rate', 1.0),
            }
        }
    except Exception as e:
        logger.error(f"Failed to get DLQ metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

TELEM_RECEIVED = Counter("telemetry_received_total",
                         "Total telemetry messages received")
TELEM_PROCESSED = Counter("telemetry_processed_total",
                          "Total telemetry messages processed")
TELEM_BATCH_SIZE = Histogram("telemetry_batch_size",
                            "Size of telemetry batches processed")
HEARTBEAT_RECEIVED = Counter("heartbeat_received_total",
                             "Total heartbeat messages received",
                             ["node_uid"])
STATUS_RECEIVED = Counter("status_received_total",
                          "Total status messages received",
                          ["node_uid", "status"])
DIAGNOSTICS_RECEIVED = Counter("diagnostics_received_total",
                               "Total diagnostics messages received",
                               ["node_uid"])
ERROR_RECEIVED = Counter("error_received_total",
                        "Total error messages received",
                        ["node_uid", "level"])
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
COMMANDS_SENT = Counter("commands_sent_total",
                       "Total commands sent via REST API",
                       ["zone_id", "metric"])
MQTT_PUBLISH_ERRORS = Counter("mqtt_publish_errors_total",
                              "MQTT publish errors",
                              ["error_type"])

# Дополнительные метрики для мониторинга
# TELEMETRY_QUEUE_SIZE удалена - используем QUEUE_SIZE из common.redis_queue
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

# Backoff состояние для telemetry broadcast (отслеживание последовательных ошибок)
_broadcast_error_count = 0
_broadcast_last_error_time: Optional[float] = None
_broadcast_backoff_until: Optional[float] = None


def _calculate_broadcast_backoff(error_count: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """
    Вычисляет задержку для exponential backoff при ошибках broadcast.
    
    Args:
        error_count: Количество последовательных ошибок
        base_delay: Базовая задержка в секундах
        max_delay: Максимальная задержка в секундах
        
    Returns:
        Задержка в секундах
    """
    if error_count == 0:
        return 0.0
    delay = base_delay * (2 ** min(error_count - 1, 6))  # Ограничиваем экспоненту
    return min(delay, max_delay)

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
    # Также проверяем отклонение от серверного времени (искаженное время)
    MIN_VALID_TIMESTAMP = 1_000_000_000  # 2001-09-09 01:46:40 UTC
    MAX_TIMESTAMP_DRIFT_SEC = 300  # Максимальное допустимое отклонение: 5 минут
    server_timestamp = time.time()
    server_time = datetime.utcfromtimestamp(server_timestamp)
    
    raw_ts = validated_data.ts
    # Поддерживаем числовые строки (например, после eval выражений)
    if isinstance(raw_ts, str):
        stripped_ts = raw_ts.strip()
        try:
            if stripped_ts.replace(".", "", 1).isdigit():
                raw_ts = float(stripped_ts)
        except Exception:
            pass
    
    ts = None
    if raw_ts:
        try:
            ts_value = None
            if isinstance(raw_ts, (int, float)):
                ts_value = float(raw_ts)
                # Поддерживаем timestamp в миллисекундах
                if ts_value > 1_000_000_000_000:
                    ts_value = ts_value / 1000.0
                # Проверяем что ts разумный (не аптайм несинхронизированной ноды)
                if ts_value >= MIN_VALID_TIMESTAMP:
                    # Проверяем отклонение от серверного времени
                    drift = ts_value - server_timestamp
                    if drift > MAX_TIMESTAMP_DRIFT_SEC:
                        logger.warning(
                            "Timestamp from device is skewed (drift too large), using server time",
                            extra={
                                "device_ts": ts_value,
                                "server_ts": server_timestamp,
                                "drift_sec": drift,
                                "max_drift_sec": MAX_TIMESTAMP_DRIFT_SEC,
                                "topic": topic,
                                "node_uid": node_uid,
                                "zone_uid": zone_uid
                            }
                        )
                        ts = server_time
                    else:
                        # Если timestamp сильно в прошлом, все равно используем его (стейл данные)
                        if drift < -MAX_TIMESTAMP_DRIFT_SEC:
                            logger.warning(
                                "Timestamp from device is older than expected, preserving for freshness checks",
                                extra={
                                    "device_ts": ts_value,
                                    "server_ts": server_timestamp,
                                    "drift_sec": drift,
                                    "max_drift_sec": MAX_TIMESTAMP_DRIFT_SEC,
                                    "topic": topic,
                                    "node_uid": node_uid,
                                    "zone_uid": zone_uid
                                }
                            )
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
            elif isinstance(raw_ts, str):
                ts = datetime.fromisoformat(raw_ts.replace('Z', '+00:00'))
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
                else:
                    # Проверяем отклонение от серверного времени
                    drift = ts_timestamp - server_timestamp
                    if drift > MAX_TIMESTAMP_DRIFT_SEC:
                        logger.warning(
                            "Timestamp from device is skewed (drift too large), using server time",
                            extra={
                                "device_ts": ts_timestamp,
                                "server_ts": server_timestamp,
                                "drift_sec": drift,
                                "max_drift_sec": MAX_TIMESTAMP_DRIFT_SEC,
                                "topic": topic,
                                "node_uid": node_uid,
                                "zone_uid": zone_uid
                            }
                        )
                        ts = None
                    elif drift < -MAX_TIMESTAMP_DRIFT_SEC:
                        logger.warning(
                            "Timestamp from device is older than expected (string), preserving for freshness checks",
                            extra={
                                "device_ts": ts_timestamp,
                                "server_ts": server_timestamp,
                                "drift_sec": drift,
                                "max_drift_sec": MAX_TIMESTAMP_DRIFT_SEC,
                                "topic": topic,
                                "node_uid": node_uid,
                                "zone_uid": zone_uid
                            }
                        )
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
        ts = server_time

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
        enqueued_at=utcnow()  # Время добавления в очередь для трекинга возраста
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


# Глобальный кеш для резолва zone_id и node_id (с TTL refresh)
_zone_cache: dict[tuple[str, Optional[str]], int] = {}
_node_cache: dict[tuple[str, Optional[str]], tuple[int, Optional[int]]] = {}
_cache_last_update = 0.0
_cache_ttl = 60.0  # TTL кеша в секундах


async def refresh_caches():
    """Обновить кеши zone_id и node_id."""
    global _zone_cache, _node_cache, _cache_last_update
    
    try:
        # Загружаем все зоны (обычно <1000, помещаются в память)
        zones = await fetch("""
            SELECT z.id, z.uid, g.uid as gh_uid
            FROM zones z
            JOIN greenhouses g ON g.id = z.greenhouse_id
        """)
        _zone_cache.clear()
        for zone in zones:
            key = (zone['uid'], zone['gh_uid'])
            _zone_cache[key] = zone['id']
            # Также добавляем без gh_uid для fallback
            if (zone['uid'], None) not in _zone_cache:
                _zone_cache[(zone['uid'], None)] = zone['id']
        
        # Загружаем все ноды (обычно <10000, помещаются в память)
        nodes = await fetch("""
            SELECT n.id, n.uid, n.zone_id, g.uid as gh_uid
            FROM nodes n
            LEFT JOIN zones z ON z.id = n.zone_id
            LEFT JOIN greenhouses g ON g.id = z.greenhouse_id
        """)
        _node_cache.clear()
        for node in nodes:
            key = (node['uid'], node['gh_uid'])
            _node_cache[key] = (node['id'], node['zone_id'])
            # Также добавляем без gh_uid для fallback
            if (node['uid'], None) not in _node_cache:
                _node_cache[(node['uid'], None)] = (node['id'], node['zone_id'])
        
        _cache_last_update = time.time()
        logger.info(f"Cache refreshed: {len(_zone_cache)} zone entries, {len(_node_cache)} node entries")
    except Exception as e:
        logger.error(f"Failed to refresh caches: {e}", exc_info=True)


async def process_telemetry_batch(samples: List[TelemetrySampleModel]):
    """
    Обработать батч телеметрии и записать в БД.
    """
    if not samples:
        return

    start_time = time.time()
    s = get_settings()
    max_age_minutes = float(os.getenv("TELEMETRY_MAX_AGE_MINUTES", "30"))
    max_age_seconds = max_age_minutes * 60
    
    # Обновляем кеш если устарел
    global _cache_last_update, _cache_ttl
    current_time = time.time()
    if current_time - _cache_last_update > _cache_ttl:
        await refresh_caches()
    
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
        # Собираем недостающие zone_uid из кеша
        missing_zones = []
        for zone_uid, gh_uid in zone_gh_pairs:
            key = (zone_uid, gh_uid)
            if key in _zone_cache:
                zone_uid_to_id[key] = _zone_cache[key]
            else:
                # Fallback: пробуем без gh_uid
                fallback_key = (zone_uid, None)
                if fallback_key in _zone_cache:
                    zone_uid_to_id[key] = _zone_cache[fallback_key]
                else:
                    missing_zones.append((zone_uid, gh_uid))
        
        # Batch resolve недостающих зон
        if missing_zones:
            # Группируем по наличию gh_uid
            zones_with_gh = [(z, g) for z, g in missing_zones if g]
            zones_without_gh = [(z, g) for z, g in missing_zones if not g]
            
            # Batch resolve с gh_uid
            if zones_with_gh:
                zone_uids = [z for z, _ in zones_with_gh]
                gh_uids = [g for _, g in zones_with_gh]
                zone_rows = await fetch("""
                    SELECT z.id, z.uid, g.uid as gh_uid
                    FROM zones z
                    JOIN greenhouses g ON g.id = z.greenhouse_id
                    WHERE (z.uid, g.uid) IN (SELECT unnest($1::text[]), unnest($2::text[]))
                """, zone_uids, gh_uids)
                
                for zone in zone_rows:
                    key = (zone['uid'], zone['gh_uid'])
                    zone_uid_to_id[key] = zone['id']
                    _zone_cache[key] = zone['id']
            
            # Batch resolve без gh_uid (fallback)
            if zones_without_gh:
                zone_uids = [z for z, _ in zones_without_gh]
                zone_rows = await fetch("""
                    SELECT id, uid
                    FROM zones
                    WHERE uid = ANY($1)
                """, zone_uids)
                
                for zone in zone_rows:
                    key = (zone['uid'], None)
                    zone_uid_to_id[key] = zone['id']
                    _zone_cache[key] = zone['id']
        
        # Логируем предупреждения для зон, которые не были найдены
        for zone_uid, gh_uid in zone_gh_pairs:
            if (zone_uid, gh_uid) not in zone_uid_to_id:
                # Проверяем fallback без gh_uid
                if (zone_uid, None) not in zone_uid_to_id:
                    logger.warning(
                        f"Zone not found: zone_uid={zone_uid}, gh_uid={gh_uid}",
                        extra={"zone_uid": zone_uid, "gh_uid": gh_uid}
                    )
    
    # Получаем node_id из node_uid с учетом gh_uid для каждого образца
    # Ключ: (node_uid, gh_uid) -> (node_id, zone_id) - сохраняем zone_id узла для проверки соответствия
    node_uid_to_info: dict[tuple[str, Optional[str]], tuple[int, Optional[int]]] = {}
    
    # Группируем samples по (node_uid, gh_uid) для батчевого резолва
    node_gh_pairs = list(set(
        (s.node_uid, s.gh_uid)
        for s in samples
        if s.node_uid
    ))
    
    if node_gh_pairs:
        # Собираем недостающие node_uid из кеша
        missing_nodes = []
        for node_uid, gh_uid in node_gh_pairs:
            key = (node_uid, gh_uid)
            if key in _node_cache:
                node_uid_to_info[key] = _node_cache[key]
            else:
                # Fallback: пробуем без gh_uid
                fallback_key = (node_uid, None)
                if fallback_key in _node_cache:
                    node_uid_to_info[key] = _node_cache[fallback_key]
                else:
                    missing_nodes.append((node_uid, gh_uid))
        
        # Batch resolve недостающих нод
        if missing_nodes:
            # Группируем по наличию gh_uid
            nodes_with_gh = [(n, g) for n, g in missing_nodes if g]
            nodes_without_gh = [(n, g) for n, g in missing_nodes if not g]
            
            # Batch resolve с gh_uid
            if nodes_with_gh:
                node_uids = [n for n, _ in nodes_with_gh]
                gh_uids = [g for _, g in nodes_with_gh]
                node_rows = await fetch("""
                    SELECT n.id, n.uid, n.zone_id, g.uid as gh_uid
                    FROM nodes n
                    LEFT JOIN zones z ON z.id = n.zone_id
                    LEFT JOIN greenhouses g ON g.id = z.greenhouse_id
                    WHERE (n.uid, COALESCE(g.uid, '')) IN (
                        SELECT unnest($1::text[]), unnest($2::text[])
                    )
                """, node_uids, gh_uids)
                
                for node in node_rows:
                    key = (node['uid'], node['gh_uid'])
                    node_uid_to_info[key] = (node['id'], node['zone_id'])
                    _node_cache[key] = (node['id'], node['zone_id'])
            
            # Batch resolve без gh_uid (fallback)
            if nodes_without_gh:
                node_uids = [n for n, _ in nodes_without_gh]
                node_rows = await fetch("""
                    SELECT id, uid, zone_id
                    FROM nodes
                    WHERE uid = ANY($1)
                """, node_uids)
                
                for node in node_rows:
                    key = (node['uid'], None)
                    node_uid_to_info[key] = (node['id'], node['zone_id'])
                    _node_cache[key] = (node['id'], node['zone_id'])
        
        # Логируем предупреждения для узлов, которые не были найдены
        for node_uid, gh_uid in node_gh_pairs:
            if (node_uid, gh_uid) not in node_uid_to_info:
                # Проверяем fallback без gh_uid
                if (node_uid, None) not in node_uid_to_info:
                    if not gh_uid:
                        logger.warning(
                            f"gh_uid not provided for node_uid={node_uid}, using simple node_id resolution (may cause conflicts in multi-greenhouse setup)",
                            extra={"node_uid": node_uid}
                        )
                    logger.warning(
                        f"Node not found: node_uid={node_uid}, gh_uid={gh_uid}",
                        extra={"node_uid": node_uid, "gh_uid": gh_uid}
                    )
    
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
        
        # Проверяем устаревшие данные телеметрии (stale) по ts с учетом max_age
        sample_ts = sample.ts
        if sample_ts:
            if getattr(sample_ts, "tzinfo", None):
                sample_ts = sample_ts.astimezone(timezone.utc)
            else:
                sample_ts = sample_ts.replace(tzinfo=timezone.utc)
            age_seconds = (utcnow() - sample_ts).total_seconds()
            if age_seconds > max_age_seconds:
                try:
                    await create_zone_event(
                        zone_id,
                        "TELEMETRY_STALE",
                        {
                            "metric_type": sample.metric_type,
                            "age_minutes": age_seconds / 60,
                            "max_age_minutes": max_age_minutes,
                            "node_uid": sample.node_uid,
                            "channel": sample.channel
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to create TELEMETRY_STALE event: {e}", exc_info=True)
    
        key = (zone_id, sample.metric_type, node_id, sample.channel)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(sample)
    
    # Batch insert в telemetry_samples
    # Считаем реально вставленные сэмплы (не пропущенные из-за отсутствия zone_id)
    processed_count = 0
    
    # Собираем все значения для batch upsert telemetry_last
    telemetry_last_updates: dict[tuple[int, str], dict] = {}  # (zone_id, metric_type) -> {node_id, channel, value, ts}
    
    for (zone_id, metric_type, node_id, channel), group_samples in grouped.items():
        logger.info(f"[BROADCAST] Processing group: zone_id={zone_id}, node_id={node_id}, metric={metric_type}, samples={len(group_samples)}")
        # Используем TimescaleDB для эффективной вставки
        values_list = []
        params_list = []
        param_index = 1
        
        for sample in group_samples:
            ts = sample.ts or utcnow()
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
        
        # Собираем данные для batch upsert telemetry_last
        # Выбираем сэмпл с максимальным ts (самый свежий), а не просто последний в батче
        # Это важно, так как телеметрия может приходить вне порядка (MQTT/очереди/ретраи)
        logger.info(f"[BROADCAST] Before upsert check: group_samples={len(group_samples) if group_samples else 0}, node_id={node_id}")
        if group_samples:
            # Находим сэмпл с максимальным ts
            latest_sample = max(
                group_samples,
                key=lambda s: s.ts if s.ts else datetime.min.replace(tzinfo=None)
            )
            
            # Сохраняем для batch upsert
            key = (zone_id, metric_type)
            if key not in telemetry_last_updates:
                telemetry_last_updates[key] = {
                    'node_id': node_id,
                    'channel': channel,
                    'value': latest_sample.value,
                    'ts': latest_sample.ts
                }
            else:
                # Обновляем только если новый ts больше
                existing_ts = telemetry_last_updates[key].get('ts') or datetime.min.replace(tzinfo=None)
                new_ts = latest_sample.ts or datetime.min.replace(tzinfo=None)
                if new_ts > existing_ts:
                    telemetry_last_updates[key] = {
                        'node_id': node_id,
                        'channel': channel,
                        'value': latest_sample.value,
                        'ts': new_ts
                    }
            
            # Broadcast телеметрии через Laravel API (Laravel отправляет через WebSocket клиентам).
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
                        timestamp=latest_sample.ts or utcnow()
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
    
    # Batch upsert telemetry_last для всех обновлений
    if telemetry_last_updates:
        try:
            values_list = []
            params_list = []
            param_index = 1
            
            for (zone_id, metric_type), update_data in telemetry_last_updates.items():
                node_id = update_data['node_id'] if update_data['node_id'] is not None else -1
                channel = update_data['channel']
                value = update_data['value']
                sample_ts = update_data.get('ts')
                if sample_ts and getattr(sample_ts, "tzinfo", None):
                    # Приводим к UTC и убираем tzinfo для совместимости с timestamp without time zone
                    sample_ts = sample_ts.astimezone(timezone.utc).replace(tzinfo=None)
                if not sample_ts:
                    sample_ts = utcnow()
                
                values_list.append(
                    f"(${param_index}, ${param_index + 1}, ${param_index + 2}, ${param_index + 3}, ${param_index + 4}, ${param_index + 5})"
                )
                params_list.extend([zone_id, node_id, metric_type, channel, value, sample_ts])
                param_index += 6
            
            if values_list:
                query = f"""
                    INSERT INTO telemetry_last (zone_id, node_id, metric_type, channel, value, updated_at)
                    VALUES {', '.join(values_list)}
                    ON CONFLICT (zone_id, metric_type)
                    DO UPDATE SET 
                        node_id = EXCLUDED.node_id,
                        channel = EXCLUDED.channel,
                        value = EXCLUDED.value,
                        updated_at = EXCLUDED.updated_at
                """
                await execute(query, *params_list)
                logger.debug(f"Batch upserted {len(telemetry_last_updates)} telemetry_last records")
        except Exception as e:
            logger.error(f"Failed to batch upsert telemetry_last: {e}", exc_info=True)
            # Fallback: используем индивидуальные upsert
            for (zone_id, metric_type), update_data in telemetry_last_updates.items():
                try:
                    await upsert_telemetry_last(
                        zone_id,
                        metric_type,
                        update_data['node_id'],
                        update_data['channel'],
                        update_data['value'],
                        update_data.get('ts')
                    )
                except Exception as e2:
                    logger.error(f"Failed to upsert telemetry_last for zone_id={zone_id}, metric_type={metric_type}: {e2}")
    
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
    Вызывает Laravel API для broadcast телеметрии.
    Laravel сам отправляет данные клиентам через WebSocket (Reverb).
    History-logger НЕ подключается к WebSocket напрямую, только через HTTP API Laravel.
    Выполняется асинхронно в фоне, чтобы не блокировать основной процесс.
    Использует глобальный httpx.AsyncClient для переиспользования соединений.
    """
    global _broadcast_error_count, _broadcast_last_error_time, _broadcast_backoff_until
    
    # Проверяем shutdown в начале функции, чтобы быстро выйти если shutdown начался.
    if shutdown_event.is_set():
        logger.debug("[BROADCAST] Shutdown in progress, skipping telemetry broadcast")
        return
    
    # Проверяем backoff: если мы в режиме backoff, пропускаем запрос
    current_time = time.time()
    if _broadcast_backoff_until is not None and current_time < _broadcast_backoff_until:
        logger.debug(
            f"[BROADCAST] In backoff mode, skipping broadcast. "
            f"Backoff until: {_broadcast_backoff_until:.2f}, current: {current_time:.2f}, "
            f"error_count: {_broadcast_error_count}"
        )
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
        # utcnow() создает aware datetime с timezone.utc.
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
        
        # Проверяем shutdown перед HTTP запросом, чтобы не делать запросы после shutdown.
        if shutdown_event.is_set():
            logger.debug("[BROADCAST] Shutdown in progress, skipping HTTP request")
            return
        
        # Используем единый HTTP клиент с semaphore для backpressure
        from common.http_client_pool import make_request
        api_start = time.time()
        response = await make_request(
            'post',
            f"{laravel_url}/api/python/broadcast/telemetry",
            endpoint='telemetry_broadcast',
            json=api_data,
            headers={
                'Authorization': f'Bearer {ingest_token}',
                'Content-Type': 'application/json',
            }
        )
        api_duration = time.time() - api_start
        LARAVEL_API_DURATION.observe(api_duration)
        
        if response.status_code == 200:
            # Успешный запрос - сбрасываем счетчик ошибок и backoff
            if _broadcast_error_count > 0:
                logger.info(
                    f"[BROADCAST] Success after {_broadcast_error_count} errors, "
                    f"resetting error count and backoff"
                )
            _broadcast_error_count = 0
            _broadcast_backoff_until = None
            logger.info(f"[BROADCAST] Telemetry broadcasted successfully: node_id={node_id}, metric={metric_type}, value={value}")
        else:
            # Ошибка HTTP статуса - увеличиваем счетчик ошибок
            _broadcast_error_count += 1
            _broadcast_last_error_time = current_time
            backoff_delay = _calculate_broadcast_backoff(_broadcast_error_count)
            _broadcast_backoff_until = current_time + backoff_delay
            
            logger.warning(
                f"[BROADCAST] Failed to broadcast telemetry: status={response.status_code}, "
                f"error_count={_broadcast_error_count}, backoff={backoff_delay:.2f}s",
                extra={
                    'node_id': node_id,
                    'metric_type': metric_type,
                    'status_code': response.status_code,
                    'response': response.text[:200],
                    'error_count': _broadcast_error_count,
                    'backoff_seconds': backoff_delay
                }
            )
    except (httpx.TimeoutException, httpx.RequestError, httpx.NetworkError) as e:
        # Сетевые ошибки - увеличиваем счетчик ошибок
        _broadcast_error_count += 1
        _broadcast_last_error_time = current_time
        backoff_delay = _calculate_broadcast_backoff(_broadcast_error_count)
        _broadcast_backoff_until = current_time + backoff_delay
        
        logger.warning(
            f"[BROADCAST] Network error broadcasting telemetry: {e}, "
            f"error_count={_broadcast_error_count}, backoff={backoff_delay:.2f}s",
            extra={
                'node_id': node_id,
                'error_count': _broadcast_error_count,
                'backoff_seconds': backoff_delay
            }
        )
    except Exception as e:
        # Неожиданные ошибки - также увеличиваем счетчик
        _broadcast_error_count += 1
        _broadcast_last_error_time = current_time
        backoff_delay = _calculate_broadcast_backoff(_broadcast_error_count)
        _broadcast_backoff_until = current_time + backoff_delay
        
        logger.warning(
            f"[BROADCAST] Error broadcasting telemetry: {e}, "
            f"error_count={_broadcast_error_count}, backoff={backoff_delay:.2f}s",
            extra={
                'node_id': node_id,
                'error_count': _broadcast_error_count,
                'backoff_seconds': backoff_delay
            },
            exc_info=True
        )


async def process_telemetry_queue():
    """
    Фоновая задача для обработки очереди телеметрии из Redis.
    Обрабатывает батчи данных согласно настройкам.
    """
    global telemetry_queue

    s = get_settings()
    last_flush = utcnow()

    logger.info("Starting telemetry queue processor")

    while not shutdown_event.is_set():
        try:
            # Проверяем условия для flush
            queue_start_time = time.time()
            queue_size = await telemetry_queue.size()
            queue_duration = time.time() - queue_start_time
            REDIS_OPERATION_DURATION.observe(queue_duration)
            
            # Метрика размера очереди обновляется автоматически в TelemetryQueue.push()
            # Не обновляем здесь, чтобы избежать дублирования регистрации
            
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
            
            time_since_flush = (utcnow() - last_flush).total_seconds() * 1000

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
                    last_flush = utcnow()

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


async def handle_status(topic: str, payload: bytes):
    """
    Обработчик status сообщений от узлов ESP32.
    Обновляет статус узла в БД при получении ONLINE/OFFLINE.
    """
    logger.info(f"[STATUS] ===== START processing status =====")
    logger.info(f"[STATUS] Topic: {topic}, payload length: {len(payload)}")
    
    data = _parse_json(payload)
    if not data or not isinstance(data, dict):
        logger.warning(f"[STATUS] Invalid JSON in status from topic {topic}")
        return
    
    node_uid = _extract_node_uid(topic)
    if not node_uid:
        logger.warning(f"[STATUS] Could not extract node_uid from topic {topic}")
        return
    
    status = data.get("status", "").upper()
    ts = data.get("ts")
    
    logger.info(f"[STATUS] Processing status for node_uid: {node_uid}, status: {status}")
    
    # Обновляем статус узла в БД
    if status == "ONLINE":
        # Обновляем статус и last_seen_at
        await execute(
            "UPDATE nodes SET status='online', last_seen_at=NOW(), updated_at=NOW() WHERE uid=$1",
            node_uid
        )
        logger.info(f"[STATUS] Node {node_uid} marked as ONLINE")
    elif status == "OFFLINE":
        # Обновляем статус
        await execute(
            "UPDATE nodes SET status='offline', updated_at=NOW() WHERE uid=$1",
            node_uid
        )
        logger.info(f"[STATUS] Node {node_uid} marked as OFFLINE")
    else:
        logger.warning(f"[STATUS] Unknown status value: {status} for node {node_uid}")
    
    STATUS_RECEIVED.labels(node_uid=node_uid, status=status.lower()).inc()


async def handle_diagnostics(topic: str, payload: bytes):
    """
    Обработчик diagnostics сообщений от узлов ESP32.
    Обрабатывает метрики ошибок через общий компонент error_handler.
    """
    logger.info(f"[DIAGNOSTICS] ===== START processing diagnostics =====")
    logger.info(f"[DIAGNOSTICS] Topic: {topic}, payload length: {len(payload)}")
    
    data = _parse_json(payload)
    if not data or not isinstance(data, dict):
        logger.warning(f"[DIAGNOSTICS] Invalid JSON in diagnostics from topic {topic}")
        return
    
    node_uid = _extract_node_uid(topic)
    if not node_uid:
        logger.warning(f"[DIAGNOSTICS] Could not extract node_uid from topic {topic}")
        return
    
    logger.info(f"[DIAGNOSTICS] Processing diagnostics for node_uid: {node_uid}")
    
    # Используем общий компонент для обработки
    error_handler = get_error_handler()
    await error_handler.handle_diagnostics(node_uid, data)
    
    DIAGNOSTICS_RECEIVED.labels(node_uid=node_uid).inc()


async def handle_error(topic: str, payload: bytes):
    """
    Обработчик error сообщений от узлов ESP32.
    Обрабатывает немедленные ошибки через общий компонент error_handler.
    Для temp-топиков (gh-temp/zn-temp) записывает ошибки в unassigned_node_errors.
    """
    logger.info(f"[ERROR] ===== START processing error =====")
    logger.info(f"[ERROR] Topic: {topic}, payload length: {len(payload)}")
    
    data = _parse_json(payload)
    if not data or not isinstance(data, dict):
        logger.warning(f"[ERROR] Invalid JSON in error from topic {topic}")
        return
    
    # Проверяем, является ли это temp-топиком
    gh_uid = _extract_gh_uid(topic)
    zone_uid = _extract_zone_uid(topic)
    is_temp_topic = (gh_uid == "gh-temp" and zone_uid == "zn-temp")
    
    if is_temp_topic:
        # Это temp-топик - извлекаем hardware_id вместо node_uid
        hardware_id = _extract_node_uid(topic)  # В temp-топике на позиции node_uid находится hardware_id
        if not hardware_id:
            logger.warning(f"[ERROR] Could not extract hardware_id from temp topic {topic}")
            return
        
        level = data.get("level", "ERROR")
        component = data.get("component", "unknown")
        error_code = data.get("error_code")
        error_message = data.get("message", data.get("error", "Unknown error"))
        
        logger.info(
            f"[ERROR] Processing error for unassigned node (hardware_id: {hardware_id}), "
            f"level: {level}, component: {component}, error_code: {error_code}"
        )
        
        # Записываем ошибку в таблицу unassigned_node_errors
        try:
            await upsert_unassigned_node_error(
                hardware_id=hardware_id,
                error_message=error_message,
                error_code=error_code,
                severity=level,
                topic=topic,
                last_payload=data
            )
            logger.info(f"[ERROR] Saved error for unassigned node hardware_id={hardware_id}")
        except Exception as e:
            logger.error(f"[ERROR] Failed to save unassigned node error: {e}", exc_info=True)
        
        ERROR_RECEIVED.labels(node_uid=f"unassigned-{hardware_id}", level=level.lower()).inc()
        return
    
    # Обычная обработка для привязанных узлов
    node_uid = _extract_node_uid(topic)
    if not node_uid:
        logger.warning(f"[ERROR] Could not extract node_uid from topic {topic}")
        return
    
    level = data.get("level", "ERROR")
    component = data.get("component", "unknown")
    error_code = data.get("error_code", "unknown")
    
    logger.info(
        f"[ERROR] Processing error for node_uid: {node_uid}, "
        f"level: {level}, component: {component}, error_code: {error_code}"
    )
    
    # Проверяем, существует ли узел в БД
    try:
        node_rows = await fetch(
            """
            SELECT n.id, n.hardware_id, n.zone_id
            FROM nodes n
            WHERE n.uid = $1
            """,
            node_uid
        )
        
        if not node_rows or len(node_rows) == 0:
            # Узел не найден - записываем в unassigned_node_errors
            # Пытаемся извлечь hardware_id из topic (может быть в формате hydro/gh/zn/{hardware_id}/error)
            # Или из payload если он там есть
            hardware_id_from_topic = node_uid  # node_uid может быть hardware_id если узел не зарегистрирован
            hardware_id_from_payload = data.get("hardware_id")
            hardware_id = hardware_id_from_payload or hardware_id_from_topic
            
            error_message = data.get("message", data.get("error", "Unknown error"))
            
            logger.info(
                f"[ERROR] Node not found in DB, saving to unassigned errors: "
                f"node_uid={node_uid}, hardware_id={hardware_id}"
            )
            
            try:
                await upsert_unassigned_node_error(
                    hardware_id=hardware_id,
                    error_message=error_message,
                    error_code=error_code,
                    severity=level,
                    topic=topic,
                    last_payload=data
                )
                logger.info(f"[ERROR] Saved error for unassigned node hardware_id={hardware_id}")
            except Exception as e:
                logger.error(f"[ERROR] Failed to save unassigned node error: {e}", exc_info=True)
            
            ERROR_RECEIVED.labels(node_uid=f"unassigned-{hardware_id}", level=level.lower()).inc()
            return
        
        # Узел найден - используем обычную обработку
        node = node_rows[0]
        zone_id = node.get("zone_id")
        
        if not zone_id:
            # Узел не привязан к зоне - записываем в unassigned_node_errors по hardware_id
            hardware_id = node.get("hardware_id")
            if hardware_id:
                error_message = data.get("message", data.get("error", "Unknown error"))
                logger.info(
                    f"[ERROR] Node not assigned to zone, saving to unassigned errors: "
                    f"node_uid={node_uid}, hardware_id={hardware_id}, node_id={node['id']}"
                )
                try:
                    await upsert_unassigned_node_error(
                        hardware_id=hardware_id,
                        error_message=error_message,
                        error_code=error_code,
                        severity=level,
                        topic=topic,
                        last_payload=data
                    )
                    logger.info(f"[ERROR] Saved error for unassigned node hardware_id={hardware_id}")
                except Exception as e:
                    logger.error(f"[ERROR] Failed to save unassigned node error: {e}", exc_info=True)
                ERROR_RECEIVED.labels(node_uid=f"unassigned-{hardware_id}", level=level.lower()).inc()
                return
        
        # Узел найден и привязан к зоне - используем обычную обработку
        error_handler = get_error_handler()
        await error_handler.handle_error(node_uid, data)
        
    except Exception as e:
        logger.error(f"[ERROR] Error checking node in DB: {e}", exc_info=True)
        # При ошибке БД всё равно пытаемся обработать через error_handler
        error_handler = get_error_handler()
        await error_handler.handle_error(node_uid, data)
    
    ERROR_RECEIVED.labels(node_uid=node_uid, level=level.lower()).inc()


async def handle_config_response(topic: str, payload: bytes):
    """
    Обработчик config_response сообщений от узлов ESP32.
    Переводит ноду в ASSIGNED_TO_ZONE после успешной установки конфига.
    """
    try:
        logger.info(f"[CONFIG_RESPONSE] ===== START processing config_response =====")
        logger.info(f"[CONFIG_RESPONSE] Topic: {topic}, payload length: {len(payload)}")
        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[CONFIG_RESPONSE] Invalid JSON in config_response from topic {topic}")
            CONFIG_RESPONSE_ERROR.labels(node_uid="unknown").inc()
            return
        
        node_uid = _extract_node_uid(topic)
        if not node_uid:
            logger.warning(f"[CONFIG_RESPONSE] Could not extract node_uid from topic {topic}")
            logger.warning(f"[CONFIG_RESPONSE] Topic parts: {topic.split('/')}")
            CONFIG_RESPONSE_ERROR.labels(node_uid="unknown").inc()
            return
        
        logger.info(f"[CONFIG_RESPONSE] Extracted node_uid: {node_uid} from topic: {topic}")
        logger.info(f"[CONFIG_RESPONSE] Payload: {data}")
        
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
                    logger.warning(
                        f"[CONFIG_RESPONSE] Node {node_uid} not found in database, ignoring ACK. "
                        f"Topic: {topic}, Payload: {data}"
                    )
                    CONFIG_RESPONSE_ERROR.labels(node_uid=node_uid).inc()
                    return
                
                node = node_rows[0]
                node_config = node.get("config") or {}
                
                logger.debug(f"[CONFIG_RESPONSE] Node found in DB: id={node.get('id')}, lifecycle_state={node.get('lifecycle_state')}, zone_id={node.get('zone_id')}, pending_zone_id={node.get('pending_zone_id')}")
                logger.debug(f"[CONFIG_RESPONSE] Node config: {node_config}, has_version: {'version' in node_config if node_config else False}")
                
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

                channels_payload = data.get("channels")
                if channels_payload is not None:
                    try:
                        await sync_node_channels_from_payload(node.get("id"), node_uid, channels_payload)
                    except Exception as sync_err:
                        logger.warning(
                            f"[CONFIG_RESPONSE] Failed to sync channels for node {node_uid}: {sync_err}",
                            exc_info=True
                        )
                
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
                # 3. Зона существует в БД (ПРОБЛЕМА #2 FIX)
                target_zone_id = zone_id or pending_zone_id
                if lifecycle_state == "REGISTERED_BACKEND" and target_zone_id:
                    # Проверяем существование зоны
                    zone_check = await fetch(
                        "SELECT id FROM zones WHERE id = $1",
                        target_zone_id
                    )
                    if not zone_check:
                        logger.warning(
                            f"[CONFIG_RESPONSE] Zone {target_zone_id} not found, cannot complete binding for node {node_uid}"
                        )
                        CONFIG_RESPONSE_ERROR.labels(node_uid=node_uid).inc()
                        return
                    
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
                                gh_uid = node.get("gh_uid")
                                zone_uid = node.get("zone_uid")
                                
                                if hardware_id and gh_uid and zone_uid:
                                    # Используем реальные gh_uid и zone_uid вместо хардкода
                                    temp_topic = f"hydro/{gh_uid}/{zone_uid}/{hardware_id}/config"
                                    logger.info(f"[CONFIG_RESPONSE] Clearing retained message on temp topic: {temp_topic}")
                                    # ПРОБЛЕМА #3 FIX: Добавляем retry логику для очистки retained сообщений
                                    max_retries = 3
                                    cleared = False
                                    for attempt in range(max_retries):
                                        try:
                                            mqtt = await get_mqtt_client()
                                            base_client = mqtt._client
                                            # Публикуем пустое сообщение с retain=True для очистки retained сообщения
                                            result = base_client._client.publish(temp_topic, "", qos=1, retain=True)
                                            if result.rc == 0:
                                                logger.info(f"[CONFIG_RESPONSE] Retained message cleared on temp topic: {temp_topic}")
                                                cleared = True
                                                break
                                            elif attempt < max_retries - 1:
                                                await asyncio.sleep(0.5 * (attempt + 1))
                                        except Exception as clear_err:
                                            if attempt < max_retries - 1:
                                                await asyncio.sleep(0.5 * (attempt + 1))
                                            else:
                                                logger.warning(f"[CONFIG_RESPONSE] Error clearing retained message on temp topic {temp_topic} after {max_retries} attempts: {clear_err}")
                                    
                                    if not cleared:
                                        logger.warning(f"[CONFIG_RESPONSE] Failed to clear retained message on temp topic {temp_topic} after {max_retries} attempts")
                                
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


async def sync_node_channels_from_payload(node_id: int, node_uid: str, channels_payload: Any) -> None:
    if not node_id:
        logger.warning("[CONFIG_RESPONSE] Cannot sync channels: node_id missing")
        return

    if not isinstance(channels_payload, list):
        logger.warning(
            f"[CONFIG_RESPONSE] channels payload is not a list for node {node_uid}: {type(channels_payload)}"
        )
        return

    if len(channels_payload) == 0:
        logger.info(f"[CONFIG_RESPONSE] channels payload empty for node {node_uid}, skipping sync")
        return

    updated = 0
    skipped = 0
    for channel in channels_payload:
        if not isinstance(channel, dict):
            skipped += 1
            continue

        channel_name = channel.get("name") or channel.get("channel")
        if channel_name is None:
            skipped += 1
            continue

        channel_name = str(channel_name).strip()
        if not channel_name:
            skipped += 1
            continue

        channel_name = channel_name[:255]

        type_value = channel.get("type") or channel.get("channel_type")
        if type_value is not None:
            type_value = str(type_value).strip().upper()
            if not type_value:
                type_value = None

        metric_value = channel.get("metric") or channel.get("metrics")
        if metric_value is not None:
            metric_value = str(metric_value).strip().upper()
            if not metric_value:
                metric_value = None

        unit_value = channel.get("unit")
        if unit_value is not None:
            unit_value = str(unit_value).strip()
            if not unit_value:
                unit_value = None

        config = {
            key: value
            for key, value in channel.items()
            if key not in {"name", "channel", "type", "channel_type", "metric", "metrics", "unit"}
        }
        if not config:
            config = None

        await execute(
            """
            INSERT INTO node_channels (node_id, channel, type, metric, unit, config, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
            ON CONFLICT (node_id, channel)
            DO UPDATE SET
                type = COALESCE(EXCLUDED.type, node_channels.type),
                metric = COALESCE(EXCLUDED.metric, node_channels.metric),
                unit = COALESCE(EXCLUDED.unit, node_channels.unit),
                config = COALESCE(EXCLUDED.config, node_channels.config),
                updated_at = NOW()
            """,
            node_id,
            channel_name,
            type_value,
            metric_value,
            unit_value,
            config,
        )
        updated += 1

    logger.info(
        f"[CONFIG_RESPONSE] Synced {updated} channel(s) for node {node_uid}, skipped {skipped}"
    )


# Helper функции для устранения дублирования
def _has_rows(rows: Optional[List]) -> bool:
    """Проверить, есть ли результаты в rows."""
    return rows is not None and len(rows) > 0


async def _get_zone_uid_from_id(zone_id: int) -> Optional[str]:
    """Получить zone_uid из zone_id для MQTT публикации."""
    rows = await fetch(
        """
        SELECT uid
        FROM zones
        WHERE id = $1
        """,
        zone_id,
    )
    if _has_rows(rows):
        zone_uid = rows[0].get("uid")
        if not zone_uid:
            logger.warning(f"Zone {zone_id} has no uid, using zn-{zone_id} as fallback")
        return zone_uid
    else:
        logger.warning(f"Zone {zone_id} not found, using zn-{zone_id} as fallback")
        return None


async def _get_gh_uid_from_zone_id(zone_id: int) -> str:
    """Получить greenhouse_uid из zone_id."""
    rows = await fetch(
        """
        SELECT g.uid
        FROM zones z
        JOIN greenhouses g ON g.id = z.greenhouse_id
        WHERE z.id = $1
        """,
        zone_id,
    )
    if not _has_rows(rows):
        raise HTTPException(status_code=404, detail="Zone not found or has no greenhouse")
    return rows[0]["uid"]


def _create_command_payload(
    cmd_type: Optional[str] = None,
    cmd_id: Optional[str] = None,
    params: Optional[dict] = None,
    cmd: Optional[str] = None,
    ts: Optional[int] = None,
    sig: Optional[str] = None
) -> dict:
    """Создать payload для команды MQTT."""
    cmd_id = cmd_id or str(uuid.uuid4())
    # Поддерживаем оба формата: cmd (новый) и type (legacy)
    command_name = cmd or cmd_type
    if not command_name:
        raise ValueError("Either 'cmd' or 'type' must be provided")
    if sig and ts is None:
        raise ValueError("sig requires ts")
    payload = {"cmd": command_name, "cmd_id": cmd_id}

    if ts is None or not sig:
        secret = get_settings().node_default_secret
        if secret:
            if ts is None:
                ts = int(time.time())
            if not sig:
                payload_str = f"{command_name}|{ts}".encode()
                sig = hmac.new(secret.encode(), payload_str, hashlib.sha256).hexdigest()

    if ts is not None:
        payload["ts"] = ts
    if sig:
        payload["sig"] = sig
    if params:
        payload["params"] = params
    return payload


@asynccontextmanager
async def _mqtt_client_context(suffix: str):
    """Context manager для создания и закрытия MQTT клиента."""
    mqtt = MqttClient(client_id_suffix=suffix)
    mqtt.start()
    try:
        yield mqtt
    finally:
        mqtt.stop()


def _validate_target_level(value: float, min_val: float, max_val: float, operation: str) -> None:
    """Валидация target_level для fill/drain операций."""
    if not (min_val <= value <= max_val):
        raise HTTPException(
            status_code=400,
            detail=f"target_level must be between {min_val} and {max_val} for {operation}"
        )


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


def _extract_topic_part(topic: str, index: int) -> Optional[str]:
    """Универсальная функция для извлечения части топика по индексу.
    
    Формат топика: hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/telemetry
    Индексы: 0=hydro, 1=gh_uid, 2=zone_uid, 3=node_uid, 4=channel, 5=telemetry
    """
    parts = topic.split("/")
    if 0 <= index < len(parts):
        return parts[index]
    return None


def _extract_zone_uid(topic: str) -> Optional[str]:
    """Извлечь zone_uid из топика."""
    return _extract_topic_part(topic, 2)


def _extract_node_uid(topic: str) -> Optional[str]:
    """Извлечь node_uid из топика."""
    return _extract_topic_part(topic, 3)


def _extract_gh_uid(topic: str) -> Optional[str]:
    """Извлечь gh_uid (greenhouse UID) из топика."""
    return _extract_topic_part(topic, 1)


def _extract_channel_from_topic(topic: str) -> Optional[str]:
    """Извлечь channel из топика телеметрии."""
    return _extract_topic_part(topic, 4)


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
    Обновляет статус команды через Laravel API с использованием надёжной доставки.
    """
    try:
        logger.info(f"[COMMAND_RESPONSE] STEP 0: Received message on topic {topic}, payload length: {len(payload)}")
        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[COMMAND_RESPONSE] STEP 0.1: Invalid JSON in command_response from topic {topic}")
            COMMAND_RESPONSE_ERROR.inc()
            return

        cmd_id = data.get("cmd_id")
        raw_status = data.get("status", "")
        
        logger.info(f"[COMMAND_RESPONSE] STEP 0.2: Parsed command_response: cmd_id={cmd_id}, status={raw_status}, topic={topic}")
        node_uid = _extract_node_uid(topic)
        channel = _extract_channel_from_topic(topic)
        gh_uid = _extract_gh_uid(topic)

        if not cmd_id or not raw_status:
            logger.warning(f"[COMMAND_RESPONSE] Missing cmd_id or status in payload: {data}")
            COMMAND_RESPONSE_ERROR.inc()
            return

        # Нормализуем статус в ACCEPTED/DONE/FAILED
        normalized_status = normalize_status(raw_status)
        if not normalized_status:
            logger.warning(
                f"[COMMAND_RESPONSE] Unknown status '{raw_status}' for cmd_id={cmd_id}, "
                f"node_uid={node_uid}, channel={channel}"
            )
            COMMAND_RESPONSE_ERROR.inc()
            return

        COMMAND_RESPONSE_RECEIVED.inc()

        # Проверяем наличие команды в БД. Если отсутствует - создаём stub record.
        # Это защищает от потери cmd_id при быстром ответе ноды (response раньше SENT).
        try:
            existing_cmd = await fetch("SELECT status FROM commands WHERE cmd_id = $1", cmd_id)
            if not existing_cmd:
                # Команда отсутствует - создаём stub record через UPSERT
                # Получаем node_id и zone_id из node_uid
                node_id = None
                zone_id = None
                cmd_name = None
                
                if node_uid:
                    node_rows = await fetch(
                        "SELECT id, zone_id FROM nodes WHERE uid = $1",
                        node_uid
                    )
                    if node_rows:
                        node_id = node_rows[0]["id"]
                        zone_id = node_rows[0]["zone_id"]
                
                # Определяем cmd из details или используем "unknown"
                # Если cmd_name не указан, используем пустую строку (не NULL, т.к. поле NOT NULL)
                cmd_name = "unknown"
                
                # Статус ставим в зависимости от normalized_status
                status_value = normalized_status.value if hasattr(normalized_status, 'value') else str(normalized_status)
                
                # UPSERT stub record с origin='device' (помечаем как полученную от устройства)
                await execute(
                    """
                    INSERT INTO commands (zone_id, node_id, channel, cmd, params, status, source, cmd_id, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
                    ON CONFLICT (cmd_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        source = COALESCE(commands.source, EXCLUDED.source),
                        updated_at = NOW()
                    """,
                    zone_id, node_id, channel, cmd_name, {}, status_value, "device", cmd_id
                )
                logger.info(
                    f"[COMMAND_RESPONSE] Created stub record for cmd_id={cmd_id}, "
                    f"status={status_value}, node_uid={node_uid}, channel={channel}, origin=device"
                )
        except Exception as e:
            logger.warning(
                f"[COMMAND_RESPONSE] Failed to ensure stub record for cmd_id={cmd_id}: {e}",
                exc_info=True
            )
            # Продолжаем обработку даже при ошибке создания stub record

        # Формируем детали для отправки
        details = {
            "error_code": data.get("error_code"),
            "error_message": data.get("error_message"),
            "raw_status": str(raw_status),
            "node_uid": node_uid,
            "channel": channel,
            "gh_uid": gh_uid,
        }
        # Убираем None значения
        details = {k: v for k, v in details.items() if v is not None}

        # Отправляем статус через надёжную систему доставки
        # (автоматически сохранит в очередь при ошибке)
        success = await send_status_to_laravel(cmd_id, normalized_status, details)
        
        if success:
            logger.info(
                f"[COMMAND_RESPONSE] Status '{normalized_status.value}' delivered to Laravel "
                f"for cmd_id={cmd_id}, node_uid={node_uid}, channel={channel}"
            )
        else:
            logger.info(
                f"[COMMAND_RESPONSE] Status '{normalized_status.value}' queued for retry "
                f"for cmd_id={cmd_id}, node_uid={node_uid}, channel={channel}"
            )
            
    except Exception as e:
        logger.error(f"[COMMAND_RESPONSE] Unexpected error processing message: {e}", exc_info=True)
        COMMAND_RESPONSE_ERROR.inc()


async def handle_time_request(topic: str, payload: bytes):
    """
    Обработчик запросов времени от устройств (time_request).
    Отправляет команду set_time с текущим серверным временем.
    
    Топик: hydro/time/request
    Payload: {"message_type": "time_request", "uptime": <seconds>}
    
    Для отправки команды set_time нужно знать node_uid, gh_uid, zone_uid.
    Так как топик hydro/time/request не содержит эту информацию,
    мы используем временный топик с hardware_id или пытаемся найти устройство по MAC.
    """
    try:
        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[TIME_REQUEST] Invalid JSON in time_request from topic {topic}")
            return
        
        # Получаем текущее серверное время (Unix timestamp в секундах)
        server_time = int(utcnow().timestamp())
        
        # Получаем MQTT клиент для публикации команды
        mqtt = await get_mqtt_client()
        
        # Пробуем найти устройство в БД по hardware_id или другим признакам
        # Если не найдем, используем временный топик
        node_uid = None
        gh_uid = None
        zone_uid = None
        
        # Пытаемся найти устройство в БД
        # Для этого нужно знать hardware_id из payload или другую информацию
        # Пока используем временный топик, который будет работать для всех устройств
        
        # Формируем команду set_time
        command_payload = {
            "cmd": "set_time",
            "cmd_id": f"time_sync_{uuid.uuid4().hex[:8]}",
            "params": {
                "unix_ts": server_time
            }
        }
        
        # Публикуем в широковещательный топик для всех устройств, которые запросили время
        # Устройства должны подписаться на hydro/time/response или использовать другой механизм
        # Временно используем временный топик, который устройство может использовать
        # для получения времени при первом подключении
        
        # Альтернативный подход: публикуем в топик, на который подписаны все устройства
        # Используем топик hydro/time/response для широковещательной рассылки времени
        broadcast_topic = "hydro/time/response"
        response_payload = {
            "message_type": "time_response",
            "unix_ts": server_time,
            "server_time": server_time
        }
        
        # Публикуем ответ
        mqtt._client.publish_json(broadcast_topic, response_payload, qos=1, retain=False)
        logger.info(
            f"[TIME_REQUEST] Sent time response: server_time={server_time}, "
            f"topic={broadcast_topic}"
        )
        
        # Также пытаемся отправить команду set_time напрямую, если знаем node_uid
        # Это можно сделать через mqtt-bridge API, но для простоты используем широковещательный ответ
        
    except Exception as e:
        logger.error(f"[TIME_REQUEST] Unexpected error processing time_request: {e}", exc_info=True)
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
        if _has_rows(rows):
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
        logger.info(f"[MQTT_PUBLISH] Publishing command to topic: {topic}, node_uid: {node_uid}, channel: {channel}, zone_id: {zone_id}, zone_segment: {zone_segment}, cmd_id={payload.get('cmd_id', 'unknown')}")
        
        # Используем базовый MQTT клиент для публикации
        base_client = mqtt_client._client
        import json as json_lib
        command_json = json_lib.dumps(payload, separators=(",", ":"))
        result = base_client._client.publish(topic, command_json, qos=1, retain=False)
        if result.rc != 0:
            logger.error(f"[MQTT_PUBLISH] FAILED: MQTT publish failed with rc={result.rc} for topic {topic}, cmd_id={payload.get('cmd_id', 'unknown')}")
            raise RuntimeError(f"MQTT publish failed with rc={result.rc} for topic {topic}")
        logger.info(f"[MQTT_PUBLISH] SUCCESS: Command published successfully to {topic}, cmd_id={payload.get('cmd_id', 'unknown')}, payload_size={len(command_json)}")
        
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
    type: Optional[str] = Field(None, max_length=64, description="Command type (legacy)")
    cmd: Optional[str] = Field(None, max_length=64, description="Command name (new format)")
    params: Dict[str, Any] = Field(default_factory=dict, description="Command parameters")
    source: Optional[str] = Field(None, max_length=64, description="Command source (automation/api/device)")
    node_uid: Optional[str] = Field(None, max_length=128, description="Node UID")
    channel: Optional[str] = Field(None, max_length=64, description="Channel name")
    greenhouse_uid: Optional[str] = Field(None, max_length=128, description="Greenhouse UID")
    zone_id: Optional[int] = Field(None, ge=1, description="Zone ID")
    zone_uid: Optional[str] = Field(None, max_length=128, description="Zone UID")
    hardware_id: Optional[str] = Field(None, max_length=128, description="Hardware ID for temporary topic")
    cmd_id: Optional[str] = Field(None, max_length=64, description="Command ID from Laravel")
    ts: Optional[int] = Field(None, description="Command timestamp (seconds)")
    sig: Optional[str] = Field(None, max_length=128, description="Command HMAC signature (hex)")
    trace_id: Optional[str] = Field(None, max_length=64, description="Trace ID for logging")
    
    def get_command_name(self) -> str:
        """Get command name from either 'cmd' or 'type' field."""
        return self.cmd or self.type or ""


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
    
    # Проверяем что команда указана
    if not req.get_command_name():
        raise HTTPException(status_code=400, detail="Either 'cmd' or 'type' must be provided")
    
    # Получаем zone_uid из БД, если mqtt_zone_format="uid"
    zone_uid = None
    s = get_settings()
    if hasattr(s, 'mqtt_zone_format') and s.mqtt_zone_format == "uid":
        zone_uid = await _get_zone_uid_from_id(zone_id)
    command_source = req.source or "api"
    
    # Создаем payload для команды
    try:
        payload = _create_command_payload(
            cmd_type=req.type,
            cmd=req.cmd,
            cmd_id=req.cmd_id,
            params=req.params,
            ts=req.ts,
            sig=req.sig
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    cmd_id = payload["cmd_id"]
    
    # Получаем MQTT клиент
    mqtt = await get_mqtt_client()
    
    # Проверяем статус команды перед публикацией (идемпотентность)
    # Если команда уже в терминальном статусе (ack/done/failed), не публикуем повторно
    try:
        existing_cmd = await fetch("SELECT status, source FROM commands WHERE cmd_id = $1", cmd_id)
        if existing_cmd:
            cmd_status = existing_cmd[0].get("status", "").lower()
            # Если команда уже есть, но без source - задаем его (для обратной совместимости)
            if not existing_cmd[0].get("source") and command_source:
                try:
                    await execute("UPDATE commands SET source = $1 WHERE cmd_id = $2", command_source, cmd_id)
                except Exception:
                    logger.warning(f"[COMMAND_PUBLISH] Failed to backfill source for command {cmd_id}")
            # Терминальные статусы: ack, done, failed
            if cmd_status in ("ack", "done", "failed"):
                logger.info(
                    f"[IDEMPOTENCY] Command {cmd_id} already in terminal status '{cmd_status}', "
                    f"skipping republish to prevent duplicate physical actions"
                )
                return {
                    "status": "ok",
                    "data": {
                        "command_id": cmd_id,
                        "message": f"Command already in terminal status: {cmd_status}",
                        "skipped": True
                    }
                }
        else:
            # Команда не существует - создаем со статусом QUEUED
            node_rows = await fetch("SELECT id FROM nodes WHERE uid = $1 AND zone_id = $2", req.node_uid, zone_id)
            node_id = node_rows[0]["id"] if node_rows else None
            await execute(
                """
                INSERT INTO commands (zone_id, node_id, channel, cmd, params, status, source, cmd_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, 'QUEUED', $6, $7, NOW(), NOW())
                ON CONFLICT (cmd_id) DO NOTHING
                """,
                zone_id, node_id, req.channel, req.get_command_name(), req.params or {}, command_source, cmd_id
            )
    except Exception as e:
        logger.warning(f"Failed to check/ensure command in DB: {e}")
    
    # Публикуем с ретраями
    max_retries = 3
    retry_delays = [0.5, 1.0, 2.0]
    publish_success = False
    last_error = None
    
    for attempt in range(max_retries):
        try:
            await publish_command_mqtt(mqtt, req.greenhouse_uid, zone_id, req.node_uid, req.channel, payload, hardware_id=req.hardware_id, zone_uid=zone_uid)
            publish_success = True
            break
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delays[attempt])
    
    if publish_success:
        await mark_command_sent(cmd_id, allow_resend=True)
        try:
            await send_status_to_laravel(cmd_id, "SENT", {"zone_id": zone_id, "node_uid": req.node_uid, "channel": req.channel})
        except Exception:
            pass
        return {"status": "ok", "data": {"command_id": cmd_id}}
    else:
        await mark_command_send_failed(cmd_id, str(last_error))
        raise HTTPException(status_code=500, detail=f"Failed to publish command: {str(last_error)}")


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
    logger.info(f"[COMMAND_PUBLISH_ENDPOINT] STEP 0: Received command publish request: node_uid={node_uid}, cmd={req.get_command_name()}, channel={req.channel}, zone_id={req.zone_id}, gh_uid={req.greenhouse_uid}")
    # Аутентификация
    _auth_ingest(request)
    logger.info(f"[COMMAND_PUBLISH_ENDPOINT] STEP 1: Authentication passed for node_uid={node_uid}")
    
    if not (req.greenhouse_uid and req.zone_id and req.channel):
        raise HTTPException(status_code=400, detail="greenhouse_uid, zone_id and channel are required")
    
    # Проверяем что команда указана
    if not req.get_command_name():
        raise HTTPException(status_code=400, detail="Either 'cmd' or 'type' must be provided")
    
    # Получаем zone_uid из БД, если mqtt_zone_format="uid"
    zone_uid = None
    s = get_settings()
    if hasattr(s, 'mqtt_zone_format') and s.mqtt_zone_format == "uid" and req.zone_id:
        zone_uid = await _get_zone_uid_from_id(req.zone_id)
    command_source = req.source or "api"
    
    # Создаем payload для команды
    try:
        payload = _create_command_payload(
            cmd_type=req.type,
            cmd=req.cmd,
            cmd_id=req.cmd_id,
            params=req.params,
            ts=req.ts,
            sig=req.sig
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    cmd_id = payload["cmd_id"]
    
    # Получаем MQTT клиент
    mqtt = await get_mqtt_client()
    
    # Проверяем статус команды перед публикацией (идемпотентность)
    # Если команда уже в терминальном статусе (ack/done/failed), не публикуем повторно
    try:
        existing_cmd = await fetch("SELECT status, source FROM commands WHERE cmd_id = $1", cmd_id)
        if existing_cmd:
            cmd_status = existing_cmd[0].get("status", "").lower()
            if not existing_cmd[0].get("source") and command_source:
                try:
                    await execute("UPDATE commands SET source = $1 WHERE cmd_id = $2", command_source, cmd_id)
                except Exception:
                    logger.warning(f"[COMMAND_PUBLISH] Failed to backfill source for command {cmd_id}")
            # Терминальные статусы: ack, done, failed
            if cmd_status in ("ack", "done", "failed"):
                logger.info(
                    f"[IDEMPOTENCY] Command {cmd_id} already in terminal status '{cmd_status}', "
                    f"skipping republish to prevent duplicate physical actions"
                )
                return {
                    "status": "ok",
                    "data": {
                        "command_id": cmd_id,
                        "message": f"Command already in terminal status: {cmd_status}",
                        "skipped": True
                    }
                }
        else:
            # Команда не существует - создаем со статусом QUEUED
            node_rows = await fetch("SELECT id FROM nodes WHERE uid = $1 AND zone_id = $2", node_uid, req.zone_id)
            node_id = node_rows[0]["id"] if node_rows else None
            await execute(
                """
                INSERT INTO commands (zone_id, node_id, channel, cmd, params, status, source, cmd_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, 'QUEUED', $6, $7, NOW(), NOW())
                ON CONFLICT (cmd_id) DO NOTHING
                """,
                req.zone_id, node_id, req.channel, req.get_command_name(), req.params or {}, command_source, cmd_id
            )
    except Exception as e:
        logger.warning(f"Failed to check/ensure command in DB: {e}")
    
    # Публикуем с ретраями
    max_retries = 3
    retry_delays = [0.5, 1.0, 2.0]
    publish_success = False
    last_error = None
    
    for attempt in range(max_retries):
        try:
            logger.info(f"[COMMAND_PUBLISH] Attempt {attempt + 1}/{max_retries} to publish command {cmd_id} to MQTT")
            await publish_command_mqtt(mqtt, req.greenhouse_uid, req.zone_id, node_uid, req.channel, payload, hardware_id=req.hardware_id, zone_uid=zone_uid)
            publish_success = True
            logger.info(f"[COMMAND_PUBLISH] Command {cmd_id} published successfully on attempt {attempt + 1}")
            break
        except Exception as e:
            last_error = e
            logger.warning(f"[COMMAND_PUBLISH] Failed to publish command {cmd_id} on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delays[attempt])
    
    logger.info(f"[COMMAND_PUBLISH] STEP 1: After publish loop: publish_success={publish_success}, cmd_id={cmd_id}, last_error={last_error}")
    
    if publish_success:
        logger.info(f"[COMMAND_PUBLISH] STEP 2: Command {cmd_id} published successfully to MQTT, starting status update to SENT")
        logger.info(f"[COMMAND_PUBLISH] STEP 2.1: Command details: node_uid={node_uid}, zone_id={req.zone_id}, channel={req.channel}")
        
        # Проверяем статус команды перед обновлением
        logger.info(f"[COMMAND_PUBLISH] STEP 3: Checking command status in DB before update, cmd_id={cmd_id}")
        try:
            from common.db import fetch
            current_cmd = await fetch("SELECT status, sent_at, updated_at FROM commands WHERE cmd_id = $1", cmd_id)
            if current_cmd:
                logger.info(f"[COMMAND_PUBLISH] STEP 3.1: Command {cmd_id} found in DB: status={current_cmd[0].get('status')}, sent_at={current_cmd[0].get('sent_at')}, updated_at={current_cmd[0].get('updated_at')}")
            else:
                logger.warning(f"[COMMAND_PUBLISH] STEP 3.2: Command {cmd_id} NOT FOUND in database before mark_command_sent!")
        except Exception as e:
            logger.error(f"[COMMAND_PUBLISH] STEP 3.3: ERROR checking command status before update: {e}", exc_info=True)
        
        logger.info(f"[COMMAND_PUBLISH] STEP 4: Calling mark_command_sent for cmd_id={cmd_id}, allow_resend=True")
        await mark_command_sent(cmd_id, allow_resend=True)
        logger.info(f"[COMMAND_PUBLISH] STEP 4.1: mark_command_sent completed for cmd_id={cmd_id}")
        
        # Проверяем статус команды после обновления
        logger.info(f"[COMMAND_PUBLISH] STEP 5: Checking command status in DB after mark_command_sent, cmd_id={cmd_id}")
        try:
            updated_cmd = await fetch("SELECT status, sent_at, updated_at FROM commands WHERE cmd_id = $1", cmd_id)
            if updated_cmd:
                logger.info(f"[COMMAND_PUBLISH] STEP 5.1: Command {cmd_id} status after mark_command_sent: status={updated_cmd[0].get('status')}, sent_at={updated_cmd[0].get('sent_at')}, updated_at={updated_cmd[0].get('updated_at')}")
            else:
                logger.error(f"[COMMAND_PUBLISH] STEP 5.2: Command {cmd_id} NOT FOUND in database after mark_command_sent!")
        except Exception as e:
            logger.error(f"[COMMAND_PUBLISH] STEP 5.3: ERROR checking command status after update: {e}", exc_info=True)
        
        logger.info(f"[COMMAND_PUBLISH] STEP 6: Sending SENT status to Laravel for cmd_id={cmd_id}")
        try:
            await send_status_to_laravel(cmd_id, "SENT", {"zone_id": req.zone_id, "node_uid": node_uid, "channel": req.channel})
            logger.info(f"[COMMAND_PUBLISH] STEP 6.1: Command {cmd_id} SENT status successfully sent to Laravel")
        except Exception as e:
            logger.error(f"[COMMAND_PUBLISH] STEP 6.2: ERROR sending SENT status to Laravel for command {cmd_id}: {e}", exc_info=True)
        
        logger.info(f"[COMMAND_PUBLISH] STEP 7: Returning success response for cmd_id={cmd_id}")
        return {"status": "ok", "data": {"command_id": cmd_id}}
    else:
        await mark_command_send_failed(cmd_id, str(last_error))
        raise HTTPException(status_code=500, detail=f"Failed to publish command: {str(last_error)}")


@app.post("/commands")
async def publish_command(
    request: Request,
    req: CommandRequest = Body(...),
):
    """
    Универсальный endpoint для публикации команд через history-logger.
    Все общение бэка с нодами должно происходить через history-logger.
    
    Поддерживает оба формата:
    - Новый: {"cmd": "set_ph", "params": {...}, "greenhouse_uid": "...", "zone_id": 1, "node_uid": "...", "channel": "..."}
    - Legacy: {"type": "set_ph", ...}
    """
    # Аутентификация
    _auth_ingest(request)
    
    # Валидация обязательных полей
    if not req.get_command_name():
        raise HTTPException(status_code=400, detail="Either 'cmd' or 'type' must be provided")
    
    if not (req.greenhouse_uid and req.zone_id and req.node_uid and req.channel):
        raise HTTPException(
            status_code=400, 
            detail="greenhouse_uid, zone_id, node_uid and channel are required"
        )
    
    # Получаем zone_uid из БД, если mqtt_zone_format="uid"
    zone_uid = None
    s = get_settings()
    if hasattr(s, 'mqtt_zone_format') and s.mqtt_zone_format == "uid":
        zone_uid = await _get_zone_uid_from_id(req.zone_id)
    command_source = req.source or "api"
    
    # Извлекаем cmd_id из params, если он не передан напрямую
    cmd_id = req.cmd_id
    if not cmd_id and req.params and 'cmd_id' in req.params:
        cmd_id = req.params.get('cmd_id')
        # Удаляем cmd_id из params, чтобы не дублировать его в payload
        params_without_cmd_id = {k: v for k, v in req.params.items() if k != 'cmd_id'}
    else:
        params_without_cmd_id = req.params
    
    # Создаем payload для команды
    try:
        payload = _create_command_payload(
            cmd_type=req.type, 
            cmd=req.cmd, 
            cmd_id=cmd_id, 
            params=params_without_cmd_id,
            ts=req.ts,
            sig=req.sig
        )
        cmd_id = payload["cmd_id"]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Логирование с trace_id если есть
    log_context = {
        "zone_id": req.zone_id,
        "node_uid": req.node_uid,
        "channel": req.channel,
        "cmd_id": cmd_id,
        "command": req.get_command_name(),
        "source": command_source
    }
    if req.trace_id:
        log_context["trace_id"] = req.trace_id
    
    logger.info(
        f"Publishing command via /commands endpoint: {log_context}",
        extra=log_context
    )
    
    # ШАГ 1: Проверяем статус команды перед публикацией (идемпотентность)
    # Если команда уже в терминальном статусе (ack/done/failed), не публикуем повторно
    try:
        # Проверяем, существует ли команда в БД и её статус
        existing_cmd = await fetch(
            """
            SELECT status, source FROM commands WHERE cmd_id = $1
            """,
            cmd_id
        )
        
        if existing_cmd:
            cmd_status = existing_cmd[0].get("status", "").lower()
            if not existing_cmd[0].get("source") and command_source:
                try:
                    await execute("UPDATE commands SET source = $1 WHERE cmd_id = $2", command_source, cmd_id)
                except Exception:
                    logger.warning(f"[COMMAND_PUBLISH] Failed to backfill source for command {cmd_id}")
            # Терминальные статусы: ack, done, failed
            if cmd_status in ("ack", "done", "failed"):
                logger.info(
                    f"[IDEMPOTENCY] Command {cmd_id} already in terminal status '{cmd_status}', "
                    f"skipping republish to prevent duplicate physical actions"
                )
                return {
                    "status": "ok",
                    "data": {
                        "command_id": cmd_id,
                        "message": f"Command already in terminal status: {cmd_status}",
                        "skipped": True
                    }
                }
        
        if not existing_cmd:
            # Команда не существует - создаем её со статусом QUEUED
            # Получаем node_id из node_uid
            node_rows = await fetch(
                """
                SELECT id FROM nodes WHERE uid = $1 AND zone_id = $2
                """,
                req.node_uid,
                req.zone_id
            )
            node_id = node_rows[0]["id"] if node_rows else None
            
            await execute(
                """
                INSERT INTO commands (zone_id, node_id, channel, cmd, params, status, source, cmd_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, 'QUEUED', $6, $7, NOW(), NOW())
                ON CONFLICT (cmd_id) DO NOTHING
                """,
                req.zone_id,
                node_id,
                req.channel,
                req.get_command_name(),
                params_without_cmd_id,
                command_source,
                cmd_id
            )
            logger.info(f"Command {cmd_id} created in DB with status QUEUED")
        else:
            current_status = existing_cmd[0]["status"]
            if current_status not in ('QUEUED', 'SEND_FAILED'):
                logger.warning(
                    f"Command {cmd_id} already exists with status {current_status}, "
                    f"cannot republish. Skipping."
                )
                return {
                    "status": "ok",
                    "data": {
                        "command_id": cmd_id,
                        "zone_id": req.zone_id,
                        "node_uid": req.node_uid,
                        "channel": req.channel,
                        "note": f"Command already exists with status {current_status}"
                    }
                }
    except Exception as e:
        logger.error(f"Failed to ensure command in DB: {e}", exc_info=True, extra=log_context)
        # Продолжаем выполнение, возможно команда уже существует
    
    # ШАГ 2: Публикуем команду в MQTT с ретраями и backoff
    mqtt = await get_mqtt_client()
    max_retries = 3
    retry_delays = [0.5, 1.0, 2.0]  # Exponential backoff
    
    publish_success = False
    last_error = None
    
    for attempt in range(max_retries):
        try:
            await publish_command_mqtt(
                mqtt,
                req.greenhouse_uid,
                req.zone_id,
                req.node_uid,
                req.channel,
                payload,
                hardware_id=req.hardware_id,
                zone_uid=zone_uid
            )
            publish_success = True
            logger.info(f"Command published successfully (attempt {attempt + 1}/{max_retries}): {log_context}")
            break
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = retry_delays[attempt]
                logger.warning(
                    f"Failed to publish command (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {delay}s...",
                    extra=log_context
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"Failed to publish command after {max_retries} attempts: {e}",
                    exc_info=True,
                    extra=log_context
                )
    
    # ШАГ 3: Обновляем статус команды в БД
    if publish_success:
        # Обновляем статус на SENT только после успешной публикации
        try:
            await mark_command_sent(cmd_id, allow_resend=True)
            logger.info(f"Command {cmd_id} status updated to SENT")
            
            # ШАГ 4: Отправляем подтверждение корреляции в backend через command_status_queue
            # Это гарантирует, что backend получит уведомление о статусе SENT
            try:
                await send_status_to_laravel(
                    cmd_id=cmd_id,
                    status="SENT",
                    details={
                        "zone_id": req.zone_id,
                        "node_uid": req.node_uid,
                        "channel": req.channel,
                        "command": req.get_command_name(),
                        "published_at": utcnow().isoformat()
                    }
                )
                logger.debug(f"Correlation ACK sent for command {cmd_id} (status: SENT)")
            except Exception as e:
                # Ошибка отправки ACK не критична - команда уже в БД со статусом SENT
                # Воркер ретраев доставит статус позже
                logger.warning(f"Failed to send correlation ACK for command {cmd_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to update command status to SENT: {e}", exc_info=True, extra=log_context)
        
        # Метрики
        COMMANDS_SENT.labels(zone_id=str(req.zone_id), metric=req.get_command_name()).inc()
        
        return {
            "status": "ok", 
            "data": {
                "command_id": cmd_id,
                "zone_id": req.zone_id,
                "node_uid": req.node_uid,
                "channel": req.channel
            }
        }
    else:
        # Публикация не удалась - обновляем статус на SEND_FAILED
        try:
            await mark_command_send_failed(cmd_id, str(last_error))
            logger.error(f"Command {cmd_id} status updated to SEND_FAILED")
        except Exception as e:
            logger.error(f"Failed to update command status to SEND_FAILED: {e}", exc_info=True)
        
        MQTT_PUBLISH_ERRORS.labels(error_type=type(last_error).__name__).inc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to publish command after {max_retries} attempts: {str(last_error)}"
        )


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
    _validate_target_level(req.target_level, 0.1, 1.0, "fill")
    
    # Get greenhouse uid
    gh_uid = await _get_gh_uid_from_zone_id(zone_id)
    
    # Используем синхронный MqttClient, так как water_flow функции ожидают его
    async with _mqtt_client_context("-fill") as mqtt:
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
    _validate_target_level(req.target_level, 0.0, 0.9, "drain")
    
    # Get greenhouse uid
    gh_uid = await _get_gh_uid_from_zone_id(zone_id)
    
    # Используем синхронный MqttClient, так как water_flow функции ожидают его
    async with _mqtt_client_context("-drain") as mqtt:
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
    gh_uid = await _get_gh_uid_from_zone_id(zone_id)
    
    # Используем синхронный MqttClient, так как water_flow функции ожидают его
    async with _mqtt_client_context("-calibrate") as mqtt:
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
            ts = utcnow()
        
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
