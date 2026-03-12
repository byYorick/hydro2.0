"""
Функции для работы с командами согласно единому контракту.

Используют новые статусы: QUEUED/SENT/ACK/DONE/NO_EFFECT/ERROR/INVALID/BUSY/TIMEOUT/SEND_FAILED
"""
import uuid
from .db import execute


def _affected_rows(command_tag: str) -> int:
    try:
        return int(str(command_tag).split()[-1])
    except (TypeError, ValueError, IndexError):
        return 0


async def mark_command_sent(cmd_id: str, allow_resend: bool = True):
    """
    Помечает команду как отправленную (SENT).
    
    Защита от гонок: обновляет только если статус QUEUED (или SEND_FAILED при allow_resend=True).
    Это предотвращает откат статуса назад, если команда уже перешла в ACK/DONE/ERROR.
    
    Args:
        cmd_id: Идентификатор команды
        allow_resend: Разрешить повторную отправку из SEND_FAILED (по умолчанию True)
    """
    import logging
    from .db import fetch
    logger = logging.getLogger(__name__)
    
    logger.info(f"[MARK_COMMAND_SENT] STEP 1: Starting mark_command_sent for cmd_id={cmd_id}, allow_resend={allow_resend}")
    
    # Проверяем текущий статус команды перед обновлением
    logger.info(f"[MARK_COMMAND_SENT] STEP 2: Checking current status for cmd_id={cmd_id}")
    try:
        current_status = await fetch("SELECT status, sent_at, updated_at FROM commands WHERE cmd_id = $1", cmd_id)
        if current_status:
            status_val = current_status[0].get('status', 'NOT_FOUND')
            sent_at_val = current_status[0].get('sent_at')
            updated_at_val = current_status[0].get('updated_at')
            logger.info(f"[MARK_COMMAND_SENT] STEP 2.1: Current status for cmd_id={cmd_id}: status={status_val}, sent_at={sent_at_val}, updated_at={updated_at_val}")
        else:
            logger.warning(f"[MARK_COMMAND_SENT] STEP 2.2: Command {cmd_id} NOT FOUND in database")
    except Exception as e:
        logger.error(f"[MARK_COMMAND_SENT] STEP 2.3: ERROR checking current status for cmd_id={cmd_id}: {e}", exc_info=True)
    
    if allow_resend:
        logger.info(f"[MARK_COMMAND_SENT] STEP 3: Executing UPDATE with allow_resend=True for cmd_id={cmd_id}")
        # Разрешаем переход из QUEUED или SEND_FAILED (для повторной отправки)
        result = await execute(
            """
            UPDATE commands 
            SET status='SENT', sent_at=NOW(), updated_at=NOW() 
            WHERE cmd_id=$1 AND status IN ('QUEUED', 'SEND_FAILED')
            """,
            cmd_id,
        )
        logger.info(f"[MARK_COMMAND_SENT] STEP 3.1: UPDATE result for cmd_id={cmd_id}: '{result}' (allow_resend=True)")
        # Проверяем, обновилась ли команда
        if "UPDATE 0" in result:
            logger.warning(f"[MARK_COMMAND_SENT] STEP 3.2: WARNING - No rows updated for cmd_id={cmd_id} - command may already be in SENT/ACK/DONE/NO_EFFECT/ERROR status")
        else:
            logger.info(f"[MARK_COMMAND_SENT] STEP 3.3: SUCCESS - Command {cmd_id} updated to SENT")
    else:
        logger.info(f"[MARK_COMMAND_SENT] STEP 3: Executing UPDATE with allow_resend=False for cmd_id={cmd_id}")
        # Только из QUEUED (без повторной отправки)
        result = await execute(
            """
            UPDATE commands 
            SET status='SENT', sent_at=NOW(), updated_at=NOW() 
            WHERE cmd_id=$1 AND status = 'QUEUED'
            """,
            cmd_id,
        )
        logger.info(f"[MARK_COMMAND_SENT] STEP 3.1: UPDATE result for cmd_id={cmd_id}: '{result}' (allow_resend=False)")
        if "UPDATE 0" in result:
            logger.warning(f"[MARK_COMMAND_SENT] STEP 3.2: WARNING - No rows updated for cmd_id={cmd_id} - command may not be in QUEUED status")
        else:
            logger.info(f"[MARK_COMMAND_SENT] STEP 3.3: SUCCESS - Command {cmd_id} updated to SENT")
    
    # Проверяем статус команды после обновления
    logger.info(f"[MARK_COMMAND_SENT] STEP 4: Verifying status after UPDATE for cmd_id={cmd_id}")
    try:
        verify_status = await fetch("SELECT status, sent_at, updated_at FROM commands WHERE cmd_id = $1", cmd_id)
        if verify_status:
            logger.info(f"[MARK_COMMAND_SENT] STEP 4.1: Verified status for cmd_id={cmd_id}: status={verify_status[0].get('status')}, sent_at={verify_status[0].get('sent_at')}, updated_at={verify_status[0].get('updated_at')}")
        else:
            logger.error(f"[MARK_COMMAND_SENT] STEP 4.2: ERROR - Command {cmd_id} NOT FOUND after UPDATE!")
    except Exception as e:
        logger.error(f"[MARK_COMMAND_SENT] STEP 4.3: ERROR verifying status after UPDATE: {e}", exc_info=True)
    
    logger.info(f"[MARK_COMMAND_SENT] STEP 5: Completed mark_command_sent for cmd_id={cmd_id}")


