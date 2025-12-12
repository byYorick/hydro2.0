import asyncio
import json
from typing import Any, Optional, Dict

import asyncpg

from .env import get_settings


_pool: Optional[asyncpg.pool.Pool] = None


async def get_pool() -> asyncpg.pool.Pool:
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = await asyncpg.create_pool(
            host=s.pg_host,
            port=s.pg_port,
            database=s.pg_db,
            user=s.pg_user,
            password=s.pg_pass,
            min_size=1,
            max_size=10,
        )
    return _pool


async def execute(query: str, *args: Any) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


async def fetch(query: str, *args: Any):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def upsert_telemetry_last(zone_id: int, metric_type: str, node_id: Optional[int], channel: Optional[str], value: Optional[float]):
    """
    Обновить или вставить последнее значение телеметрии.
    Использует (zone_id, metric_type) как уникальный ключ (текущая структура таблицы).
    Если node_id указан, он также обновляется.
    """
    actual_node_id = node_id if node_id is not None else -1
    
    await execute(
        """
        INSERT INTO telemetry_last (zone_id, node_id, metric_type, channel, value, updated_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
        ON CONFLICT (zone_id, metric_type)
        DO UPDATE SET 
            node_id = EXCLUDED.node_id,
            channel = EXCLUDED.channel, 
            value = EXCLUDED.value, 
            updated_at = NOW()
        """,
        zone_id, actual_node_id, metric_type, channel, value
    )


async def upsert_unassigned_node_error(
    hardware_id: str,
    error_message: str,
    error_code: Optional[str] = None,
    error_level: str = "ERROR",
    topic: str = "",
    error_data: Optional[Dict[str, Any]] = None
):
    """
    Записать или обновить ошибку неназначенного узла.
    
    Args:
        hardware_id: Hardware ID узла из temp-топика
        error_message: Текст ошибки
        error_code: Код ошибки (опционально)
        error_level: Уровень ошибки (ERROR, WARNING, etc)
        topic: MQTT топик, откуда пришла ошибка
        error_data: Дополнительные данные ошибки (опционально)
    """
    error_data_json = json.dumps(error_data) if error_data else None
    
    # Используем hardware_id + topic как уникальный ключ (unique constraint)
    await execute(
        """
        INSERT INTO unassigned_node_errors (
            hardware_id, error_message, error_code, error_level, topic, error_data,
            count, first_seen_at, last_seen_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, 1, NOW(), NOW(), NOW())
        ON CONFLICT (hardware_id, topic) 
        DO UPDATE SET
            count = unassigned_node_errors.count + 1,
            last_seen_at = NOW(),
            updated_at = NOW(),
            error_data = COALESCE(EXCLUDED.error_data, unassigned_node_errors.error_data),
            error_code = COALESCE(EXCLUDED.error_code, unassigned_node_errors.error_code),
            error_message = EXCLUDED.error_message
        """,
        hardware_id,
        error_message,
        error_code,
        error_level,
        topic,
        error_data_json
    )


async def create_zone_event(zone_id: int, event_type: str, details: Optional[Dict[str, Any]] = None):
    """Create a zone event according to DATA_MODEL_REFERENCE.md section 8.1."""
    details_json = json.dumps(details) if details else None
    await execute(
        """
        INSERT INTO zone_events (zone_id, type, details, created_at)
        VALUES ($1, $2, $3, NOW())
        """,
        zone_id, event_type, details_json
    )


async def create_ai_log(zone_id: Optional[int], action: str, details: Optional[Dict[str, Any]] = None):
    """Create an AI log entry."""
    details_json = json.dumps(details) if details else None
    await execute(
        """
        INSERT INTO ai_logs (zone_id, action, details, created_at)
        VALUES ($1, $2, $3, NOW())
        """,
        zone_id, action, details_json
    )


async def create_scheduler_log(task_name: str, status: str, details: Optional[Dict[str, Any]] = None):
    """Create a scheduler log entry."""
    details_json = json.dumps(details) if details else None
    await execute(
        """
        INSERT INTO scheduler_logs (task_name, status, details, created_at)
        VALUES ($1, $2, $3, NOW())
        """,
        task_name, status, details_json
    )


