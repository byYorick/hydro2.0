"""
Унифицированная система очередей для надёжной доставки сообщений в Laravel backend.

Поддерживает:
- telemetry_in: входящая телеметрия
- status_updates: обновления статусов команд
- alerts: алерты
- telemetry_dlq: dead letter queue для телеметрии

Обеспечивает:
- Персистентность через PostgreSQL (гарантия отсутствия потерь)
- Dead Letter Queue (DLQ) для всех типов
- Метрики Prometheus для мониторинга
- Exponential backoff при ретраях
- Graceful shutdown
"""
import asyncio
import json
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from enum import Enum

import httpx

from .db import get_pool, execute, fetch
from .env import get_settings
from .trace_context import inject_trace_id_header

logger = logging.getLogger(__name__)

# Глобальное хранилище метрик Prometheus (на уровне модуля)
_global_metrics: Dict[str, Dict[str, Any]] = {}


class QueueType(str, Enum):
    """Типы очередей."""
    TELEMETRY_IN = "telemetry_in"
    STATUS_UPDATES = "status_updates"
    ALERTS = "alerts"
    TELEMETRY_DLQ = "telemetry_dlq"


class MessageStatus(str, Enum):
    """Статусы сообщений."""
    PENDING = "pending"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    FAILED = "failed"
    DLQ = "dlq"