async def mark_command_ack(cmd_id: str):
    """
    Помечает команду как принятую узлом (ACK).
    
    Защита от гонок: обновляет только если статус QUEUED или SENT.
    Не обновляет если команда уже в ACK/DONE/NO_EFFECT/ERROR/INVALID/BUSY/TIMEOUT/SEND_FAILED.
    """
    await execute(
        """
        UPDATE commands
        SET status='ACK', ack_at=NOW(), updated_at=NOW()
        WHERE cmd_id=$1 AND status IN ('QUEUED','SENT')
        """,
        cmd_id,
    )


async def mark_command_done(cmd_id: str, duration_ms: int = None, result_code: int = 0):
    """
    Помечает команду как успешно выполненную (DONE).
    
    Защита от гонок: обновляет только если статус не является конечным (QUEUED/SENT/ACK).
    Не обновляет если команда уже в DONE/NO_EFFECT/ERROR/INVALID/BUSY/TIMEOUT/SEND_FAILED.
    """
    if duration_ms is not None:
        await execute(
            """
            UPDATE commands
            SET status='DONE', ack_at=COALESCE(ack_at, NOW()), 
                result_code=$2, duration_ms=$3, updated_at=NOW()
            WHERE cmd_id=$1 AND status IN ('QUEUED','SENT','ACK')
            """,
            cmd_id,
            result_code,
            duration_ms,
        )
    else:
        await execute(
            """
            UPDATE commands
            SET status='DONE', ack_at=COALESCE(ack_at, NOW()), 
                result_code=$2, updated_at=NOW()
            WHERE cmd_id=$1 AND status IN ('QUEUED','SENT','ACK')
        """,
        cmd_id,
        result_code,
    )

async def mark_command_no_effect(cmd_id: str, duration_ms: int = None):
    """
    Помечает команду как выполненную без эффекта (NO_EFFECT).
    """
    if duration_ms is not None:
        await execute(
            """
            UPDATE commands
            SET status='NO_EFFECT', ack_at=COALESCE(ack_at, NOW()), 
                result_code=0, duration_ms=$2, updated_at=NOW()
            WHERE cmd_id=$1 AND status IN ('QUEUED','SENT','ACK')
            """,
            cmd_id,
            duration_ms,
        )
    else:
        await execute(
            """
            UPDATE commands
            SET status='NO_EFFECT', ack_at=COALESCE(ack_at, NOW()), 
                result_code=0, updated_at=NOW()
            WHERE cmd_id=$1 AND status IN ('QUEUED','SENT','ACK')
            """,
            cmd_id,
        )


