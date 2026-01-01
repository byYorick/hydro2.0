import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Optional, Dict

import asyncpg

from .env import get_settings


_pool: Optional[asyncpg.pool.Pool] = None
_pool_loop: Optional[asyncio.AbstractEventLoop] = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    """
    Настраиваем кодеки JSON/JSONB один раз для каждого подключения.
    Это позволяет безопасно передавать dict/list прямо в запросы без предварительного json.dumps.
    """
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
        format="text",
    )
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
        format="text",
    )


async def get_pool() -> asyncpg.pool.Pool:
    global _pool, _pool_loop
    loop = asyncio.get_running_loop()

    if _pool is not None:
        if _pool_loop is loop:
            return _pool
        # Старый пул привязан к другому loop - закрываем и пересоздаем
        try:
            await _pool.close()
        except Exception:
            pass
        _pool = None
        _pool_loop = None

    s = get_settings()
    _pool = await asyncpg.create_pool(
        host=s.pg_host,
        port=s.pg_port,
        database=s.pg_db,
        user=s.pg_user,
        password=s.pg_pass,
        min_size=1,
        max_size=10,
        init=_init_connection,
    )
    _pool_loop = loop
    return _pool


async def execute(query: str, *args: Any) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


async def fetch(query: str, *args: Any):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def upsert_telemetry_last(
    sensor_id: int,
    value: Optional[float],
    ts: Optional[datetime] = None,
    quality: str = "GOOD",
):
    """
    Обновить или вставить последнее значение телеметрии.
    """
    sample_ts = ts
    if sample_ts and getattr(sample_ts, "tzinfo", None):
        sample_ts = sample_ts.astimezone(timezone.utc).replace(tzinfo=None)
    if not sample_ts:
        sample_ts = datetime.utcnow()
    
    await execute(
        """
        INSERT INTO telemetry_last (sensor_id, last_value, last_ts, last_quality, updated_at)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (sensor_id)
        DO UPDATE SET 
            last_value = EXCLUDED.last_value, 
            last_ts = EXCLUDED.last_ts, 
            last_quality = EXCLUDED.last_quality,
            updated_at = EXCLUDED.updated_at
        """,
        sensor_id,
        value,
        sample_ts,
        quality,
        sample_ts,
    )


async def upsert_unassigned_node_error(
    hardware_id: str,
    error_message: str,
    error_code: Optional[str] = None,
    severity: str = "ERROR",
    topic: str = "",
    last_payload: Optional[Dict[str, Any]] = None
):
    """
    Записать или обновить ошибку неназначенного узла.
    
    Args:
        hardware_id: Hardware ID узла из temp-топика
        error_message: Текст ошибки
        error_code: Код ошибки (опционально, используется как часть уникального ключа)
        severity: Уровень ошибки (ERROR, WARNING, CRITICAL, etc)
        topic: MQTT топик, откуда пришла ошибка
        last_payload: Последний payload ошибки (опционально)
    """
    last_payload_json = json.dumps(last_payload) if last_payload else None
    
    # Используем hardware_id + COALESCE(error_code, '') как уникальный ключ
    # Обрабатываем NULL в error_code через COALESCE
    normalized_code = error_code or ''
    
    # Используем функциональный уникальный индекс для ON CONFLICT
    # Индекс создан как: CREATE UNIQUE INDEX ... ON (hardware_id, COALESCE(error_code, ''))
    # Для использования функционального индекса в ON CONFLICT нужно использовать имя индекса
    # или синтаксис ON CONFLICT ON CONSTRAINT, но для функционального индекса это не работает
    # Поэтому используем подход с проверкой существования и обновлением
    
    # Сначала проверяем, существует ли запись
    existing = await fetch(
        """
        SELECT id, count, last_seen_at
        FROM unassigned_node_errors
        WHERE hardware_id = $1 AND COALESCE(error_code, '') = COALESCE($2, '')
        """,
        hardware_id,
        error_code
    )
    
    if existing and len(existing) > 0:
        # Обновляем существующую запись
        await execute(
            """
            UPDATE unassigned_node_errors
            SET 
                count = count + 1,
                last_seen_at = NOW(),
                updated_at = NOW(),
                last_payload = $1::jsonb,
                error_message = $2,
                severity = $3,
                topic = $4
            WHERE hardware_id = $5 AND COALESCE(error_code, '') = COALESCE($6, '')
            """,
            last_payload_json,
            error_message,
            severity,
            topic,
            hardware_id,
            error_code
        )
    else:
        # Создаем новую запись
        await execute(
            """
            INSERT INTO unassigned_node_errors (
                hardware_id, error_message, error_code, severity, topic, last_payload,
                count, first_seen_at, last_seen_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, 1, NOW(), NOW(), NOW())
            """,
            hardware_id,
            error_message,
            error_code,
            severity,
            topic,
            last_payload_json
        )


async def create_zone_event(zone_id: int, event_type: str, details: Optional[Dict[str, Any]] = None):
    """Create a zone event according to DATA_MODEL_REFERENCE.md section 8.1."""
    await execute(
        """
        INSERT INTO zone_events (zone_id, type, payload_json, created_at)
        VALUES ($1, $2, $3, NOW())
        """,
        zone_id, event_type, details
    )


async def create_ai_log(zone_id: Optional[int], action: str, details: Optional[Dict[str, Any]] = None):
    """Create an AI log entry."""
    await execute(
        """
        INSERT INTO ai_logs (zone_id, action, details, created_at)
        VALUES ($1, $2, $3, NOW())
        """,
        zone_id, action, details
    )


async def create_scheduler_log(task_name: str, status: str, details: Optional[Dict[str, Any]] = None):
    """Create a scheduler log entry."""
    await execute(
        """
        INSERT INTO scheduler_logs (task_name, status, details, created_at)
        VALUES ($1, $2, $3, NOW())
        """,
        task_name, status, details
    )
