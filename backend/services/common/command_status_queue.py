"""
Модуль для надёжной доставки статусов команд в Laravel API.

Обеспечивает:
- Нормализацию статусов command_response → ACCEPTED/DONE/FAILED
- Персистентную очередь для статусов при ошибках API
- Воркер для ретраев с exponential backoff
- Единый httpx.AsyncClient на процесс
"""
import asyncio
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum

import httpx

from .db import get_pool
from .env import get_settings

logger = logging.getLogger(__name__)


class CommandStatus(str, Enum):
    """Нормализованные статусы команд."""
    ACCEPTED = "ACCEPTED"
    DONE = "DONE"
    FAILED = "FAILED"


def normalize_status(raw_status: str) -> Optional[CommandStatus]:
    """
    Нормализует статус command_response в строго ACCEPTED/DONE/FAILED.
    
    Args:
        raw_status: Сырой статус из command_response (может быть в любом регистре)
        
    Returns:
        Нормализованный статус или None, если статус неизвестен
    """
    raw_upper = str(raw_status).upper().strip()
    
    # ACCEPTED - команда принята к выполнению
    if raw_upper in ("ACK", "ACCEPTED", "ACCEPT"):
        return CommandStatus.ACCEPTED
    
    # DONE - команда успешно выполнена
    if raw_upper in ("COMPLETED", "OK", "SUCCESS", "DONE", "FINISHED"):
        return CommandStatus.DONE
    
    # FAILED - команда завершилась с ошибкой
    if raw_upper in ("ERROR", "FAILED", "FAIL", "REJECTED", "TIMEOUT"):
        return CommandStatus.FAILED
    
    return None


