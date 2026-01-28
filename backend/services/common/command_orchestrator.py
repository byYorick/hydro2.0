"""
Единый оркестратор команд (Command Integrity Agent).

Запрещает прямую публикацию команд в MQTT из backend/services/common/*.
Все команды должны идти через этот оркестратор, который:
- Добавляет cmd_id
- Ведёт статусы в БД
- Обеспечивает ретраи
- Отслеживает результаты (ACK/DONE/NO_EFFECT/ERROR/INVALID/BUSY)
"""
import asyncio
import logging
import os
import time
from typing import Optional, Dict, Any, Literal
import httpx
from .db import fetch, execute
from .commands import new_command_id, mark_command_send_failed
from .env import get_settings
from .schemas import Command, CommandResponse
from .trace_context import inject_trace_id_header, set_trace_id

logger = logging.getLogger(__name__)


async def send_command(
    zone_id: int,
    node_uid: str,
    channel: str,
    cmd: str,
    params: Optional[Dict[str, Any]] = None,
    greenhouse_uid: Optional[str] = None,
    cmd_id: Optional[str] = None,
    deadline_ms: Optional[int] = None,
    attempt: int = 1,
    wait_for_response: bool = False,
    timeout_sec: float = 30.0
) -> Dict[str, Any]:
    """
    Отправить команду через единый оркестратор (history-logger API).
    
    Все команды должны идти через этот интерфейс, а не напрямую в MQTT.
    
    Args:
        zone_id: ID зоны
        node_uid: UID узла
        channel: Канал узла
        cmd: Тип команды (например: "dose", "run_pump", "set_relay", "set_pwm")
        params: Параметры команды
        greenhouse_uid: UID теплицы (опционально, будет получен из БД если не указан)
        cmd_id: Идентификатор команды (генерируется автоматически если не указан)
        deadline_ms: Дедлайн выполнения команды в миллисекундах
        attempt: Номер попытки (начинается с 1)
        wait_for_response: Ожидать ли ответа (ACK/DONE/NO_EFFECT/ERROR/INVALID/BUSY)
        timeout_sec: Таймаут ожидания ответа в секундах
    
    Returns:
        Dict с результатом:
        - cmd_id: идентификатор команды
        - status: статус отправки ("sent", "failed")
        - command_status: статус команды из БД (если wait_for_response=True)
        - error: сообщение об ошибке (если есть)
    """
    if params is None:
        params = {}
    
    # Генерируем cmd_id если не указан
    if cmd_id is None:
        cmd_id = new_command_id()
    
    # Получаем greenhouse_uid из БД если не указан
    if greenhouse_uid is None:
        rows = await fetch(
            """
            SELECT gh.uid as greenhouse_uid
            FROM zones z
            JOIN greenhouses gh ON gh.id = z.greenhouse_id
            WHERE z.id = $1
            """,
            zone_id,
        )
        if not rows:
            error_msg = f"Zone {zone_id} not found"
            logger.error(error_msg)
            await mark_command_send_failed(cmd_id, error_msg)
            return {
                "cmd_id": cmd_id,
                "status": "failed",
                "error": error_msg
            }
        greenhouse_uid = rows[0]["greenhouse_uid"]
    
    # Создаем запись команды в БД со статусом QUEUED
    try:
        existing_cmd = await fetch(
            "SELECT 1 FROM commands WHERE cmd_id = $1",
            cmd_id,
        )
        if not existing_cmd:
            await execute(
                """
                INSERT INTO commands (zone_id, node_id, channel, cmd, params, status, cmd_id, created_at, updated_at)
                SELECT $1, n.id, $3, $4, $5, 'QUEUED', $6, NOW(), NOW()
                FROM nodes n
                WHERE n.uid = $2 AND n.zone_id = $1
                """,
                zone_id,
                node_uid,
                channel,
                cmd,
                params,
                cmd_id,
            )
    except Exception as e:
        logger.error(f"Failed to create command record in DB: {e}", exc_info=True)
        # Продолжаем выполнение, возможно команда уже существует
    
    # Получаем настройки для history-logger API
    settings = get_settings()
    history_logger_url = getattr(settings, 'history_logger_url', None) or os.getenv("HISTORY_LOGGER_URL", "http://history-logger:9300")
    api_token = getattr(settings, 'history_logger_api_token', None) or os.getenv("HISTORY_LOGGER_API_TOKEN") or os.getenv("PY_INGEST_TOKEN")
    
    # Формируем запрос к history-logger API
    request_data = {
        "type": cmd,
        "params": params,
        "greenhouse_uid": greenhouse_uid,
        "node_uid": node_uid,
        "channel": channel,
        "cmd_id": cmd_id,
    }
    
    set_trace_id(cmd_id, allow_generate=False)
    headers = inject_trace_id_header({})
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    
    # Отправляем команду через history-logger API
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{history_logger_url}/zones/{zone_id}/commands",
                json=request_data,
                headers=headers,
            )
            
            if response.status_code != 200:
                error_msg = f"History-logger API returned {response.status_code}: {response.text}"
                logger.error(error_msg)
                await mark_command_send_failed(cmd_id, error_msg)
                return {
                    "cmd_id": cmd_id,
                    "status": "failed",
                    "error": error_msg
                }
            
            result = response.json()
            logger.info(f"Command {cmd_id} sent successfully via history-logger")
            
            # Если нужно ожидать ответа, ждем изменения статуса в БД
            if wait_for_response:
                command_status = await wait_for_command_result(
                    cmd_id,
                    timeout_sec=timeout_sec
                )
                return {
                    "cmd_id": cmd_id,
                    "status": "sent",
                    "command_status": command_status
                }
            
            return {
                "cmd_id": cmd_id,
                "status": "sent"
            }
            
    except httpx.TimeoutException:
        error_msg = f"Timeout sending command to history-logger"
        logger.error(error_msg)
        await mark_command_send_failed(cmd_id, error_msg)
        return {
            "cmd_id": cmd_id,
            "status": "failed",
            "error": error_msg
        }
    except Exception as e:
        error_msg = f"Failed to send command via history-logger: {e}"
        logger.error(error_msg, exc_info=True)
        await mark_command_send_failed(cmd_id, error_msg)
        return {
            "cmd_id": cmd_id,
            "status": "failed",
            "error": error_msg
        }


