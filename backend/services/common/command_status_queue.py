"""
Модуль для надёжной доставки статусов команд в Laravel API.

Обеспечивает:
- Нормализацию статусов command_response → ACK/DONE/ERROR/INVALID/BUSY/NO_EFFECT
- Персистентную очередь для статусов при ошибках API
- Воркер для ретраев с exponential backoff
- Единый httpx.AsyncClient на процесс
"""
import asyncio
import json
import logging
from typing import Optional, Dict, Any, Union, List
from datetime import datetime, timedelta
from .utils.time import utcnow
from enum import Enum

from .db import get_pool
from .env import get_settings
from .http_client_pool import make_request, calculate_backoff_with_jitter
from .infra_alerts import send_infra_alert

logger = logging.getLogger(__name__)

_COMMAND_ACK_NOT_FOUND_ALERT_TTL_SECONDS = 120
_last_command_ack_not_found_alert_at: Dict[str, datetime] = {}
_PENDING_STATUS_UPDATES_REQUIRED_COLUMNS = {
    "id",
    "cmd_id",
    "status",
    "details",
    "retry_count",
    "max_attempts",
    "next_retry_at",
    "last_error",
    "moved_to_dlq_at",
    "created_at",
    "updated_at",
}
_PENDING_STATUS_UPDATES_DLQ_REQUIRED_COLUMNS = {
    "id",
    "cmd_id",
    "status",
    "details",
    "retry_count",
    "max_attempts",
    "last_error",
    "failed_at",
    "moved_to_dlq_at",
    "original_id",
    "created_at",
}


class _SchemaValidationError(RuntimeError):
    """Ошибка несовместимости runtime-кода и Laravel-схемы очереди."""