class StatusUpdateQueue:
    """Персистентная очередь для статусов команд."""
    
    def __init__(self):
        self._initialized = False
    
    async def ensure_table(self):
        """Создаёт таблицу для очереди, если её нет."""
        if self._initialized:
            return
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_status_updates (
                    id BIGSERIAL PRIMARY KEY,
                    cmd_id VARCHAR(64) NOT NULL,
                    status VARCHAR(16) NOT NULL CHECK (status IN ('ACCEPTED', 'DONE', 'FAILED')),
                    details JSONB,
                    retry_count INTEGER DEFAULT 0,
                    next_retry_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    UNIQUE(cmd_id, status)
                )
            """)
            
            # Индекс для быстрого поиска записей для ретрая
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pending_status_retry 
                ON pending_status_updates(next_retry_at) 
                WHERE next_retry_at IS NOT NULL
            """)
            
            # Индекс для cmd_id
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pending_status_cmd_id 
                ON pending_status_updates(cmd_id)
            """)
        
        self._initialized = True
        logger.info("Status update queue table initialized")
    
    async def enqueue(
        self,
        cmd_id: str,
        status: CommandStatus,
        details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Добавляет статус в очередь.
        
        Args:
            cmd_id: Идентификатор команды
            status: Нормализованный статус
            details: Дополнительные детали (error_code, error_message, etc.)
            
        Returns:
            True если успешно добавлено, False если уже существует
        """
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            try:
                details_json = json.dumps(details) if details else None
                await conn.execute("""
                    INSERT INTO pending_status_updates (cmd_id, status, details, retry_count, next_retry_at)
                    VALUES ($1, $2, $3, 0, NOW())
                    ON CONFLICT (cmd_id, status) 
                    DO UPDATE SET 
                        details = EXCLUDED.details,
                        retry_count = 0,
                        next_retry_at = NOW(),
                        updated_at = NOW()
                """, cmd_id, status.value, details_json)
                return True
            except Exception as e:
                logger.error(f"Failed to enqueue status update: {e}", exc_info=True)
                return False
    
    async def mark_retry(self, update_id: int, retry_count: int, next_retry_at: datetime):
        """Отмечает запись для повторной попытки."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE pending_status_updates
                SET retry_count = $1, next_retry_at = $2, updated_at = NOW()
                WHERE id = $3
            """, retry_count, next_retry_at, update_id)
    
    async def mark_delivered(self, update_id: int):
        """Удаляет запись после успешной доставки."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM pending_status_updates WHERE id = $1
            """, update_id)
    
    async def get_pending(self, limit: int = 100) -> list:
        """
        Получает записи, готовые к ретраю.
        
        Returns:
            Список кортежей (id, cmd_id, status, details, retry_count)
        """
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, cmd_id, status, details, retry_count
                FROM pending_status_updates
                WHERE next_retry_at <= NOW()
                ORDER BY next_retry_at ASC, id ASC
                LIMIT $1
            """, limit)
        
        result = []
        for row in rows:
            details = json.loads(row['details']) if row['details'] else None
            result.append((
                row['id'],
                row['cmd_id'],
                CommandStatus(row['status']),
                details,
                row['retry_count']
            ))
        
        return result


# Глобальный экземпляр очереди
_status_queue = StatusUpdateQueue()


async def get_status_queue() -> StatusUpdateQueue:
    """Возвращает глобальный экземпляр очереди."""
    return _status_queue


# Глобальный httpx.AsyncClient
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
        logger.info("Created global httpx.AsyncClient for command status delivery")
    
    return _http_client


async def close_http_client():
    """Закрывает глобальный httpx.AsyncClient."""
    global _http_client
    
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
        logger.info("Closed global httpx.AsyncClient")


async def send_status_to_laravel(
    cmd_id: str,
    status: CommandStatus,
    details: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Отправляет статус команды в Laravel API.
    
    При ошибке сохраняет в персистентную очередь для последующего ретрая.
    
    Args:
        cmd_id: Идентификатор команды
        status: Нормализованный статус
        details: Дополнительные детали
        
    Returns:
        True если успешно отправлено, False если сохранено в очередь
    """
    s = get_settings()
    laravel_url = s.laravel_api_url if hasattr(s, 'laravel_api_url') else None
    
    if not laravel_url:
        logger.error("[STATUS_DELIVERY] Laravel API URL not configured")
        # Сохраняем в очередь для ретрая после настройки
        queue = await get_status_queue()
        await queue.enqueue(cmd_id, status, details)
        return False
    
    ingest_token = (
        s.history_logger_api_token 
        if hasattr(s, 'history_logger_api_token') and s.history_logger_api_token 
        else (s.ingest_token if hasattr(s, 'ingest_token') and s.ingest_token else None)
    )
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if ingest_token:
        headers["Authorization"] = f"Bearer {ingest_token}"
    
    payload = {
        "cmd_id": cmd_id,
        "status": status.value,
        "details": details or None,
    }
    
    try:
        client = await get_http_client()
        resp = await client.post(
            f"{laravel_url}/api/python/commands/ack",
            headers=headers,
            json=payload,
        )
        
        if resp.status_code == 200:
            logger.info(
                f"[STATUS_DELIVERY] Status '{status.value}' delivered to Laravel "
                f"for cmd_id={cmd_id}"
            )
            return True
        else:
            logger.warning(
                f"[STATUS_DELIVERY] Laravel responded with {resp.status_code}: "
                f"{resp.text[:200]}"
            )
            # Сохраняем в очередь для ретрая
            queue = await get_status_queue()
            await queue.enqueue(cmd_id, status, details)
            return False
            
    except (httpx.TimeoutException, httpx.RequestError, httpx.NetworkError) as e:
        logger.warning(
            f"[STATUS_DELIVERY] Network error sending status to Laravel: {e}"
        )
        # Сохраняем в очередь для ретрая
        queue = await get_status_queue()
        await queue.enqueue(cmd_id, status, details)
        return False
    except Exception as e:
        logger.error(
            f"[STATUS_DELIVERY] Unexpected error sending status to Laravel: {e}",
            exc_info=True
        )
        # Сохраняем в очередь для ретрая
        queue = await get_status_queue()
        await queue.enqueue(cmd_id, status, details)
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
    Воркер для ретраев статусов из очереди.
    
    Args:
        interval: Интервал между проверками очереди в секундах
        shutdown_event: Событие для graceful shutdown (опционально)
    """
    logger.info("Starting status retry worker")
    queue = await get_status_queue()
    
    while True:
        # Проверяем shutdown event, если передан
        if shutdown_event and shutdown_event.is_set():
            logger.info("Status retry worker received shutdown signal")
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
            
            logger.info(f"[RETRY_WORKER] Processing {len(pending)} pending status updates")
            
            for update_id, cmd_id, status, details, retry_count in pending:
                # Проверяем shutdown перед обработкой каждой записи
                if shutdown_event and shutdown_event.is_set():
                    logger.info("Status retry worker received shutdown signal during processing")
                    break
                
                try:
                    # Пытаемся отправить
                    success = await send_status_to_laravel(cmd_id, status, details)
                    
                    if success:
                        # Успешно доставлено - удаляем из очереди
                        await queue.mark_delivered(update_id)
                        logger.info(
                            f"[RETRY_WORKER] Successfully delivered status update "
                            f"id={update_id}, cmd_id={cmd_id}, status={status.value}"
                        )
                    else:
                        # Не удалось - планируем следующий ретрай
                        new_retry_count = retry_count + 1
                        backoff_seconds = calculate_backoff(new_retry_count)
                        next_retry_at = datetime.utcnow() + timedelta(seconds=backoff_seconds)
                        
                        await queue.mark_retry(update_id, new_retry_count, next_retry_at)
                        logger.info(
                            f"[RETRY_WORKER] Scheduled retry for update id={update_id}, "
                            f"cmd_id={cmd_id}, retry_count={new_retry_count}, "
                            f"next_retry_at={next_retry_at.isoformat()}"
                        )
                        
                        # Ограничиваем количество попыток (максимум 10)
                        if new_retry_count >= 10:
                            logger.error(
                                f"[RETRY_WORKER] Max retries reached for update "
                                f"id={update_id}, cmd_id={cmd_id}. Removing from queue."
                            )
                            await queue.mark_delivered(update_id)
                
                except Exception as e:
                    logger.error(
                        f"[RETRY_WORKER] Error processing update id={update_id}: {e}",
                        exc_info=True
                    )
                    # Планируем ретрай даже при ошибке обработки
                    new_retry_count = retry_count + 1
                    if new_retry_count < 10:
                        backoff_seconds = calculate_backoff(new_retry_count)
                        next_retry_at = datetime.utcnow() + timedelta(seconds=backoff_seconds)
                        await queue.mark_retry(update_id, new_retry_count, next_retry_at)
                    else:
                        await queue.mark_delivered(update_id)
            
            # Небольшая задержка перед следующей итерацией
            if shutdown_event and shutdown_event.is_set():
                break
            await asyncio.sleep(1.0)
            
        except Exception as e:
            logger.error(f"[RETRY_WORKER] Unexpected error in retry worker: {e}", exc_info=True)
            if shutdown_event and shutdown_event.is_set():
                break
            await asyncio.sleep(interval)
    
    logger.info("Status retry worker stopped")
