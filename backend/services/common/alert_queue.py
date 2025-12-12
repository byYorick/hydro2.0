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

import httpx

from .db import get_pool
from .env import get_settings

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


# Глобальный экземпляр очереди
_alert_queue = AlertQueue()


async def get_alert_queue() -> AlertQueue:
    """Возвращает глобальный экземпляр очереди."""
    return _alert_queue


# Глобальный httpx.AsyncClient для алертов
_http_client: Optional[httpx.AsyncClient] = None


async def get_http_client() -> httpx.AsyncClient:
    """
    Возвращает глобальный httpx.AsyncClient для процесса.
    Создаёт клиент при первом вызове.
    """
    global _http_client
    
    if _http_client is None:
        s = get_settings()
        timeout = httpx.Timeout(10.0, connect=5.0)
        _http_client = httpx.AsyncClient(timeout=timeout)
        logger.info("Created global httpx.AsyncClient for alert delivery")
    
    return _http_client


async def close_http_client():
    """Закрывает глобальный httpx.AsyncClient."""
    global _http_client
    
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
        logger.info("Closed global httpx.AsyncClient for alerts")


async def send_alert_to_laravel(
    zone_id: Optional[int],
    source: str,
    code: str,
    type: str,
    status: str,
    details: Optional[Dict[str, Any]] = None
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
    
    try:
        client = await get_http_client()
        resp = await client.post(
            f"{laravel_url}/api/python/alerts",
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
            
    except (httpx.TimeoutException, httpx.RequestError, httpx.NetworkError) as e:
        logger.warning(
            f"[ALERT_DELIVERY] Network error sending alert to Laravel: {e}"
        )
        # Сохраняем в очередь для ретрая
        queue = await get_alert_queue()
        await queue.enqueue(zone_id, source, code, type, status, details)
        return False
    except Exception as e:
        logger.error(
            f"[ALERT_DELIVERY] Unexpected error sending alert to Laravel: {e}",
            exc_info=True
        )
        # Сохраняем в очередь для ретрая
        queue = await get_alert_queue()
        await queue.enqueue(zone_id, source, code, type, status, details)
        return False


def calculate_backoff(retry_count: int, base_delay: float = 1.0, max_delay: float = 300.0) -> float:
    """
    Вычисляет задержку для exponential backoff.
    
    Args:
        retry_count: Номер попытки (0-based)
        base_delay: Базовая задержка в секундах
        max_delay: Максимальная задержка в секундах
        
    Returns:
        Задержка в секундах
    """
    delay = base_delay * (2 ** retry_count)
    return min(delay, max_delay)


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
                    # Пытаемся отправить
                    success = await send_alert_to_laravel(zone_id, source, code, type, status, details)
                    
                    if success:
                        # Успешно доставлено - удаляем из очереди
                        await queue.mark_delivered(alert_id)
                        logger.info(
                            f"[RETRY_WORKER] Successfully delivered alert "
                            f"id={alert_id}, code={code}, zone_id={zone_id}"
                        )
                    else:
                        # Не удалось - планируем следующий ретрай
                        new_retry_count = retry_count + 1
                        backoff_seconds = calculate_backoff(new_retry_count)
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
                                f"id={alert_id}, code={code}. Removing from queue."
                            )
                            await queue.mark_delivered(alert_id)
                
                except Exception as e:
                    logger.error(
                        f"[RETRY_WORKER] Error processing alert id={alert_id}: {e}",
                        exc_info=True
                    )
                    # Планируем ретрай даже при ошибке обработки
                    new_retry_count = retry_count + 1
                    if new_retry_count < 10:
                        backoff_seconds = calculate_backoff(new_retry_count)
                        next_retry_at = datetime.utcnow() + timedelta(seconds=backoff_seconds)
                        await queue.mark_retry(alert_id, new_retry_count, next_retry_at)
                    else:
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