def _decode_details_payload(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            logger.warning("Failed to decode status details JSON, returning raw string payload")
            return {"raw_details": raw}
        if isinstance(parsed, dict):
            return parsed
        return {"raw_details": parsed}
    return {"raw_details": raw}


def _decode_laravel_error_payload(resp: Any) -> Dict[str, Any]:
    try:
        payload = resp.json()
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {}


def _is_command_not_found_response(resp: Any, payload: Dict[str, Any]) -> bool:
    if getattr(resp, "status_code", None) != 404:
        return False
    return str(payload.get("code", "")).upper().strip() == "COMMAND_NOT_FOUND"


def _should_emit_command_ack_not_found_alert(now: datetime, key: str) -> bool:
    last = _last_command_ack_not_found_alert_at.get(key)
    if last is None:
        _last_command_ack_not_found_alert_at[key] = now
        return True

    if (now - last).total_seconds() >= _COMMAND_ACK_NOT_FOUND_ALERT_TTL_SECONDS:
        _last_command_ack_not_found_alert_at[key] = now
        return True

    return False


async def _emit_command_ack_not_found_alert(
    *,
    cmd_id: str,
    status_value: str,
    details: Optional[Dict[str, Any]],
    http_status: int,
) -> None:
    zone_id_raw = None
    if isinstance(details, dict):
        zone_id_raw = details.get("zone_id")

    zone_id: Optional[int] = None
    if isinstance(zone_id_raw, int):
        zone_id = zone_id_raw
    elif isinstance(zone_id_raw, str):
        try:
            zone_id = int(zone_id_raw)
        except ValueError:
            zone_id = None

    throttle_key = f"{zone_id or 'global'}:{status_value}"
    now = utcnow()
    if not _should_emit_command_ack_not_found_alert(now, throttle_key):
        return

    await send_infra_alert(
        code="infra_command_ack_command_not_found",
        alert_type="Command Ack Not Found",
        message=f"Laravel не нашёл команду при обработке ACK: {cmd_id}",
        severity="warning",
        zone_id=zone_id,
        service="history-logger",
        component="command_status_delivery",
        node_uid=details.get("node_uid") if isinstance(details, dict) else None,
        channel=details.get("channel") if isinstance(details, dict) else None,
        cmd=details.get("command") if isinstance(details, dict) else None,
        error_type="command_not_found",
        details={
            "cmd_id": cmd_id,
            "status": status_value,
            "http_status": http_status,
            "throttle_seconds": _COMMAND_ACK_NOT_FOUND_ALERT_TTL_SECONDS,
        },
    )


class CommandStatus(str, Enum):
    """Нормализованные статусы команд."""
    SENT = "SENT"  # Команда отправлена в MQTT (подтверждение корреляции)
    ACK = "ACK"
    DONE = "DONE"
    ERROR = "ERROR"
    INVALID = "INVALID"
    BUSY = "BUSY"
    NO_EFFECT = "NO_EFFECT"


def normalize_status(raw_status: str) -> Optional[CommandStatus]:
    """
    Нормализует статус command_response в строго ACK/DONE/ERROR/INVALID/BUSY/NO_EFFECT.
    
    Args:
        raw_status: Сырой статус из command_response (может быть в любом регистре)
        
    Returns:
        Нормализованный статус или None, если статус неизвестен
    """
    raw_upper = str(raw_status).upper().strip()
    
    # ACK - команда принята к выполнению
    if raw_upper == "ACK":
        return CommandStatus.ACK

    # DONE - команда успешно выполнена
    if raw_upper == "DONE":
        return CommandStatus.DONE
    
    # ERROR - команда завершилась с ошибкой
    if raw_upper in ("ERROR", "FAILED", "FAIL"):
        return CommandStatus.ERROR

    if raw_upper == "INVALID":
        return CommandStatus.INVALID

    if raw_upper == "BUSY":
        return CommandStatus.BUSY

    if raw_upper == "NO_EFFECT":
        return CommandStatus.NO_EFFECT
    
    return None


class StatusUpdateQueue:
    """Персистентная очередь для статусов команд."""
    
    def __init__(self):
        self._initialized = False
        self._schema_error: Optional[str] = None

    async def _load_columns(self, conn, table_name: str) -> set[str]:
        rows = await conn.fetch(
            """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = $1
            """,
            table_name,
        )
        return {str(row["column_name"]) for row in rows}

    async def _validate_table_schema(
        self,
        conn,
        table_name: str,
        required_columns: set[str],
    ) -> None:
        actual_columns = await self._load_columns(conn, table_name)
        if not actual_columns:
            raise _SchemaValidationError(
                f"Missing required table '{table_name}'. "
                "Run Laravel migrations before starting history-logger."
            )

        missing_columns = sorted(required_columns - actual_columns)
        if missing_columns:
            raise _SchemaValidationError(
                f"Table '{table_name}' is missing required columns: {', '.join(missing_columns)}. "
                "Run Laravel migrations before starting history-logger."
            )
    
    async def ensure_table(self):
        """Проверяет, что schema очереди подготовлена Laravel-миграциями."""
        if self._initialized:
            return
        if self._schema_error:
            raise RuntimeError(self._schema_error)
        
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await self._validate_table_schema(
                    conn,
                    "pending_status_updates",
                    _PENDING_STATUS_UPDATES_REQUIRED_COLUMNS,
                )
                await self._validate_table_schema(
                    conn,
                    "pending_status_updates_dlq",
                    _PENDING_STATUS_UPDATES_DLQ_REQUIRED_COLUMNS,
                )
        except _SchemaValidationError as exc:
            self._schema_error = str(exc)
            logger.critical(
                "[STATUS_QUEUE_SCHEMA_INVALID] %s",
                self._schema_error,
                exc_info=True,
            )
            raise RuntimeError(self._schema_error) from exc
        except Exception as exc:
            logger.error(
                "[STATUS_QUEUE_SCHEMA_CHECK_FAILED] %s",
                exc,
                exc_info=True,
            )
            raise RuntimeError(
                "Failed to validate status queue schema due to temporary infrastructure error"
            ) from exc

        self._initialized = True
        logger.info("Status update queue schema validated (Laravel migrations)")
    
    async def enqueue(
        self,
        cmd_id: str,
        status: Union[CommandStatus, str],
        details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Добавляет статус в очередь.
        
        Args:
            cmd_id: Идентификатор команды
            status: Нормализованный статус (enum или строка)
            details: Дополнительные детали (error_code, error_message, etc.)
            
        Returns:
            True если успешно добавлено, False если уже существует
        """
        await self.ensure_table()
        
        # Поддержка как enum, так и строки
        status_value = status.value if isinstance(status, CommandStatus) else str(status)
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            try:
                await conn.execute("""
                    INSERT INTO pending_status_updates (cmd_id, status, details, retry_count, next_retry_at)
                    VALUES ($1, $2, $3, 0, NOW())
                    ON CONFLICT (cmd_id, status) 
                    DO UPDATE SET 
                        details = EXCLUDED.details,
                        retry_count = 0,
                        next_retry_at = NOW(),
                        updated_at = NOW()
                """, cmd_id, status_value, details)
                return True
            except Exception as e:
                logger.error(f"Failed to enqueue status update: {e}", exc_info=True)
                return False
    
    async def mark_retry(self, update_id: int, retry_count: int, next_retry_at: datetime, last_error: Optional[str] = None):
        """Отмечает запись для повторной попытки."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE pending_status_updates
                SET retry_count = $1, next_retry_at = $2, last_error = $3, updated_at = NOW()
                WHERE id = $4
            """, retry_count, next_retry_at, last_error, update_id)
    
    async def mark_delivered(self, update_id: int):
        """Удаляет запись после успешной доставки."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM pending_status_updates WHERE id = $1
            """, update_id)
    
    async def move_to_dlq(
        self,
        update_id: int,
        cmd_id: str,
        status: Union[CommandStatus, str],
        details: Optional[Dict[str, Any]],
        retry_count: int,
        max_attempts: int,
        last_error: str
    ):
        """Перемещает запись в DLQ после превышения максимального количества попыток."""
        await self.ensure_table()
        
        status_value = status.value if isinstance(status, CommandStatus) else str(status)
        pool = await get_pool()
        async with pool.acquire() as conn:
            try:
                moved_at = utcnow()
                await conn.execute("""
                    INSERT INTO pending_status_updates_dlq 
                    (cmd_id, status, details, retry_count, max_attempts, last_error, moved_to_dlq_at, original_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """, cmd_id, status_value, details, retry_count, max_attempts, last_error, moved_at, update_id)
                
                # Обновляем moved_to_dlq_at в основной таблице перед удалением
                await conn.execute("""
                    UPDATE pending_status_updates
                    SET moved_to_dlq_at = $1
                    WHERE id = $2
                """, moved_at, update_id)
                
                logger.warning(
                    f"[DLQ] Moved status update to DLQ: cmd_id={cmd_id}, "
                    f"status={status_value}, retry_count={retry_count}/{max_attempts}, error={last_error[:100]}"
                )
            except Exception as e:
                logger.error(f"Failed to move status update to DLQ: {e}", exc_info=True)
    
    async def get_pending(self, limit: int = 100) -> list:
        """
        Получает записи, готовые к ретраю.
        
        Returns:
            Список кортежей (id, cmd_id, status, details, retry_count, max_attempts, last_error)
        """
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, cmd_id, status, details, retry_count, max_attempts, last_error
                FROM pending_status_updates
                WHERE next_retry_at <= NOW()
                ORDER BY next_retry_at ASC, id ASC
                LIMIT $1
            """, limit)
        
        result = []
        for row in rows:
            details = _decode_details_payload(row["details"])
            result.append((
                row['id'],
                row['cmd_id'],
                CommandStatus(row['status']),
                details,
                row['retry_count'],
                row.get('max_attempts', 10),
                row.get('last_error')
            ))
        
        return result
    
    async def get_queue_metrics(self) -> Dict[str, Any]:
        """
        Получает метрики очереди для observability.
        
        Returns:
            Словарь с метриками: size, oldest_age_seconds, dlq_size, success_rate
        """
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            try:
                # Получаем размер очереди
                size_row = await conn.fetchrow("""
                    SELECT COUNT(*) as count
                    FROM pending_status_updates
                """)
                size = size_row['count'] if size_row else 0
                
                # Получаем размер DLQ
                dlq_size_row = await conn.fetchrow("""
                    SELECT COUNT(*) as count
                    FROM pending_status_updates_dlq
                """)
                dlq_size = dlq_size_row['count'] if dlq_size_row else 0
                
                # Получаем возраст самой старой записи (только если есть записи)
                if size > 0:
                    oldest_row = await conn.fetchrow("""
                        SELECT EXTRACT(EPOCH FROM (NOW() - MIN(created_at))) as age_seconds
                        FROM pending_status_updates
                    """)
                    oldest_age_seconds = oldest_row['age_seconds'] if oldest_row and oldest_row['age_seconds'] is not None else 0.0
                else:
                    oldest_age_seconds = 0.0
                
                # Вычисляем success_rate
                total_processed = size + dlq_size
                if total_processed > 0:
                    success_rate = 1.0 - (dlq_size / total_processed) if total_processed > 0 else 1.0
                else:
                    success_rate = 1.0
                
                return {
                    'size': size,
                    'oldest_age_seconds': float(oldest_age_seconds),
                    'dlq_size': dlq_size,
                    'success_rate': float(success_rate),
                }
            except Exception as e:
                # Если таблица еще не создана, возвращаем нулевые метрики
                logger.warning(f"Failed to get queue metrics: {e}")
                return {
                    'size': 0,
                    'oldest_age_seconds': 0.0,
                    'dlq_size': 0,
                    'success_rate': 1.0,
                }
    
    async def list_dlq(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Получает список элементов из DLQ.
        
        Args:
            limit: Максимальное количество записей
            offset: Смещение для пагинации
            
        Returns:
            Список словарей с данными DLQ элементов
        """
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, cmd_id, status, details, retry_count, max_attempts, 
                       last_error, failed_at, moved_to_dlq_at, original_id, created_at
                FROM pending_status_updates_dlq
                ORDER BY moved_to_dlq_at DESC, id DESC
                LIMIT $1 OFFSET $2
            """, limit, offset)
        
        result = []
        for row in rows:
            details = _decode_details_payload(row["details"])
            result.append({
                'id': row['id'],
                'cmd_id': row['cmd_id'],
                'status': row['status'],
                'details': details,
                'retry_count': row['retry_count'],
                'max_attempts': row.get('max_attempts'),
                'last_error': row['last_error'],
                'failed_at': row['failed_at'].isoformat() if row['failed_at'] else None,
                'moved_to_dlq_at': row['moved_to_dlq_at'].isoformat() if row.get('moved_to_dlq_at') else None,
                'original_id': row['original_id'],
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            })
        
        return result
    
    async def replay_dlq_item(self, dlq_id: int) -> bool:
        """
        Перемещает элемент из DLQ обратно в очередь для повторной попытки.
        
        Args:
            dlq_id: ID элемента в DLQ
            
        Returns:
            True если успешно перемещено, False если элемент не найден
        """
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Получаем элемент из DLQ
            row = await conn.fetchrow("""
                SELECT cmd_id, status, details, max_attempts
                FROM pending_status_updates_dlq
                WHERE id = $1
            """, dlq_id)
            
            if not row:
                return False
            
            # Добавляем обратно в очередь с нулевым retry_count
            details_json = row['details']
            status_value = str(row['status'])  # Убеждаемся, что это строка
            max_attempts = row.get('max_attempts', 10)
            
            await conn.execute("""
                INSERT INTO pending_status_updates (cmd_id, status, details, retry_count, max_attempts, next_retry_at)
                VALUES ($1, $2, $3, 0, $4, NOW())
                ON CONFLICT (cmd_id, status) 
                DO UPDATE SET 
                    details = EXCLUDED.details,
                    retry_count = 0,
                    max_attempts = EXCLUDED.max_attempts,
                    next_retry_at = NOW(),
                    updated_at = NOW()
            """, row['cmd_id'], status_value, details_json, max_attempts)
            
            # Удаляем из DLQ
            await conn.execute("""
                DELETE FROM pending_status_updates_dlq WHERE id = $1
            """, dlq_id)
            
            logger.info(f"[DLQ] Replayed status update from DLQ: dlq_id={dlq_id}, cmd_id={row['cmd_id']}")
            return True
    
    async def purge_dlq_item(self, dlq_id: int) -> bool:
        """
        Удаляет элемент из DLQ.
        
        Args:
            dlq_id: ID элемента в DLQ
            
        Returns:
            True если успешно удалено, False если элемент не найден
        """
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM pending_status_updates_dlq WHERE id = $1
            """, dlq_id)
            
            deleted = result == "DELETE 1"
            if deleted:
                logger.info(f"[DLQ] Purged status update from DLQ: dlq_id={dlq_id}")
            return deleted
    
    async def purge_dlq_all(self) -> int:
        """
        Удаляет все элементы из DLQ.
        
        Returns:
            Количество удаленных элементов
        """
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Сначала получаем количество
            count_row = await conn.fetchrow("""
                SELECT COUNT(*) as count FROM pending_status_updates_dlq
            """)
            count = count_row['count'] if count_row else 0
            
            # Удаляем все
            await conn.execute("""
                DELETE FROM pending_status_updates_dlq
            """)
            
            logger.info(f"[DLQ] Purged all status updates from DLQ: count={count}")
            return count


# Глобальный экземпляр очереди
_status_queue = StatusUpdateQueue()


async def get_status_queue() -> StatusUpdateQueue:
    """Возвращает глобальный экземпляр очереди."""
    return _status_queue


# Используем единый HTTP клиент из http_client_pool
# close_http_client больше не нужен - закрывается централизованно


async def send_status_to_laravel(
    cmd_id: str,
    status: Union[CommandStatus, str],
    details: Optional[Dict[str, Any]] = None,
    enqueue_on_failure: bool = True,
) -> bool:
    """
    Отправляет статус команды в Laravel API.
    
    При ошибке сохраняет в персистентную очередь для последующего ретрая.
    
    Args:
        cmd_id: Идентификатор команды
        status: Нормализованный статус
        details: Дополнительные детали
        enqueue_on_failure: Добавлять ли запись в retry-очередь при неуспехе доставки
        
    Returns:
        True если успешно отправлено, False если сохранено в очередь
    """
    logger.info(f"[STATUS_DELIVERY] STEP 1: Starting send_status_to_laravel for cmd_id={cmd_id}, status={status}, details={details}")
    
    s = get_settings()
    laravel_url = s.laravel_api_url if hasattr(s, 'laravel_api_url') else None
    
    logger.info(f"[STATUS_DELIVERY] STEP 2: Checking Laravel API URL: {laravel_url}")
    if not laravel_url:
        logger.error("[STATUS_DELIVERY] STEP 2.1: ERROR - Laravel API URL not configured")
        if enqueue_on_failure:
            # Сохраняем в очередь для ретрая после настройки
            queue = await get_status_queue()
            await queue.enqueue(cmd_id, status, details)
            logger.info(f"[STATUS_DELIVERY] STEP 2.2: Status saved to retry queue for cmd_id={cmd_id}")
        return False
    
    ingest_token = (
        s.history_logger_api_token 
        if hasattr(s, 'history_logger_api_token') and s.history_logger_api_token 
        else (s.ingest_token if hasattr(s, 'ingest_token') and s.ingest_token else None)
    )
    
    logger.info(f"[STATUS_DELIVERY] STEP 3: Ingest token configured: {bool(ingest_token)}, token_length={len(ingest_token) if ingest_token else 0}")
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if ingest_token:
        headers["Authorization"] = f"Bearer {ingest_token}"
        logger.info("[STATUS_DELIVERY] STEP 3.1: Authorization header set")
    else:
        logger.warning("[STATUS_DELIVERY] STEP 3.2: WARNING - No ingest token configured, request may fail with 401")
    
    # Поддержка как enum, так и строки
    status_value = status.value if isinstance(status, CommandStatus) else str(status)
    
    payload = {
        "cmd_id": cmd_id,
        "status": status_value,
        "details": details or None,
    }
    
    logger.info(f"[STATUS_DELIVERY] STEP 4: Prepared payload: cmd_id={cmd_id}, status={status_value}, details={details}")
    logger.info(f"[STATUS_DELIVERY] STEP 5: Sending POST request to {laravel_url}/api/python/commands/ack")
    
    try:
        resp = await make_request(
            'post',
            f"{laravel_url}/api/python/commands/ack",
            endpoint='command_ack',
            headers=headers,
            json=payload,
        )
        
        logger.info(f"[STATUS_DELIVERY] STEP 6: Received response: status_code={resp.status_code}")
        
        if resp.status_code == 200:
            logger.info(
                f"[STATUS_DELIVERY] STEP 6.1: SUCCESS - Status '{status_value}' delivered to Laravel "
                f"for cmd_id={cmd_id}"
            )
            return True
        else:
            error_payload = _decode_laravel_error_payload(resp)
            if _is_command_not_found_response(resp, error_payload):
                logger.warning(
                    f"[STATUS_DELIVERY] STEP 6.2: COMMAND_NOT_FOUND for cmd_id={cmd_id}, "
                    f"status={status_value}. Response body: {resp.text[:200]}"
                )
                try:
                    await _emit_command_ack_not_found_alert(
                        cmd_id=cmd_id,
                        status_value=status_value,
                        details=details,
                        http_status=resp.status_code,
                    )
                except Exception as alert_error:
                    logger.error(
                        f"[STATUS_DELIVERY] Failed to emit COMMAND_NOT_FOUND alert for cmd_id={cmd_id}: {alert_error}",
                        exc_info=True,
                    )
            else:
                logger.warning(
                    f"[STATUS_DELIVERY] STEP 6.2: ERROR - Laravel responded with {resp.status_code}: "
                    f"{resp.text[:200]}"
                )

            if enqueue_on_failure:
                # Сохраняем в очередь для ретрая
                queue = await get_status_queue()
                await queue.enqueue(cmd_id, status, details)
                logger.info(f"[STATUS_DELIVERY] STEP 6.3: Status saved to retry queue for cmd_id={cmd_id}")
            return False
            
    except Exception as e:
        logger.error(
            f"[STATUS_DELIVERY] STEP 6.4: EXCEPTION - Unexpected error sending status to Laravel: {e}",
            exc_info=True
        )
        if enqueue_on_failure:
            # Сохраняем в очередь для ретрая
            queue = await get_status_queue()
            await queue.enqueue(cmd_id, status, details)
        return False


# calculate_backoff удалён - используем calculate_backoff_with_jitter из http_client_pool


async def retry_worker(interval: float = 30.0, shutdown_event: Optional[asyncio.Event] = None):
    """
    Воркер для ретраев статусов из очереди.
    
    Args:
        interval: Интервал между проверками очереди в секундах
        shutdown_event: Событие для graceful shutdown (опционально)
    """
    logger.info("Starting status retry worker")
    queue = await get_status_queue()

    async def _sleep_with_shutdown(timeout: float) -> None:
        if shutdown_event is None:
            await asyncio.sleep(timeout)
            return
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
    
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
                await _sleep_with_shutdown(interval)
                continue
            
            logger.info(f"[RETRY_WORKER] Processing {len(pending)} pending status updates")
            
            for update_id, cmd_id, status, details, retry_count, max_attempts, last_error in pending:
                # Проверяем shutdown перед обработкой каждой записи
                if shutdown_event and shutdown_event.is_set():
                    logger.info("Status retry worker received shutdown signal during processing")
                    break
                
                try:
                    # Пытаемся отправить
                    success = await send_status_to_laravel(
                        cmd_id,
                        status,
                        details,
                        enqueue_on_failure=False,
                    )
                    
                    if success:
                        # Успешно доставлено - удаляем из очереди
                        await queue.mark_delivered(update_id)
                        logger.info(
                            f"[RETRY_WORKER] Successfully delivered status update "
                            f"id={update_id}, cmd_id={cmd_id}, status={status.value}"
                        )
                    else:
                        # Не удалось - планируем следующий ретрай с jitter
                        new_retry_count = retry_count + 1
                        backoff_seconds = calculate_backoff_with_jitter(new_retry_count)
                        next_retry_at = utcnow() + timedelta(seconds=backoff_seconds)
                        
                        error_msg = f"Failed to deliver after {new_retry_count} attempts"
                        await queue.mark_retry(update_id, new_retry_count, next_retry_at, error_msg)
                        logger.info(
                            f"[RETRY_WORKER] Scheduled retry for update id={update_id}, "
                            f"cmd_id={cmd_id}, retry_count={new_retry_count}, "
                            f"next_retry_at={next_retry_at.isoformat()}"
                        )
                        
                        # Проверяем максимальное количество попыток
                        if new_retry_count >= max_attempts:
                            logger.error(
                                f"[RETRY_WORKER] Max retries reached for update "
                                f"id={update_id}, cmd_id={cmd_id} ({new_retry_count}/{max_attempts}). Moving to DLQ."
                            )
                            # Перемещаем в DLQ перед удалением
                            await queue.move_to_dlq(update_id, cmd_id, status, details, new_retry_count, max_attempts, "Max retries reached")
                            await queue.mark_delivered(update_id)
                
                except Exception as e:
                    logger.error(
                        f"[RETRY_WORKER] Error processing update id={update_id}: {e}",
                        exc_info=True
                    )
                    # Планируем ретрай даже при ошибке обработки с jitter
                    new_retry_count = retry_count + 1
                    error_msg = f"Processing error: {str(e)}"
                    if new_retry_count < max_attempts:
                        backoff_seconds = calculate_backoff_with_jitter(new_retry_count)
                        next_retry_at = utcnow() + timedelta(seconds=backoff_seconds)
                        await queue.mark_retry(update_id, new_retry_count, next_retry_at, error_msg)
                    else:
                        # Перемещаем в DLQ перед удалением
                        await queue.move_to_dlq(update_id, cmd_id, status, details, new_retry_count, max_attempts, error_msg)
                        await queue.mark_delivered(update_id)
            
            # Небольшая задержка перед следующей итерацией
            if shutdown_event and shutdown_event.is_set():
                break
            pause_sec = max(0.01, min(interval, 1.0))
            await _sleep_with_shutdown(pause_sec)
            
        except Exception as e:
            logger.error(f"[RETRY_WORKER] Unexpected error in retry worker: {e}", exc_info=True)
            if shutdown_event and shutdown_event.is_set():
                break
            await _sleep_with_shutdown(interval)
    
    logger.info("Status retry worker stopped")