async def wait_for_command_result(
    cmd_id: str,
    timeout_sec: float = 30.0,
    poll_interval_sec: float = 0.5
) -> Optional[Dict[str, Any]]:
    """
    Ожидать результата выполнения команды (ACK/DONE/NO_EFFECT/ERROR/INVALID/BUSY).
    
    Периодически проверяет статус команды в БД.
    
    Args:
        cmd_id: Идентификатор команды
        timeout_sec: Максимальное время ожидания в секундах
        poll_interval_sec: Интервал проверки статуса в секундах
    
    Returns:
        Dict с информацией о статусе команды или None при таймауте
    """
    start_time = time.time()
    
    while (time.time() - start_time) < timeout_sec:
        rows = await fetch(
            """
            SELECT status, error_code, error_message, result_code, duration_ms
            FROM commands
            WHERE cmd_id = $1
            """,
            cmd_id,
        )
        
        if rows:
            status = rows[0]["status"]
            
            # Конечные статусы
            if status in ["DONE", "NO_EFFECT", "ERROR", "INVALID", "BUSY", "TIMEOUT", "SEND_FAILED"]:
                return {
                    "status": status,
                    "error_code": rows[0].get("error_code"),
                    "error_message": rows[0].get("error_message"),
                    "result_code": rows[0].get("result_code", 0),
                    "duration_ms": rows[0].get("duration_ms"),
                }
            
            # Промежуточные статусы - продолжаем ждать
            if status in ["ACK"]:
                # Команда принята, но еще не завершена
                pass
        
        await asyncio.sleep(poll_interval_sec)
    
    # Таймаут
    logger.warning(f"Timeout waiting for command {cmd_id} result")
    return None


async def get_command_status(cmd_id: str) -> Optional[Dict[str, Any]]:
    """
    Получить текущий статус команды из БД.
    
    Args:
        cmd_id: Идентификатор команды
    
    Returns:
        Dict с информацией о статусе команды или None если команда не найдена
    """
    rows = await fetch(
        """
        SELECT status, error_code, error_message, result_code, duration_ms, 
               created_at, sent_at, ack_at, failed_at
        FROM commands
        WHERE cmd_id = $1
        """,
        cmd_id,
    )
    
    if not rows:
        return None
    
    row = rows[0]
    return {
        "status": row["status"],
        "error_code": row.get("error_code"),
        "error_message": row.get("error_message"),
        "result_code": row.get("result_code", 0),
        "duration_ms": row.get("duration_ms"),
        "created_at": row.get("created_at"),
        "sent_at": row.get("sent_at"),
        "ack_at": row.get("ack_at"),
        "failed_at": row.get("failed_at"),
    }