class UnifiedQueue:
    """Унифицированная очередь с персистентностью через PostgreSQL."""
    
    MAX_RETRIES = 10
    BASE_RETRY_DELAY = 1.0  # секунды
    MAX_RETRY_DELAY = 300.0  # секунды
    
    def __init__(self, queue_type: QueueType):
        self.queue_type = queue_type
        self._initialized = False
    
    async def ensure_table(self):
        """Создаёт таблицу для очереди, если её нет."""
        if self._initialized:
            return
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Основная таблица очереди
            table_name = f"queue_{self.queue_type.value}"
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id BIGSERIAL PRIMARY KEY,
                    payload JSONB NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    status VARCHAR(16) NOT NULL DEFAULT 'pending' 
                        CHECK (status IN ('pending', 'processing', 'delivered', 'failed', 'dlq')),
                    next_retry_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    delivered_at TIMESTAMP WITH TIME ZONE,
                    error_message TEXT
                )
            """)
            
            # Индексы для производительности
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_status_retry 
                ON {table_name}(status, next_retry_at) 
                WHERE status IN ('pending', 'processing', 'failed')
            """)
            
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_created_at 
                ON {table_name}(created_at)
            """)
            
            # DLQ таблица (если это не сама DLQ)
            if self.queue_type != QueueType.TELEMETRY_DLQ:
                dlq_table_name = f"queue_{self.queue_type.value}_dlq"
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {dlq_table_name} (
                        id BIGSERIAL PRIMARY KEY,
                        original_id BIGINT,
                        payload JSONB NOT NULL,
                        retry_count INTEGER,
                        error_message TEXT,
                        failed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)
                
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{dlq_table_name}_failed_at 
                    ON {dlq_table_name}(failed_at)
                """)
        
        self._initialized = True
        logger.info(f"Queue table initialized for {self.queue_type.value}")
    
    async def enqueue(self, payload: Dict[str, Any]) -> Optional[int]:
        """
        Добавляет сообщение в очередь.
        
        Args:
            payload: Данные сообщения (JSON-совместимый словарь)
            
        Returns:
            ID созданной записи или None при ошибке
        """
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            try:
                payload_json = json.dumps(payload)
                result = await conn.fetchval(f"""
                    INSERT INTO queue_{self.queue_type.value} 
                        (payload, status, next_retry_at)
                    VALUES ($1, 'pending', NOW())
                    RETURNING id
                """, payload_json)
                
                # Инкрементируем метрику enqueued
                await self._inc_metric('enqueued_total')
                
                return result
            except Exception as e:
                logger.error(f"Failed to enqueue message to {self.queue_type.value}: {e}", exc_info=True)
                return None
    
    async def get_pending(self, limit: int = 100) -> List[Tuple[int, Dict[str, Any], int]]:
        """
        Получает сообщения, готовые к обработке.
        
        Returns:
            Список кортежей (id, payload, retry_count)
        """
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT id, payload, retry_count
                FROM queue_{self.queue_type.value}
                WHERE status = 'pending' AND (next_retry_at IS NULL OR next_retry_at <= NOW())
                ORDER BY created_at ASC, id ASC
                LIMIT $1
                FOR UPDATE SKIP LOCKED
            """, limit)
        
        result = []
        for row in rows:
            payload = json.loads(row['payload']) if isinstance(row['payload'], str) else row['payload']
            result.append((row['id'], payload, row['retry_count']))
        
        return result
    
    async def mark_processing(self, message_id: int):
        """Отмечает сообщение как обрабатываемое."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"""
                UPDATE queue_{self.queue_type.value}
                SET status = 'processing', updated_at = NOW()
                WHERE id = $1
            """, message_id)
    
    async def mark_delivered(self, message_id: int):
        """Отмечает сообщение как доставленное."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"""
                UPDATE queue_{self.queue_type.value}
                SET status = 'delivered', 
                    delivered_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1
            """, message_id)
        
        # Обновляем метрики
        await self._update_metrics()
    
    async def mark_failed(self, message_id: int, error_message: str, retry_count: int):
        """
        Отмечает сообщение как неудачное и планирует ретрай или отправляет в DLQ.
        
        Args:
            message_id: ID сообщения
            error_message: Сообщение об ошибке
            retry_count: Текущее количество попыток
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            if retry_count >= self.MAX_RETRIES:
                # Отправляем в DLQ
                await self._move_to_dlq(conn, message_id, error_message, retry_count)
                await conn.execute(f"""
                    UPDATE queue_{self.queue_type.value}
                    SET status = 'dlq', updated_at = NOW()
                    WHERE id = $1
                """, message_id)
            else:
                # Планируем ретрай
                backoff_seconds = self._calculate_backoff(retry_count)
                from datetime import timezone
                next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
                
                await conn.execute(f"""
                    UPDATE queue_{self.queue_type.value}
                    SET status = 'failed',
                        retry_count = $1,
                        next_retry_at = $2,
                        error_message = $3,
                        updated_at = NOW()
                    WHERE id = $4
                """, retry_count + 1, next_retry_at, error_message, message_id)
        
        # Инкрементируем метрику failed при достижении лимита ретраев
        if retry_count + 1 >= self.MAX_RETRIES:
            await self._inc_metric('failed_total')
    
    async def _move_to_dlq(self, conn, message_id: int, error_message: str, retry_count: int):
        """Перемещает сообщение в Dead Letter Queue."""
        if self.queue_type == QueueType.TELEMETRY_DLQ:
            # Не перемещаем из DLQ в DLQ
            return
        
        # Получаем payload
        row = await conn.fetchrow(f"""
            SELECT payload FROM queue_{self.queue_type.value} WHERE id = $1
        """, message_id)
        
        if row:
            dlq_table_name = f"queue_{self.queue_type.value}_dlq"
            await conn.execute(f"""
                INSERT INTO {dlq_table_name} 
                    (original_id, payload, retry_count, error_message, failed_at)
                VALUES ($1, $2, $3, $4, NOW())
            """, message_id, row['payload'], retry_count, error_message)
            
            logger.warning(
                f"Message {message_id} moved to DLQ for queue {self.queue_type.value} "
                f"after {retry_count} retries. Error: {error_message}"
            )
    
    def _calculate_backoff(self, retry_count: int) -> float:
        """Вычисляет задержку для exponential backoff."""
        delay = self.BASE_RETRY_DELAY * (2 ** retry_count)
        return min(delay, self.MAX_RETRY_DELAY)
    
    async def get_stats(self) -> Dict[str, Any]:
        """Получает статистику очереди."""
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            stats = await conn.fetchrow(f"""
                SELECT 
                    COUNT(*) FILTER (WHERE status = 'pending') as pending_count,
                    COUNT(*) FILTER (WHERE status = 'processing') as processing_count,
                    COUNT(*) FILTER (WHERE status = 'delivered') as delivered_count,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed_count,
                    COUNT(*) FILTER (WHERE status = 'dlq') as dlq_count,
                    COUNT(*) as total_count
                FROM queue_{self.queue_type.value}
            """)
            
            # Получаем размер DLQ
            dlq_count = 0
            if self.queue_type != QueueType.TELEMETRY_DLQ:
                dlq_stats = await conn.fetchrow(f"""
                    SELECT COUNT(*) as count
                    FROM queue_{self.queue_type.value}_dlq
                """)
                if dlq_stats:
                    dlq_count = dlq_stats['count']
            
            return {
                'queue_type': self.queue_type.value,
                'pending': stats['pending_count'],
                'processing': stats['processing_count'],
                'delivered': stats['delivered_count'],
                'failed': stats['failed_count'],
                'dlq': stats['dlq_count'],
                'dlq_total': dlq_count,
                'total': stats['total_count']
            }
    
    async def _update_metrics(self):
        """Обновляет метрики Prometheus."""
        try:
            from prometheus_client import Gauge, Counter
            
            # Создаём метрики если их нет (используем класс как ключ для глобального хранилища)
            metrics_key = f"queue_{self.queue_type.value}"
            
            # Используем глобальное хранилище метрик на уровне модуля
            global _global_metrics
            
            if metrics_key not in _global_metrics:
                try:
                    _global_metrics[metrics_key] = {
                        'size': Gauge(
                            f"{metrics_key}_size",
                            f"Current size of {self.queue_type.value} queue",
                            ['status']
                        ),
                        'dlq_size': Gauge(
                            f"{metrics_key}_dlq_size",
                            f"Current size of {self.queue_type.value} DLQ"
                        ),
                        'enqueued_total': Counter(
                            f"{metrics_key}_enqueued_total",
                            f"Total messages enqueued to {self.queue_type.value}"
                        ),
                        'delivered_total': Counter(
                            f"{metrics_key}_delivered_total",
                            f"Total messages delivered from {self.queue_type.value}"
                        ),
                        'failed_total': Counter(
                            f"{metrics_key}_failed_total",
                            f"Total messages failed in {self.queue_type.value}"
                        ),
                    }
                except ValueError:
                    # Метрики уже существуют - используем заглушки
                    class _NoOp:
                        def set(self, *args, **kwargs): pass
                        def inc(self, *args, **kwargs): pass
                        def labels(self, *args, **kwargs): return self
                    _global_metrics[metrics_key] = {
                        'size': _NoOp(),
                        'dlq_size': _NoOp(),
                        'enqueued_total': _NoOp(),
                        'delivered_total': _NoOp(),
                        'failed_total': _NoOp(),
                    }
            
            metrics = _global_metrics[metrics_key]
            
            # Обновляем метрики на основе статистики
            stats = await self.get_stats()
            metrics['size'].labels(status='pending').set(stats['pending'])
            metrics['size'].labels(status='processing').set(stats['processing'])
            metrics['size'].labels(status='failed').set(stats['failed'])
            metrics['dlq_size'].set(stats['dlq_total'])
            
        except ImportError:
            # Prometheus не установлен - пропускаем
            pass
        except Exception as e:
            logger.debug(f"Failed to update metrics: {e}")
    
    async def _inc_metric(self, metric_name: str):
        """Инкрементирует счётчик метрики."""
        try:
            from prometheus_client import Counter
            
            metrics_key = f"queue_{self.queue_type.value}"
            global _global_metrics
            
            if metrics_key not in _global_metrics:
                # Метрики ещё не созданы - создадим при следующем вызове _update_metrics
                return
            
            metrics = _global_metrics[metrics_key]
            if metric_name in metrics:
                metrics[metric_name].inc()
            
        except ImportError:
            # Prometheus не установлен - пропускаем
            pass
        except Exception as e:
            logger.debug(f"Failed to increment metric {metric_name}: {e}")


