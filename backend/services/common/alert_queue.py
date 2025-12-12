"""
Модуль для надёжной доставки алертов в Laravel API.

Обеспечивает:
- Персистентную очередь для алертов при ошибках API
- Воркер для ретраев с exponential backoff
- Единый httpx.AsyncClient на процесс
"""
import asyncio
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from .db import get_pool
from .env import get_settings
from .http_client_pool import make_request, calculate_backoff_with_jitter

logger = logging.getLogger(__name__)


class AlertQueue:
    """Персистентная очередь для алертов."""
    
    def __init__(self):
        self._initialized = False
    
    async def ensure_table(self):
        """Создаёт таблицу для очереди, если её нет."""
        if self._initialized:
            return
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_alerts (
                    id BIGSERIAL PRIMARY KEY,
                    zone_id INTEGER,
                    source VARCHAR(16) NOT NULL CHECK (source IN ('biz', 'infra')),
                    code VARCHAR(64) NOT NULL,
                    type VARCHAR(64) NOT NULL,
                    status VARCHAR(16) NOT NULL CHECK (status IN ('ACTIVE', 'RESOLVED')),
                    details JSONB,
                    retry_count INTEGER DEFAULT 0,
                    next_retry_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            
            # Индекс для быстрого поиска записей для ретрая
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pending_alerts_retry 
                ON pending_alerts(next_retry_at) 
                WHERE next_retry_at IS NOT NULL
            """)
            
            # Индекс для zone_id
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pending_alerts_zone_id 
                ON pending_alerts(zone_id)
            """)
            
            # Таблица DLQ для pending_alerts
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_alerts_dlq (
                    id BIGSERIAL PRIMARY KEY,
                    zone_id INTEGER,
                    source VARCHAR(16) NOT NULL,
                    code VARCHAR(64) NOT NULL,
                    type VARCHAR(64) NOT NULL,
                    status VARCHAR(16) NOT NULL,
                    details JSONB,
                    retry_count INTEGER NOT NULL,
                    last_error TEXT,
                    failed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    original_id BIGINT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_alerts_dlq_zone_id 
                ON pending_alerts_dlq(zone_id)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_alerts_dlq_failed_at 
                ON pending_alerts_dlq(failed_at)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_alerts_dlq_code 
                ON pending_alerts_dlq(code)
            """)
        
        self._initialized = True
        logger.info("Alert queue table initialized")
    
    async def enqueue(
        self,
        zone_id: Optional[int],
        source: str,
        code: str,
        type: str,
        status: str,
        details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Добавляет алерт в очередь.
        
        Args:
            zone_id: ID зоны (может быть None)
            source: Источник алерта (biz или infra)
            code: Код алерта
            type: Тип алерта
            status: Статус алерта (ACTIVE или RESOLVED)
            details: Дополнительные детали (JSON)
            
        Returns:
            True если успешно добавлено
        """
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            try:
                details_json = json.dumps(details) if details else None
                await conn.execute("""
                    INSERT INTO pending_alerts (zone_id, source, code, type, status, details, retry_count, next_retry_at)
                    VALUES ($1, $2, $3, $4, $5, $6, 0, NOW())
                """, zone_id, source, code, type, status, details_json)
                return True
            except Exception as e:
                logger.error(f"Failed to enqueue alert: {e}", exc_info=True)
                return False
    
    async def mark_retry(self, alert_id: int, retry_count: int, next_retry_at: datetime):
        """Отмечает запись для повторной попытки."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE pending_alerts
                SET retry_count = $1, next_retry_at = $2, updated_at = NOW()
                WHERE id = $3
            """, retry_count, next_retry_at, alert_id)
    
    async def mark_delivered(self, alert_id: int):
        """Удаляет запись после успешной доставки."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM pending_alerts WHERE id = $1
            """, alert_id)
    
    async def move_to_dlq(
        self,
        alert_id: int,
        zone_id: Optional[int],
        source: str,
        code: str,
        type: str,
        status: str,
        details: Optional[Dict[str, Any]],
        retry_count: int,
        last_error: str
    ):
        """Перемещает запись в DLQ после превышения максимального количества попыток."""
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            try:
                details_json = json.dumps(details) if details else None
                await conn.execute("""
                    INSERT INTO pending_alerts_dlq 
                    (zone_id, source, code, type, status, details, retry_count, last_error, original_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """, zone_id, source, code, type, status, details_json, retry_count, last_error, alert_id)
                logger.warning(
                    f"[DLQ] Moved alert to DLQ: code={code}, zone_id={zone_id}, "
                    f"retry_count={retry_count}, error={last_error[:100]}"
                )
            except Exception as e:
                logger.error(f"Failed to move alert to DLQ: {e}", exc_info=True)
    
    async def get_pending(self, limit: int = 100) -> list:
        """
        Получает записи, готовые к ретраю.
        
        Returns:
            Список кортежей (id, zone_id, source, code, type, status, details, retry_count)
        """
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, zone_id, source, code, type, status, details, retry_count
                FROM pending_alerts
                WHERE next_retry_at <= NOW()
                ORDER BY next_retry_at ASC, id ASC
                LIMIT $1
            """, limit)
        
        result = []
        for row in rows:
            details = json.loads(row['details']) if row['details'] else None
            result.append((
                row['id'],
                row['zone_id'],
                row['source'],
                row['code'],
                row['type'],
                row['status'],
                details,
                row['retry_count']
            ))
        
        return result
    
    async def get_queue_metrics(self) -> Dict[str, Any]:
        """
        Получает метрики очереди для observability.
        
        Returns:
            Словарь с метриками: size, oldest_age_seconds
        """
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            try:
                # Получаем размер очереди
                size_row = await conn.fetchrow("""
                    SELECT COUNT(*) as count
                    FROM pending_alerts
                """)
                size = size_row['count'] if size_row else 0
                
                # Получаем возраст самой старой записи (только если есть записи)
                if size > 0:
                    oldest_row = await conn.fetchrow("""
                        SELECT EXTRACT(EPOCH FROM (NOW() - MIN(created_at))) as age_seconds
                        FROM pending_alerts
                    """)
                    oldest_age_seconds = oldest_row['age_seconds'] if oldest_row and oldest_row['age_seconds'] is not None else 0.0
                else:
                    oldest_age_seconds = 0.0
                
                return {
                    'size': size,
                    'oldest_age_seconds': float(oldest_age_seconds),
                }
            except Exception as e:
                # Если таблица еще не создана, возвращаем нулевые метрики
                logger.warning(f"Failed to get queue metrics: {e}")
                return {
                    'size': 0,
                    'oldest_age_seconds': 0.0,
                }


# Глобальный экземпляр очереди
_alert_queue = AlertQueue()


async def get_alert_queue() -> AlertQueue:
    """Возвращает глобальный экземпляр очереди."""
    return _alert_queue


# Используем единый HTTP клиент из http_client_pool
# close_http_client больше не нужен - закрывается централизованно


async def send_alert_to_laravel(
    zone_id: Optional[int],
    source: str,
    code: str,
    type: str,
    status: str,
    details: Optional[Dict[str, Any]] = None,
    node_uid: Optional[str] = None,
    hardware_id: Optional[str] = None,
    severity: Optional[str] = None,
    ts_device: Optional[str] = None
) -> bool:
    """
    Отправляет алерт в Laravel API.
    
    При ошибке сохраняет в персистентную очередь для последующего ретрая.
    
    Args:
        zone_id: ID зоны (может быть None)
        source: Источник алерта (biz или infra)
        code: Код алерта
        type: Тип алерта
        status: Статус алерта (ACTIVE или RESOLVED)
        details: Дополнительные детали
        node_uid: UID узла (опционально)
        hardware_id: Hardware ID узла (опционально)
        severity: Уровень серьезности (опционально)
        ts_device: Временная метка устройства (опционально)
        
    Returns:
        True если успешно отправлено, False если сохранено в очередь
    """
    s = get_settings()
    laravel_url = s.laravel_api_url if hasattr(s, 'laravel_api_url') else None
    
    if not laravel_url:
        logger.error("[ALERT_DELIVERY] Laravel API URL not configured")
        # Сохраняем в очередь для ретрая после настройки
        queue = await get_alert_queue()
        await queue.enqueue(zone_id, source, code, type, status, details)
        return False
    
    ingest_token = (
        s.history_logger_api_token 
        if hasattr(s, 'history_logger_api_token') and s.history_logger_api_token 
        else (s.ingest_token if hasattr(s, 'ingest_token') else None)
    )
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if ingest_token:
        headers["Authorization"] = f"Bearer {ingest_token}"
    
    payload = {
        "zone_id": zone_id,
        "source": source,
        "code": code,
        "type": type,
        "status": status,
        "details": details or None,
    }
    
    # Добавляем опциональные поля, если они указаны
    if node_uid:
        payload["node_uid"] = node_uid
    if hardware_id:
        payload["hardware_id"] = hardware_id
    if severity:
        payload["severity"] = severity
    if ts_device:
        payload["ts_device"] = ts_device
    
    try:
        resp = await make_request(
            'post',
            f"{laravel_url}/api/python/alerts",
            endpoint='alert_delivery',
            headers=headers,
            json=payload,
        )
        
        if resp.status_code == 200:
            logger.info(
                f"[ALERT_DELIVERY] Alert '{code}' delivered to Laravel "
                f"for zone_id={zone_id}"
            )
            return True
        else:
            logger.warning(
                f"[ALERT_DELIVERY] Laravel responded with {resp.status_code}: "
                f"{resp.text[:200]}"
            )
            # Сохраняем в очередь для ретрая
            queue = await get_alert_queue()
            await queue.enqueue(zone_id, source, code, type, status, details)
            return False
            
    except Exception as e:
        # Все ошибки (включая сетевые) обрабатываются здесь
        # make_request уже обработал сетевые ошибки и вернул исключение
        logger.warning(
            f"[ALERT_DELIVERY] Error sending alert to Laravel: {e}"
        )
        # Сохраняем в очередь для ретрая
        queue = await get_alert_queue()
        await queue.enqueue(zone_id, source, code, type, status, details)
        return False
        logger.error(
            f"[ALERT_DELIVERY] Unexpected error sending alert to Laravel: {e}",
            exc_info=True
        )
        # Сохраняем в очередь для ретрая
        queue = await get_alert_queue()
        await queue.enqueue(zone_id, source, code, type, status, details)
        return False


# calculate_backoff удалён - используем calculate_backoff_with_jitter из http_client_pool


async def retry_worker(interval: float = 30.0, shutdown_event: Optional[asyncio.Event] = None):
    """
    Воркер для ретраев алертов из очереди.
    
    Args:
        interval: Интервал между проверками очереди в секундах
        shutdown_event: Событие для graceful shutdown (опционально)
    """
    logger.info("Starting alert retry worker")
    queue = await get_alert_queue()
    
    while True:
        # Проверяем shutdown event, если передан
        if shutdown_event and shutdown_event.is_set():
            logger.info("Alert retry worker received shutdown signal")
            break
        try:
            # Получаем записи, готовые к ретраю
            pending = await queue.get_pending(limit=50)
            
            if not pending:
                # Проверяем shutdown перед sleep
                if shutdown_event and shutdown_event.is_set():
                    break
                await asyncio.sleep(interval)
                continue
            
            logger.info(f"[RETRY_WORKER] Processing {len(pending)} pending alerts")
            
            for alert_id, zone_id, source, code, type, status, details, retry_count in pending:
                # Проверяем shutdown перед обработкой каждой записи
                if shutdown_event and shutdown_event.is_set():
                    logger.info("Alert retry worker received shutdown signal during processing")
                    break
                
                try:
                    # Извлекаем дополнительные поля из details, если они есть
                    node_uid = details.get("node_uid") if details else None
                    hardware_id = details.get("hardware_id") if details else None
                    severity = details.get("severity") or details.get("level") if details else None
                    ts_device = details.get("ts_device") or details.get("ts") if details else None
                    
                    # Пытаемся отправить
                    success = await send_alert_to_laravel(
                        zone_id=zone_id,
                        source=source,
                        code=code,
                        type=type,
                        status=status,
                        details=details,
                        node_uid=node_uid,
                        hardware_id=hardware_id,
                        severity=severity,
                        ts_device=ts_device
                    )
                    
                    if success:
                        # Успешно доставлено - удаляем из очереди
                        await queue.mark_delivered(alert_id)
                        logger.info(
                            f"[RETRY_WORKER] Successfully delivered alert "
                            f"id={alert_id}, code={code}, zone_id={zone_id}"
                        )
                    else:
                        # Не удалось - планируем следующий ретрай с jitter
                        new_retry_count = retry_count + 1
                        backoff_seconds = calculate_backoff_with_jitter(new_retry_count)
                        next_retry_at = datetime.utcnow() + timedelta(seconds=backoff_seconds)
                        
                        await queue.mark_retry(alert_id, new_retry_count, next_retry_at)
                        logger.info(
                            f"[RETRY_WORKER] Scheduled retry for alert id={alert_id}, "
                            f"code={code}, retry_count={new_retry_count}, "
                            f"next_retry_at={next_retry_at.isoformat()}"
                        )
                        
                        # Ограничиваем количество попыток (максимум 10)
                        if new_retry_count >= 10:
                            logger.error(
                                f"[RETRY_WORKER] Max retries reached for alert "
                                f"id={alert_id}, code={code}. Moving to DLQ."
                            )
                            # Перемещаем в DLQ перед удалением
                            await queue.move_to_dlq(
                                alert_id, zone_id, source, code, type, status,
                                details, new_retry_count, "Max retries reached"
                            )
                            await queue.mark_delivered(alert_id)
                
                except Exception as e:
                    logger.error(
                        f"[RETRY_WORKER] Error processing alert id={alert_id}: {e}",
                        exc_info=True
                    )
                    # Планируем ретрай даже при ошибке обработки с jitter
                    new_retry_count = retry_count + 1
                    if new_retry_count < 10:
                        backoff_seconds = calculate_backoff_with_jitter(new_retry_count)
                        next_retry_at = datetime.utcnow() + timedelta(seconds=backoff_seconds)
                        await queue.mark_retry(alert_id, new_retry_count, next_retry_at)
                    else:
                        # Перемещаем в DLQ перед удалением
                        await queue.move_to_dlq(
                            alert_id, zone_id, source, code, type, status,
                            details, retry_count + 1, str(e)
                        )
                        await queue.mark_delivered(alert_id)
            
            # Небольшая задержка перед следующей итерацией
            if shutdown_event and shutdown_event.is_set():
                break
            await asyncio.sleep(1.0)
            
        except Exception as e:
            logger.error(f"[RETRY_WORKER] Unexpected error in alert retry worker: {e}", exc_info=True)
            if shutdown_event and shutdown_event.is_set():
                break
            await asyncio.sleep(interval)
    
    logger.info("Alert retry worker stopped")
