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
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import asyncpg
from .utils.time import utcnow

from .db import get_pool
from .env import get_settings
from .http_client_pool import make_request, calculate_backoff_with_jitter

logger = logging.getLogger(__name__)

_ALERT_QUEUE_META_KEY = "__hydro_alert_meta__"
_QUEUE_META_FIELDS = ("node_uid", "hardware_id", "severity", "ts_device")


def _pack_queue_details(
    details: Optional[Dict[str, Any]],
    node_uid: Optional[str] = None,
    hardware_id: Optional[str] = None,
    severity: Optional[str] = None,
    ts_device: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Упаковать details с техническими метаданными для сохранения в очереди.
    Метаданные нужны только для ретрая и не должны уходить в финальный payload как есть.
    """
    payload: Dict[str, Any] = dict(details) if isinstance(details, dict) else {}
    meta: Dict[str, Any] = {}

    if node_uid:
        meta["node_uid"] = node_uid
    if hardware_id:
        meta["hardware_id"] = hardware_id
    if severity:
        meta["severity"] = severity
    if ts_device:
        meta["ts_device"] = ts_device

    if meta:
        payload[_ALERT_QUEUE_META_KEY] = meta

    return payload or None


def _unpack_queue_details(details: Optional[Dict[str, Any]]) -> tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Распаковать details из очереди:
    - вернуть details без технических ключей
    - вернуть метаданные доставки (node_uid/hardware_id/severity/ts_device)
    """
    if not isinstance(details, dict):
        return details, {}

    details_copy = dict(details)
    meta = details_copy.pop(_ALERT_QUEUE_META_KEY, None)
    meta_out: Dict[str, Any] = {}
    if isinstance(meta, dict):
        meta_out.update(meta)

    # Backward compatibility для старых записей очереди
    for key in _QUEUE_META_FIELDS:
        if key not in meta_out and key in details_copy:
            value = details_copy.get(key)
            if value is not None:
                meta_out[key] = value

    return details_copy or None, meta_out


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
                    source VARCHAR(16) NOT NULL CHECK (source IN ('biz', 'infra', 'node')),
                    code VARCHAR(64) NOT NULL,
                    type VARCHAR(64) NOT NULL,
                    status VARCHAR(16) NOT NULL CHECK (status IN ('ACTIVE', 'RESOLVED')),
                    details JSONB,
                    attempts INTEGER DEFAULT 0,
                    max_attempts INTEGER DEFAULT 10,
                    next_retry_at TIMESTAMP WITH TIME ZONE,
                    last_error TEXT,
                    moved_to_dlq_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            
            # Добавляем новые колонки, если они еще не существуют (для миграции существующих таблиц)
            try:
                await conn.execute("""
                    ALTER TABLE pending_alerts 
                    ADD COLUMN IF NOT EXISTS max_attempts INTEGER DEFAULT 10
                """)
            except Exception:
                pass  # Колонка уже существует
            
            try:
                await conn.execute("""
                    ALTER TABLE pending_alerts 
                    ADD COLUMN IF NOT EXISTS last_error TEXT
                """)
            except Exception:
                pass

            # Обновляем check-constraint source для поддержки node-алертов.
            try:
                await conn.execute(
                    "ALTER TABLE pending_alerts DROP CONSTRAINT IF EXISTS pending_alerts_source_check"
                )
                await conn.execute(
                    """
                    ALTER TABLE pending_alerts
                    ADD CONSTRAINT pending_alerts_source_check
                    CHECK (source IN ('biz', 'infra', 'node'))
                    """
                )
            except Exception:
                # В старых схемах имя constraint может отличаться; не прерываем startup.
                pass
            
            try:
                await conn.execute("""
                    ALTER TABLE pending_alerts
                    ADD COLUMN IF NOT EXISTS moved_to_dlq_at TIMESTAMP WITH TIME ZONE
                """)
            except Exception:
                pass

            try:
                # Проверяем, существует ли колонка
                column_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'pending_alerts'
                        AND column_name = 'next_retry_at'
                        AND table_schema = 'public'
                    )
                """)
                if not column_exists:
                    await conn.execute("""
                        ALTER TABLE pending_alerts
                        ADD COLUMN next_retry_at TIMESTAMP WITH TIME ZONE
                    """)
            except Exception:
                pass
            
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
                    attempts INTEGER NOT NULL,
                    max_attempts INTEGER,
                    last_error TEXT,
                    failed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    moved_to_dlq_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    original_id BIGINT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            
            # Добавляем новые колонки в DLQ, если они еще не существуют
            try:
                await conn.execute("""
                    ALTER TABLE pending_alerts_dlq 
                    ADD COLUMN IF NOT EXISTS max_attempts INTEGER
                """)
            except Exception:
                pass
            
            try:
                await conn.execute("""
                    ALTER TABLE pending_alerts_dlq 
                    ADD COLUMN IF NOT EXISTS moved_to_dlq_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                """)
            except Exception:
                pass
            
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
        details: Optional[Dict[str, Any]] = None,
        node_uid: Optional[str] = None,
        hardware_id: Optional[str] = None,
        severity: Optional[str] = None,
        ts_device: Optional[str] = None,
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
                safe_zone_id = zone_id
                details_payload = dict(details) if isinstance(details, dict) else details

                # Fail-safe: если зоны уже нет, сохраняем алерт как unassigned (zone_id=NULL),
                # чтобы не ловить FK-ошибку и не терять сам алерт.
                if zone_id is not None:
                    zone_exists = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM zones WHERE id = $1)",
                        zone_id,
                    )
                    if not zone_exists:
                        safe_zone_id = None
                        if not isinstance(details_payload, dict):
                            details_payload = {}
                        details_payload.setdefault("requested_zone_id", zone_id)
                        details_payload.setdefault("zone_validation", "zone_not_found")
                        logger.warning(
                            "Alert queue: zone_id=%s not found, enqueue as unassigned alert",
                            zone_id,
                            extra={"zone_id": zone_id, "code": code, "source": source},
                        )

                details_json = _pack_queue_details(
                    details=details_payload,
                    node_uid=node_uid,
                    hardware_id=hardware_id,
                    severity=severity,
                    ts_device=ts_device,
                )
                await conn.execute("""
                    INSERT INTO pending_alerts (zone_id, source, code, type, status, details, attempts, next_retry_at)
                    VALUES ($1, $2, $3, $4, $5, $6, 0, NOW())
                """, safe_zone_id, source, code, type, status, details_json)
                return True
            except asyncpg.ForeignKeyViolationError as e:
                # Возможен race-condition: зона удалена после проверки выше.
                # Переписываем запись как unassigned.
                if zone_id is not None:
                    details_payload = dict(details) if isinstance(details, dict) else {}
                    details_payload.setdefault("requested_zone_id", zone_id)
                    details_payload.setdefault("zone_validation", "zone_deleted_race")
                    details_json = _pack_queue_details(
                        details=details_payload,
                        node_uid=node_uid,
                        hardware_id=hardware_id,
                        severity=severity,
                        ts_device=ts_device,
                    )
                    await conn.execute("""
                        INSERT INTO pending_alerts (zone_id, source, code, type, status, details, attempts, next_retry_at)
                        VALUES (NULL, $1, $2, $3, $4, $5, 0, NOW())
                    """, source, code, type, status, details_json)
                    logger.warning(
                        "Alert queue: FK race for zone_id=%s, enqueued as unassigned alert: %s",
                        zone_id,
                        e,
                        extra={"zone_id": zone_id, "code": code, "source": source},
                    )
                    return True
                logger.error(f"Failed to enqueue alert: {e}", exc_info=True)
                return False
            except Exception as e:
                logger.error(f"Failed to enqueue alert: {e}", exc_info=True)
                return False
    
    async def mark_retry(self, alert_id: int, attempts: int, next_retry_at: datetime, last_error: Optional[str] = None):
        """Отмечает запись для повторной попытки."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE pending_alerts
                SET attempts = $1, next_retry_at = $2, last_error = $3, updated_at = NOW()
                WHERE id = $4
            """, attempts, next_retry_at, last_error, alert_id)
    
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
        attempts: int,
        max_attempts: int,
        last_error: str
    ):
        """Перемещает запись в DLQ после превышения максимального количества попыток."""
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            try:
                details_json = details if details else None
                moved_at = utcnow()
                await conn.execute("""
                    INSERT INTO pending_alerts_dlq
                    (zone_id, source, code, type, status, details, attempts, max_attempts, last_error, moved_to_dlq_at, original_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """, zone_id, source, code, type, status, details_json, attempts, max_attempts, last_error, moved_at, alert_id)
                
                # Обновляем moved_to_dlq_at в основной таблице перед удалением
                await conn.execute("""
                    UPDATE pending_alerts
                    SET moved_to_dlq_at = $1
                    WHERE id = $2
                """, moved_at, alert_id)
                
                logger.warning(
                    f"[DLQ] Moved alert to DLQ: code={code}, zone_id={zone_id}, "
                    f"attempts={attempts}/{max_attempts}, error={last_error[:100]}"
                )
            except Exception as e:
                logger.error(f"Failed to move alert to DLQ: {e}", exc_info=True)
    
    async def get_pending(self, limit: int = 100) -> list:
        """
        Получает записи, готовые к ретраю.
        
        Returns:
            Список кортежей (id, zone_id, source, code, type, status, details, attempts, max_attempts, last_error)
        """
        await self.ensure_table()
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, zone_id, source, code, type, status, details, attempts, max_attempts, last_error
                FROM pending_alerts
                WHERE next_retry_at IS NULL OR next_retry_at <= NOW()
                ORDER BY next_retry_at ASC NULLS FIRST, id ASC
                LIMIT $1
            """, limit)
        
        result = []
        for row in rows:
            details = row['details'] if row['details'] else None
            result.append((
                row['id'],
                row['zone_id'],
                row['source'],
                row['code'],
                row['type'],
                row['status'],
                details,
                row['attempts'],
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
                    FROM pending_alerts
                """)
                size = size_row['count'] if size_row else 0
                
                # Получаем размер DLQ
                dlq_size_row = await conn.fetchrow("""
                    SELECT COUNT(*) as count
                    FROM pending_alerts_dlq
                """)
                dlq_size = dlq_size_row['count'] if dlq_size_row else 0
                
                # Получаем возраст самой старой записи (только если есть записи)
                if size > 0:
                    oldest_row = await conn.fetchrow("""
                        SELECT EXTRACT(EPOCH FROM (NOW() - MIN(created_at))) as age_seconds
                        FROM pending_alerts
                    """)
                    oldest_age_seconds = oldest_row['age_seconds'] if oldest_row and oldest_row['age_seconds'] is not None else 0.0
                else:
                    oldest_age_seconds = 0.0
                
                # Вычисляем success_rate: (всего - в очереди - в DLQ) / всего
                # Для упрощения считаем success_rate как 1 - (size + dlq_size) / (size + dlq_size + delivered)
                # Но так как delivered не хранится, используем приближение через retry_count
                total_processed = size + dlq_size
                if total_processed > 0:
                    # Приблизительно: успешные = те, что не в очереди и не в DLQ
                    # Для точности нужно было бы хранить счетчик, но для метрик это достаточно
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
                SELECT id, zone_id, source, code, type, status, details, attempts,
                       max_attempts, last_error, failed_at, moved_to_dlq_at, original_id, created_at
                FROM pending_alerts_dlq
                ORDER BY moved_to_dlq_at DESC, id DESC
                LIMIT $1 OFFSET $2
            """, limit, offset)
        
        result = []
        for row in rows:
            details = row['details'] if row['details'] else None
            result.append({
                'id': row['id'],
                'zone_id': row['zone_id'],
                'source': row['source'],
                'code': row['code'],
                'type': row['type'],
                'status': row['status'],
                'details': details,
                'attempts': row['attempts'],
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
                SELECT zone_id, source, code, type, status, details, max_attempts
                FROM pending_alerts_dlq
                WHERE id = $1
            """, dlq_id)
            
            if not row:
                return False
            
            # Добавляем обратно в очередь с нулевым retry_count
            details_json = row['details']
            max_attempts = row.get('max_attempts', 10)
            
            await conn.execute("""
                INSERT INTO pending_alerts (zone_id, source, code, type, status, details, attempts, max_attempts, next_retry_at)
                VALUES ($1, $2, $3, $4, $5, $6, 0, $7, NOW())
            """, row['zone_id'], row['source'], row['code'], row['type'], row['status'], details_json, max_attempts)
            
            # Удаляем из DLQ
            await conn.execute("""
                DELETE FROM pending_alerts_dlq WHERE id = $1
            """, dlq_id)
            
            logger.info(f"[DLQ] Replayed alert from DLQ: dlq_id={dlq_id}, code={row['code']}")
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
                DELETE FROM pending_alerts_dlq WHERE id = $1
            """, dlq_id)
            
            deleted = result == "DELETE 1"
            if deleted:
                logger.info(f"[DLQ] Purged alert from DLQ: dlq_id={dlq_id}")
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
                SELECT COUNT(*) as count FROM pending_alerts_dlq
            """)
            count = count_row['count'] if count_row else 0
            
            # Удаляем все
            await conn.execute("""
                DELETE FROM pending_alerts_dlq
            """)
            
            logger.info(f"[DLQ] Purged all alerts from DLQ: count={count}")
            return count


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
    ts_device: Optional[str] = None,
    enqueue_on_failure: bool = True,
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
        enqueue_on_failure: Добавлять запись в очередь при ошибке доставки.
            Для retry_worker должно быть False, чтобы не дублировать запись.
        
    Returns:
        True если успешно отправлено, False если сохранено в очередь
    """
    s = get_settings()
    laravel_url = s.laravel_api_url if hasattr(s, 'laravel_api_url') else None
    
    if not laravel_url:
        logger.error("[ALERT_DELIVERY] Laravel API URL not configured")
        if enqueue_on_failure:
            # Сохраняем в очередь для ретрая после настройки
            queue = await get_alert_queue()
            await queue.enqueue(
                zone_id,
                source,
                code,
                type,
                status,
                details,
                node_uid=node_uid,
                hardware_id=hardware_id,
                severity=severity,
                ts_device=ts_device,
            )
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
            if enqueue_on_failure:
                # Сохраняем в очередь для ретрая
                queue = await get_alert_queue()
                await queue.enqueue(
                    zone_id,
                    source,
                    code,
                    type,
                    status,
                    details,
                    node_uid=node_uid,
                    hardware_id=hardware_id,
                    severity=severity,
                    ts_device=ts_device,
                )
            return False
            
    except Exception as e:
        # Все ошибки (включая сетевые) обрабатываются здесь
        # make_request уже обработал сетевые ошибки и вернул исключение
        logger.warning(
            f"[ALERT_DELIVERY] Error sending alert to Laravel: {e}"
        )
        if enqueue_on_failure:
            # Сохраняем в очередь для ретрая
            queue = await get_alert_queue()
            await queue.enqueue(
                zone_id,
                source,
                code,
                type,
                status,
                details,
                node_uid=node_uid,
                hardware_id=hardware_id,
                severity=severity,
                ts_device=ts_device,
            )
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
            
            for alert_id, zone_id, source, code, type, status, details, attempts, max_attempts, last_error in pending:
                # Проверяем shutdown перед обработкой каждой записи
                if shutdown_event and shutdown_event.is_set():
                    logger.info("Alert retry worker received shutdown signal during processing")
                    break
                
                try:
                    # Извлекаем дополнительные поля для доставки (без утечки служебных ключей в payload)
                    clean_details, meta = _unpack_queue_details(details)
                    node_uid = meta.get("node_uid")
                    hardware_id = meta.get("hardware_id")
                    severity = meta.get("severity")
                    ts_device = meta.get("ts_device")
                    
                    # Пытаемся отправить
                    success = await send_alert_to_laravel(
                        zone_id=zone_id,
                        source=source,
                        code=code,
                        type=type,
                        status=status,
                        details=clean_details,
                        node_uid=node_uid,
                        hardware_id=hardware_id,
                        severity=severity,
                        ts_device=ts_device,
                        enqueue_on_failure=False,
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
                        new_attempts = attempts + 1
                        backoff_seconds = calculate_backoff_with_jitter(new_attempts)
                        next_retry_at = utcnow() + timedelta(seconds=backoff_seconds)

                        error_msg = f"Failed to deliver after {new_attempts} attempts"
                        await queue.mark_retry(alert_id, new_attempts, next_retry_at, error_msg)
                        logger.info(
                            f"[RETRY_WORKER] Scheduled retry for alert id={alert_id}, "
                            f"code={code}, attempts={new_attempts}, "
                            f"next_retry_at={next_retry_at.isoformat()}"
                        )

                        # Проверяем максимальное количество попыток
                        if new_attempts >= max_attempts:
                            logger.error(
                                f"[RETRY_WORKER] Max retries reached for alert "
                                f"id={alert_id}, code={code} ({new_attempts}/{max_attempts}). Moving to DLQ."
                            )
                            # Перемещаем в DLQ перед удалением
                            await queue.move_to_dlq(
                                alert_id, zone_id, source, code, type, status,
                                details, new_attempts, max_attempts, "Max retries reached"
                            )
                            await queue.mark_delivered(alert_id)
                
                except Exception as e:
                    logger.error(
                        f"[RETRY_WORKER] Error processing alert id={alert_id}: {e}",
                        exc_info=True
                    )
                    # Планируем ретрай даже при ошибке обработки с jitter
                    new_attempts = attempts + 1
                    error_msg = f"Processing error: {str(e)}"
                    if new_attempts < max_attempts:
                        backoff_seconds = calculate_backoff_with_jitter(new_attempts)
                        next_retry_at = utcnow() + timedelta(seconds=backoff_seconds)
                        await queue.mark_retry(alert_id, new_attempts, next_retry_at, error_msg)
                    else:
                        # Перемещаем в DLQ перед удалением
                        await queue.move_to_dlq(
                            alert_id, zone_id, source, code, type, status,
                            details, new_attempts, max_attempts, error_msg
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