# Глобальные экземпляры очередей
_queues: Dict[QueueType, UnifiedQueue] = {}


def get_queue(queue_type: QueueType) -> UnifiedQueue:
    """Возвращает глобальный экземпляр очереди указанного типа."""
    if queue_type not in _queues:
        _queues[queue_type] = UnifiedQueue(queue_type)
    return _queues[queue_type]


# Глобальный httpx.AsyncClient
_http_client: Optional[httpx.AsyncClient] = None


async def get_http_client() -> httpx.AsyncClient:
    """Возвращает глобальный httpx.AsyncClient для процесса."""
    global _http_client
    
    if _http_client is None:
        s = get_settings()
        timeout = httpx.Timeout(10.0, connect=5.0)
        _http_client = httpx.AsyncClient(timeout=timeout)
        logger.info("Created global httpx.AsyncClient for queue delivery")
    
    return _http_client


async def close_http_client():
    """Закрывает глобальный httpx.AsyncClient."""
    global _http_client
    
    if _http_client is None:
        return
    
    await _http_client.aclose()
    _http_client = None
    logger.info("Closed global httpx.AsyncClient")


# Функции для отправки сообщений в Laravel

async def send_telemetry_to_laravel(payload: Dict[str, Any]) -> bool:
    """
    Отправляет телеметрию в Laravel API.
    При ошибке сохраняет в очередь telemetry_in.
    
    Args:
        payload: Данные телеметрии
        
    Returns:
        True если успешно отправлено, False если сохранено в очередь
    """
    s = get_settings()
    laravel_url = s.laravel_api_url if hasattr(s, 'laravel_api_url') else None
    
    if not laravel_url:
        logger.error("[TELEMETRY_DELIVERY] Laravel API URL not configured")
        queue = get_queue(QueueType.TELEMETRY_IN)
        await queue.enqueue(payload)
        return False
    
    ingest_token = (
        s.history_logger_api_token 
        if hasattr(s, 'history_logger_api_token') and s.history_logger_api_token 
        else (s.ingest_token if hasattr(s, 'ingest_token') else None)
    )
    
    headers = inject_trace_id_header(
        {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    )
    if ingest_token:
        headers["Authorization"] = f"Bearer {ingest_token}"
    
    try:
        client = await get_http_client()
        resp = await client.post(
            f"{laravel_url}/api/python/telemetry",
            headers=headers,
            json=payload,
        )
        
        if resp.status_code == 200:
            logger.debug(f"[TELEMETRY_DELIVERY] Telemetry delivered to Laravel")
            return True
        else:
            logger.warning(
                f"[TELEMETRY_DELIVERY] Laravel responded with {resp.status_code}: "
                f"{resp.text[:200]}"
            )
            queue = get_queue(QueueType.TELEMETRY_IN)
            await queue.enqueue(payload)
            return False
            
    except (httpx.TimeoutException, httpx.RequestError, httpx.NetworkError) as e:
        logger.warning(f"[TELEMETRY_DELIVERY] Network error: {e}")
        queue = get_queue(QueueType.TELEMETRY_IN)
        await queue.enqueue(payload)
        return False
    except Exception as e:
        logger.error(f"[TELEMETRY_DELIVERY] Unexpected error: {e}", exc_info=True)
        queue = get_queue(QueueType.TELEMETRY_IN)
        await queue.enqueue(payload)
        return False


async def send_status_update_to_laravel(payload: Dict[str, Any]) -> bool:
    """
    Отправляет обновление статуса команды в Laravel API.
    При ошибке сохраняет в очередь status_updates.
    
    Args:
        payload: Данные статуса (cmd_id, status, details)
        
    Returns:
        True если успешно отправлено, False если сохранено в очередь
    """
    s = get_settings()
    laravel_url = s.laravel_api_url if hasattr(s, 'laravel_api_url') else None
    
    if not laravel_url:
        logger.error("[STATUS_DELIVERY] Laravel API URL not configured")
        queue = get_queue(QueueType.STATUS_UPDATES)
        await queue.enqueue(payload)
        return False
    
    ingest_token = (
        s.history_logger_api_token 
        if hasattr(s, 'history_logger_api_token') and s.history_logger_api_token 
        else (s.ingest_token if hasattr(s, 'ingest_token') else None)
    )
    
    headers = inject_trace_id_header(
        {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    )
    if ingest_token:
        headers["Authorization"] = f"Bearer {ingest_token}"
    
    try:
        client = await get_http_client()
        resp = await client.post(
            f"{laravel_url}/api/python/commands/ack",
            headers=headers,
            json=payload,
        )
        
        if resp.status_code == 200:
            logger.debug(
                f"[STATUS_DELIVERY] Status update delivered to Laravel "
                f"for cmd_id={payload.get('cmd_id')}"
            )
            return True
        else:
            logger.warning(
                f"[STATUS_DELIVERY] Laravel responded with {resp.status_code}: "
                f"{resp.text[:200]}"
            )
            queue = get_queue(QueueType.STATUS_UPDATES)
            await queue.enqueue(payload)
            return False
            
    except (httpx.TimeoutException, httpx.RequestError, httpx.NetworkError) as e:
        logger.warning(f"[STATUS_DELIVERY] Network error: {e}")
        queue = get_queue(QueueType.STATUS_UPDATES)
        await queue.enqueue(payload)
        return False
    except Exception as e:
        logger.error(f"[STATUS_DELIVERY] Unexpected error: {e}", exc_info=True)
        queue = get_queue(QueueType.STATUS_UPDATES)
        await queue.enqueue(payload)
        return False


async def send_alert_to_laravel_unified(payload: Dict[str, Any]) -> bool:
    """
    Отправляет алерт в Laravel API.
    При ошибке сохраняет в очередь alerts.
    
    Args:
        payload: Данные алерта (zone_id, source, code, type, status, details)
        
    Returns:
        True если успешно отправлено, False если сохранено в очередь
    """
    s = get_settings()
    laravel_url = s.laravel_api_url if hasattr(s, 'laravel_api_url') else None
    
    if not laravel_url:
        logger.error("[ALERT_DELIVERY] Laravel API URL not configured")
        queue = get_queue(QueueType.ALERTS)
        await queue.enqueue(payload)
        return False
    
    ingest_token = (
        s.history_logger_api_token 
        if hasattr(s, 'history_logger_api_token') and s.history_logger_api_token 
        else (s.ingest_token if hasattr(s, 'ingest_token') else None)
    )
    
    headers = inject_trace_id_header(
        {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    )
    if ingest_token:
        headers["Authorization"] = f"Bearer {ingest_token}"
    
    try:
        client = await get_http_client()
        resp = await client.post(
            f"{laravel_url}/api/python/alerts",
            headers=headers,
            json=payload,
        )
        
        if resp.status_code == 200:
            logger.debug(
                f"[ALERT_DELIVERY] Alert '{payload.get('code')}' delivered to Laravel "
                f"for zone_id={payload.get('zone_id')}"
            )
            return True
        else:
            logger.warning(
                f"[ALERT_DELIVERY] Laravel responded with {resp.status_code}: "
                f"{resp.text[:200]}"
            )
            queue = get_queue(QueueType.ALERTS)
            await queue.enqueue(payload)
            return False
            
    except (httpx.TimeoutException, httpx.RequestError, httpx.NetworkError) as e:
        logger.warning(f"[ALERT_DELIVERY] Network error: {e}")
        queue = get_queue(QueueType.ALERTS)
        await queue.enqueue(payload)
        return False
    except Exception as e:
        logger.error(f"[ALERT_DELIVERY] Unexpected error: {e}", exc_info=True)
        queue = get_queue(QueueType.ALERTS)
        await queue.enqueue(payload)
        return False


# Воркеры для обработки очередей

async def queue_worker(
    queue_type: QueueType,
    send_func,
    interval: float = 30.0,
    batch_size: int = 50,
    shutdown_event: Optional[asyncio.Event] = None
):
    """
    Воркер для обработки очереди.
    
    Args:
        queue_type: Тип очереди для обработки
        send_func: Функция для отправки сообщения (принимает payload, возвращает bool)
        interval: Интервал между проверками очереди в секундах
        batch_size: Размер батча для обработки
        shutdown_event: Событие для graceful shutdown
    """
    logger.info(f"Starting {queue_type.value} queue worker")
    queue = get_queue(queue_type)
    
    while True:
        if shutdown_event and shutdown_event.is_set():
            logger.info(f"{queue_type.value} worker received shutdown signal")
            break
        
        try:
            # Получаем сообщения, готовые к обработке
            pending = await queue.get_pending(limit=batch_size)
            
            if not pending:
                if shutdown_event and shutdown_event.is_set():
                    break
                await asyncio.sleep(interval)
                continue
            
            logger.debug(f"[QUEUE_WORKER] Processing {len(pending)} messages from {queue_type.value}")
            
            for message_id, payload, retry_count in pending:
                if shutdown_event and shutdown_event.is_set():
                    logger.info(f"{queue_type.value} worker received shutdown signal during processing")
                    break
                
                try:
                    # Отмечаем как обрабатываемое
                    await queue.mark_processing(message_id)
                    
                    # Пытаемся отправить
                    success = await send_func(payload)
                    
                    if success:
                        # Успешно доставлено
                        await queue.mark_delivered(message_id)
                        logger.debug(
                            f"[QUEUE_WORKER] Successfully delivered message "
                            f"id={message_id} from {queue_type.value}"
                        )
                    else:
                        # Не удалось - планируем ретрай или отправляем в DLQ
                        error_msg = f"Failed to deliver message after {retry_count} retries"
                        await queue.mark_failed(message_id, error_msg, retry_count)
                
                except Exception as e:
                    logger.error(
                        f"[QUEUE_WORKER] Error processing message id={message_id} "
                        f"from {queue_type.value}: {e}",
                        exc_info=True
                    )
                    error_msg = str(e)
                    await queue.mark_failed(message_id, error_msg, retry_count)
            
            # Небольшая задержка перед следующей итерацией
            if shutdown_event and shutdown_event.is_set():
                break
            await asyncio.sleep(1.0)
            
        except Exception as e:
            logger.error(
                f"[QUEUE_WORKER] Unexpected error in {queue_type.value} worker: {e}",
                exc_info=True
            )
            if shutdown_event and shutdown_event.is_set():
                break
            await asyncio.sleep(interval)
    
    logger.info(f"{queue_type.value} worker stopped")


async def metrics_updater(interval: float = 60.0, shutdown_event: Optional[asyncio.Event] = None):
    """
    Периодически обновляет метрики размеров очередей.
    
    Args:
        interval: Интервал обновления метрик в секундах
        shutdown_event: Событие для graceful shutdown
    """
    logger.info("Starting queue metrics updater")
    
    while True:
        if shutdown_event and shutdown_event.is_set():
            logger.info("Metrics updater received shutdown signal")
            break
        
        try:
            # Обновляем метрики для всех очередей
            for queue_type in QueueType:
                queue = get_queue(queue_type)
                await queue._update_metrics()
            
            await asyncio.sleep(interval)
            
        except Exception as e:
            logger.error(f"Error in metrics updater: {e}", exc_info=True)
            if shutdown_event and shutdown_event.is_set():
                break
            await asyncio.sleep(interval)
    
    logger.info("Metrics updater stopped")