async def mark_command_failed(
    cmd_id: str, 
    error_code: str = None, 
    error_message: str = None,
    result_code: int = 1
):
    """
    Помечает команду как завершившуюся с ошибкой (ERROR).
    
    Защита от гонок: обновляет только если статус не является конечным (QUEUED/SENT/ACK).
    Не обновляет если команда уже в DONE/NO_EFFECT/ERROR/INVALID/BUSY/TIMEOUT/SEND_FAILED.
    """
    if error_code or error_message:
        await execute(
            """
            UPDATE commands
            SET status='ERROR', failed_at=NOW(), 
                error_code=$2, error_message=$3, result_code=$4, updated_at=NOW()
            WHERE cmd_id=$1 AND status IN ('QUEUED','SENT','ACK')
            """,
            cmd_id,
            error_code,
            error_message,
            result_code,
        )
    else:
        await execute(
            """
            UPDATE commands
            SET status='ERROR', failed_at=NOW(), result_code=$2, updated_at=NOW()
            WHERE cmd_id=$1 AND status IN ('QUEUED','SENT','ACK')
            """,
            cmd_id,
            result_code,
        )

async def mark_command_invalid(
    cmd_id: str,
    error_code: str = None,
    error_message: str = None,
    result_code: int = 1,
):
    await execute(
        """
        UPDATE commands
        SET status='INVALID', failed_at=NOW(), 
            error_code=$2, error_message=$3, result_code=$4, updated_at=NOW()
        WHERE cmd_id=$1 AND status IN ('QUEUED','SENT','ACK')
        """,
        cmd_id,
        error_code,
        error_message,
        result_code,
    )

async def mark_command_busy(
    cmd_id: str,
    error_code: str = None,
    error_message: str = None,
    result_code: int = 1,
):
    await execute(
        """
        UPDATE commands
        SET status='BUSY', failed_at=NOW(), 
            error_code=$2, error_message=$3, result_code=$4, updated_at=NOW()
        WHERE cmd_id=$1 AND status IN ('QUEUED','SENT','ACK')
        """,
        cmd_id,
        error_code,
        error_message,
        result_code,
    )

async def mark_command_timeout(cmd_id: str):
    """
    Помечает команду как завершившуюся по таймауту (TIMEOUT).
    
    Защита от гонок: обновляет только если статус не является конечным (QUEUED/SENT/ACK).
    Не обновляет если команда уже в DONE/NO_EFFECT/ERROR/INVALID/BUSY/TIMEOUT/SEND_FAILED.
    """
    result = await execute(
        """
        UPDATE commands
        SET status='TIMEOUT', failed_at=NOW(), 
            error_code='TIMEOUT', result_code=1, updated_at=NOW()
        WHERE cmd_id=$1 AND status IN ('QUEUED','SENT','ACK')
        """,
        cmd_id,
    )
    return _affected_rows(result) > 0


async def mark_command_send_failed(cmd_id: str, error_message: str = None):
    """
    Помечает команду как не отправленную (SEND_FAILED).
    
    Защита от гонок: обновляет только если статус QUEUED.
    Не обновляет если команда уже отправлена (SENT/ACK) или завершена (DONE/NO_EFFECT/ERROR/INVALID/BUSY/TIMEOUT).
    """
    result = await execute(
        """
        UPDATE commands
        SET status='SEND_FAILED', failed_at=NOW(), 
            error_code='SEND_FAILED', error_message=$2, result_code=1, updated_at=NOW()
        WHERE cmd_id=$1 AND status = 'QUEUED'
        """,
        cmd_id,
        error_message,
    )
    return _affected_rows(result) > 0


async def mark_timeouts(seconds: int = 30):
    """Помечает команды без ответа как завершившиеся по таймауту."""
    await execute(
        """
        UPDATE commands
        SET status='TIMEOUT', failed_at=NOW(), 
            error_code='TIMEOUT', result_code=1, updated_at=NOW()
        WHERE status IN ('QUEUED','SENT','ACK')
          AND created_at < NOW() - ($1::text || ' seconds')::interval
        """,
        str(seconds),
    )


# Legacy функция удалена: используйте mark_command_ack для ACK и mark_command_done для DONE.


def new_command_id() -> str:
    """Генерирует новый уникальный идентификатор команды."""
    return str(uuid.uuid4())
