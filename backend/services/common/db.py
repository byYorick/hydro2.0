import asyncio
import json
import logging
import threading
import weakref
from datetime import datetime, timezone
from typing import Any, Optional, Dict

import asyncpg

from .env import get_settings
from .utils.time import utcnow

logger = logging.getLogger(__name__)

_state_lock = threading.Lock()
_pools: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncpg.pool.Pool]" = weakref.WeakKeyDictionary()
_pool_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = weakref.WeakKeyDictionary()


def _get_pool_lock(loop: asyncio.AbstractEventLoop) -> asyncio.Lock:
    """
    Возвращает lock инициализации пула для конкретного event loop.
    Доступ к структурам состояния защищен thread lock, т.к. сервис может
    работать с несколькими loop в разных потоках (например, main loop + API thread).
    """
    with _state_lock:
        lock = _pool_locks.get(loop)
        if lock is None:
            lock = asyncio.Lock()
            _pool_locks[loop] = lock
        return lock


def _get_pool_for_loop(loop: asyncio.AbstractEventLoop) -> Optional[asyncpg.pool.Pool]:
    with _state_lock:
        return _pools.get(loop)


def _set_pool_for_loop(loop: asyncio.AbstractEventLoop, pool: asyncpg.pool.Pool) -> None:
    with _state_lock:
        _pools[loop] = pool


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
    loop = asyncio.get_running_loop()

    pool = _get_pool_for_loop(loop)
    if pool is not None:
        return pool

    async with _get_pool_lock(loop):
        # Double-check после lock, чтобы не создать pool повторно в гонке.
        pool = _get_pool_for_loop(loop)
        if pool is not None:
            return pool

        s = get_settings()
        pool_min_size = max(1, int(getattr(s, "pg_pool_min_size", 1)))
        pool_max_size = max(pool_min_size, int(getattr(s, "pg_pool_max_size", 5)))
        pg_app_name = str(getattr(s, "pg_app_name", "hydro:python-service"))

        pool = await asyncpg.create_pool(
            host=s.pg_host,
            port=s.pg_port,
            database=s.pg_db,
            user=s.pg_user,
            password=s.pg_pass,
            min_size=pool_min_size,
            max_size=pool_max_size,
            server_settings={"application_name": pg_app_name},
            init=_init_connection,
        )
        logger.info(
            "Initialized PostgreSQL pool: min_size=%s max_size=%s app_name=%s",
            pool_min_size,
            pool_max_size,
            pg_app_name,
        )
        _set_pool_for_loop(loop, pool)
        return pool


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
        sample_ts = utcnow().replace(tzinfo=None)
    
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

    update_query = """
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
    """

    insert_query = """
        INSERT INTO unassigned_node_errors (
            hardware_id, error_message, error_code, severity, topic, last_payload,
            count, first_seen_at, last_seen_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, 1, NOW(), NOW(), NOW())
    """

    def _affected_rows(command_tag: str) -> int:
        try:
            return int(str(command_tag).split()[-1])
        except (TypeError, ValueError, IndexError):
            return 0

    updated_tag = await execute(
        update_query,
        last_payload_json,
        error_message,
        severity,
        topic,
        hardware_id,
        error_code,
    )
    if _affected_rows(updated_tag) > 0:
        return

    try:
        await execute(
            insert_query,
            hardware_id,
            error_message,
            error_code,
            severity,
            topic,
            last_payload_json,
        )
    except Exception as exc:
        # Возможна гонка конкурентных вставок: второй воркер ловит unique violation.
        is_unique_violation = isinstance(exc, asyncpg.UniqueViolationError) or getattr(exc, "sqlstate", None) == "23505"
        if not is_unique_violation:
            raise

        await execute(
            update_query,
            last_payload_json,
            error_message,
            severity,
            topic,
            hardware_id,
            error_code,
        )


async def create_zone_event(zone_id: int, event_type: str, details: Optional[Dict[str, Any]] = None):
    """Create a zone event according to DATA_MODEL_REFERENCE.md section 8.1."""
    await execute(
        """
        INSERT INTO zone_events (zone_id, type, payload_json, details, created_at)
        VALUES ($1, $2, $3, $3, NOW())
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
