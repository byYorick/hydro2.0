"""
Метрики для observability пайплайна.

Отслеживает:
- lag по очередям (pending_* size, oldest_age)
- command end-to-end latency (SENT→DONE/NO_EFFECT)
- error delivery latency (MQTT→WS)
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from .utils.time import utcnow
from prometheus_client import Gauge, Histogram, Counter

logger = logging.getLogger(__name__)

# Метрики lag по очередям
PENDING_ALERTS_SIZE = Gauge(
    "pipeline_pending_alerts_size",
    "Number of pending alerts in queue"
)

PENDING_ALERTS_OLDEST_AGE = Gauge(
    "pipeline_pending_alerts_oldest_age_seconds",
    "Age of oldest pending alert in seconds"
)

PENDING_STATUS_UPDATES_SIZE = Gauge(
    "pipeline_pending_status_updates_size",
    "Number of pending status updates in queue"
)

PENDING_STATUS_UPDATES_OLDEST_AGE = Gauge(
    "pipeline_pending_status_updates_oldest_age_seconds",
    "Age of oldest pending status update in seconds"
)

# Метрики command latency
COMMAND_E2E_LATENCY = Histogram(
    "pipeline_command_e2e_latency_seconds",
    "Command end-to-end latency from SENT to DONE/NO_EFFECT",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0]
)

COMMAND_SENT_TO_ACK_LATENCY = Histogram(
    "pipeline_command_sent_to_ack_latency_seconds",
    "Command latency from SENT to ACK",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

COMMAND_ACK_TO_DONE_LATENCY = Histogram(
    "pipeline_command_ack_to_done_latency_seconds",
    "Command latency from ACK to DONE/NO_EFFECT",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

# Метрики error delivery latency
ERROR_DELIVERY_LATENCY = Histogram(
    "pipeline_error_delivery_latency_seconds",
    "Error delivery latency from MQTT to WebSocket",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

ERROR_MQTT_TO_LARAVEL_LATENCY = Histogram(
    "pipeline_error_mqtt_to_laravel_latency_seconds",
    "Error latency from MQTT to Laravel API",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
)

ERROR_LARAVEL_TO_WS_LATENCY = Histogram(
    "pipeline_error_laravel_to_ws_latency_seconds",
    "Error latency from Laravel API to WebSocket",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0]
)

# Счетчики для отслеживания ошибок доставки
ERROR_DELIVERY_FAILED = Counter(
    "pipeline_error_delivery_failed_total",
    "Total number of failed error deliveries",
    ["stage"]  # stage: mqtt_to_laravel, laravel_to_ws
)

# Метрики health компонентов
MQTT_CONNECTED = Gauge(
    "pipeline_mqtt_connected",
    "MQTT connection status (1=connected, 0=disconnected)"
)

DB_CONNECTED = Gauge(
    "pipeline_db_connected",
    "Database connection status (1=connected, 0=disconnected)"
)

QUEUE_HEALTHY = Gauge(
    "pipeline_queue_healthy",
    "Queue health status (1=healthy, 0=unhealthy)",
    ["queue_name"]  # queue_name: alerts, status_updates
)

COMMAND_STATUS_REPAIR_TOTAL = Counter(
    "pipeline_command_status_repair_total",
    "Total number of command status repair outcomes",
    ["outcome", "command_status", "source", "replay_status"],
)

COMMAND_STATUS_REPAIR_LAST_SCAN_TS = Gauge(
    "pipeline_command_status_repair_last_scan_unixtime",
    "Unix timestamp of the last command status repair scan",
)

COMMAND_STATUS_REPAIR_LAST_SCAN_SCANNED = Gauge(
    "pipeline_command_status_repair_last_scan_scanned",
    "Number of stale commands scanned during the last command status repair pass",
)

COMMAND_STATUS_REPAIR_LAST_SCAN_REPAIRED = Gauge(
    "pipeline_command_status_repair_last_scan_repaired",
    "Number of stale commands repaired during the last command status repair pass",
)

COMMAND_STATUS_REPAIR_LAST_SCAN_REPLAY_FAILED = Gauge(
    "pipeline_command_status_repair_last_scan_replay_failed",
    "Number of stale commands whose replay delivery failed during the last repair pass",
)

COMMAND_STATUS_REPAIR_LAST_SCAN_NO_CORRELATION = Gauge(
    "pipeline_command_status_repair_last_scan_no_correlation",
    "Number of stale commands with no correlated terminal status during the last repair pass",
)

COMMAND_STATUS_RETRY_TOTAL = Counter(
    "pipeline_command_status_retry_total",
    "Total number of retry worker outcomes while delivering pending command statuses",
    ["outcome", "status"],
)

COMMAND_STATUS_RETRY_LAST_SCAN_TS = Gauge(
    "pipeline_command_status_retry_last_scan_unixtime",
    "Unix timestamp of the last retry worker scan",
)

COMMAND_STATUS_RETRY_LAST_SCAN_PROCESSED = Gauge(
    "pipeline_command_status_retry_last_scan_processed",
    "Number of pending status updates processed during the last retry worker pass",
)

COMMAND_STATUS_RETRY_LAST_SCAN_DELIVERED = Gauge(
    "pipeline_command_status_retry_last_scan_delivered",
    "Number of pending status updates delivered during the last retry worker pass",
)

COMMAND_STATUS_RETRY_LAST_SCAN_RETRY_SCHEDULED = Gauge(
    "pipeline_command_status_retry_last_scan_retry_scheduled",
    "Number of pending status updates rescheduled for retry during the last retry worker pass",
)

COMMAND_STATUS_RETRY_LAST_SCAN_DLQ_MOVED = Gauge(
    "pipeline_command_status_retry_last_scan_dlq_moved",
    "Number of pending status updates moved to DLQ during the last retry worker pass",
)

COMMAND_STATUS_RETRY_LAST_SCAN_DLQ_MOVE_FAILED = Gauge(
    "pipeline_command_status_retry_last_scan_dlq_move_failed",
    "Number of pending status updates that failed to move to DLQ during the last retry worker pass",
)


def update_queue_metrics(queue_name: str, size: int, oldest_age_seconds: float):
    """
    Обновляет метрики очереди.
    
    Args:
        queue_name: Имя очереди ('alerts' или 'status_updates')
        size: Размер очереди
        oldest_age_seconds: Возраст самой старой записи в секундах
    """
    if queue_name == 'alerts':
        PENDING_ALERTS_SIZE.set(size)
        PENDING_ALERTS_OLDEST_AGE.set(oldest_age_seconds)
    elif queue_name == 'status_updates':
        PENDING_STATUS_UPDATES_SIZE.set(size)
        PENDING_STATUS_UPDATES_OLDEST_AGE.set(oldest_age_seconds)
    else:
        logger.warning(f"Unknown queue name: {queue_name}")


def record_command_latency(sent_at: datetime, ack_at: Optional[datetime], done_at: Optional[datetime]):
    """
    Записывает метрики latency команды.
    
    Args:
        sent_at: Время отправки команды (SENT)
        ack_at: Время принятия команды (ACK), может быть None
        done_at: Время завершения команды (DONE/NO_EFFECT), может быть None
    """
    now = utcnow()
    
    if ack_at:
        sent_to_ack = (ack_at - sent_at).total_seconds()
        COMMAND_SENT_TO_ACK_LATENCY.observe(sent_to_ack)
    
    if done_at:
        if ack_at:
            ack_to_done = (done_at - ack_at).total_seconds()
            COMMAND_ACK_TO_DONE_LATENCY.observe(ack_to_done)
        
        e2e_latency = (done_at - sent_at).total_seconds()
        COMMAND_E2E_LATENCY.observe(e2e_latency)


def record_error_delivery_latency(mqtt_received_at: datetime, laravel_received_at: Optional[datetime], ws_sent_at: Optional[datetime]):
    """
    Записывает метрики latency доставки ошибки.
    
    Args:
        mqtt_received_at: Время получения ошибки из MQTT
        laravel_received_at: Время получения ошибки в Laravel API, может быть None
        ws_sent_at: Время отправки ошибки через WebSocket, может быть None
    """
    if laravel_received_at:
        mqtt_to_laravel = (laravel_received_at - mqtt_received_at).total_seconds()
        ERROR_MQTT_TO_LARAVEL_LATENCY.observe(mqtt_to_laravel)
    
    if ws_sent_at:
        if laravel_received_at:
            laravel_to_ws = (ws_sent_at - laravel_received_at).total_seconds()
            ERROR_LARAVEL_TO_WS_LATENCY.observe(laravel_to_ws)
        
        total_latency = (ws_sent_at - mqtt_received_at).total_seconds()
        ERROR_DELIVERY_LATENCY.observe(total_latency)


def record_error_delivery_failed(stage: str):
    """
    Записывает ошибку доставки.
    
    Args:
        stage: Стадия, на которой произошла ошибка ('mqtt_to_laravel' или 'laravel_to_ws')
    """
    ERROR_DELIVERY_FAILED.labels(stage=stage).inc()


def update_mqtt_health(connected: bool):
    """Обновляет метрику health MQTT."""
    MQTT_CONNECTED.set(1 if connected else 0)


def update_db_health(connected: bool):
    """Обновляет метрику health БД."""
    DB_CONNECTED.set(1 if connected else 0)


def update_queue_health(queue_name: str, healthy: bool):
    """
    Обновляет метрику health очереди.
    
    Args:
        queue_name: Имя очереди ('alerts' или 'status_updates')
        healthy: True если очередь здорова
    """
    QUEUE_HEALTHY.labels(queue_name=queue_name).set(1 if healthy else 0)


def record_command_status_repair(
    *,
    outcome: str,
    command_status: str,
    source: str,
    replay_status: str,
) -> None:
    """Инкрементирует счётчик исходов self-heal command status repair."""
    COMMAND_STATUS_REPAIR_TOTAL.labels(
        outcome=outcome,
        command_status=command_status,
        source=source,
        replay_status=replay_status,
    ).inc()


def update_command_status_repair_scan(*, scanned: int, repaired: int, replay_failed: int, no_correlation: int) -> None:
    """Обновляет gauges последнего прохода repair worker."""
    COMMAND_STATUS_REPAIR_LAST_SCAN_TS.set(utcnow().timestamp())
    COMMAND_STATUS_REPAIR_LAST_SCAN_SCANNED.set(scanned)
    COMMAND_STATUS_REPAIR_LAST_SCAN_REPAIRED.set(repaired)
    COMMAND_STATUS_REPAIR_LAST_SCAN_REPLAY_FAILED.set(replay_failed)
    COMMAND_STATUS_REPAIR_LAST_SCAN_NO_CORRELATION.set(no_correlation)


def record_command_status_retry(*, outcome: str, status: str) -> None:
    """Инкрементирует счётчик исходов retry worker."""
    COMMAND_STATUS_RETRY_TOTAL.labels(
        outcome=outcome,
        status=status,
    ).inc()


def update_command_status_retry_scan(
    *,
    processed: int,
    delivered: int,
    retry_scheduled: int,
    dlq_moved: int,
    dlq_move_failed: int,
) -> None:
    """Обновляет gauges последнего прохода retry worker."""
    COMMAND_STATUS_RETRY_LAST_SCAN_TS.set(utcnow().timestamp())
    COMMAND_STATUS_RETRY_LAST_SCAN_PROCESSED.set(processed)
    COMMAND_STATUS_RETRY_LAST_SCAN_DELIVERED.set(delivered)
    COMMAND_STATUS_RETRY_LAST_SCAN_RETRY_SCHEDULED.set(retry_scheduled)
    COMMAND_STATUS_RETRY_LAST_SCAN_DLQ_MOVED.set(dlq_moved)
    COMMAND_STATUS_RETRY_LAST_SCAN_DLQ_MOVE_FAILED.set(dlq_move_failed)
