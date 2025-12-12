"""
Функции для работы с командами согласно единому контракту.

Используют новые статусы: QUEUED/SENT/ACCEPTED/DONE/FAILED/TIMEOUT/SEND_FAILED
"""
import uuid
from .db import execute


async def mark_command_sent(cmd_id: str, allow_resend: bool = True):
    """
    Помечает команду как отправленную (SENT).
    
    Защита от гонок: обновляет только если статус QUEUED (или SEND_FAILED при allow_resend=True).
    Это предотвращает откат статуса назад, если команда уже перешла в ACCEPTED/DONE/FAILED.
    
    Args:
        cmd_id: Идентификатор команды
        allow_resend: Разрешить повторную отправку из SEND_FAILED (по умолчанию True)
    """
    if allow_resend:
        # Разрешаем переход из QUEUED или SEND_FAILED (для повторной отправки)
        await execute(
            """
            UPDATE commands 
            SET status='SENT', sent_at=NOW(), updated_at=NOW() 
            WHERE cmd_id=$1 AND status IN ('QUEUED', 'SEND_FAILED')
            """,
            cmd_id,
        )
    else:
        # Только из QUEUED (без повторной отправки)
        await execute(
            """
            UPDATE commands 
            SET status='SENT', sent_at=NOW(), updated_at=NOW() 
            WHERE cmd_id=$1 AND status = 'QUEUED'
            """,
            cmd_id,
        )


async def mark_command_accepted(cmd_id: str):
    """
    Помечает команду как принятую узлом (ACCEPTED).
    
    Защита от гонок: обновляет только если статус QUEUED или SENT.
    Не обновляет если команда уже в ACCEPTED/DONE/FAILED/TIMEOUT/SEND_FAILED.
    """
    await execute(
        """
        UPDATE commands
        SET status='ACCEPTED', ack_at=NOW(), updated_at=NOW()
        WHERE cmd_id=$1 AND status IN ('QUEUED','SENT')
        """,
        cmd_id,
    )


async def mark_command_done(cmd_id: str, duration_ms: int = None, result_code: int = 0):
    """
    Помечает команду как успешно выполненную (DONE).
    
    Защита от гонок: обновляет только если статус не является конечным (QUEUED/SENT/ACCEPTED).
    Не обновляет если команда уже в DONE/FAILED/TIMEOUT/SEND_FAILED.
    """
    if duration_ms is not None:
        await execute(
            """
            UPDATE commands
            SET status='DONE', ack_at=COALESCE(ack_at, NOW()), 
                result_code=$2, duration_ms=$3, updated_at=NOW()
            WHERE cmd_id=$1 AND status IN ('QUEUED','SENT','ACCEPTED')
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
            WHERE cmd_id=$1 AND status IN ('QUEUED','SENT','ACCEPTED')
            """,
            cmd_id,
            result_code,
        )


async def mark_command_failed(
    cmd_id: str, 
    error_code: str = None, 
    error_message: str = None,
    result_code: int = 1
):
    """
    Помечает команду как завершившуюся с ошибкой (FAILED).
    
    Защита от гонок: обновляет только если статус не является конечным (QUEUED/SENT/ACCEPTED).
    Не обновляет если команда уже в DONE/FAILED/TIMEOUT/SEND_FAILED.
    """
    if error_code or error_message:
        await execute(
            """
            UPDATE commands
            SET status='FAILED', failed_at=NOW(), 
                error_code=$2, error_message=$3, result_code=$4, updated_at=NOW()
            WHERE cmd_id=$1 AND status IN ('QUEUED','SENT','ACCEPTED')
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
            SET status='FAILED', failed_at=NOW(), result_code=$2, updated_at=NOW()
            WHERE cmd_id=$1 AND status IN ('QUEUED','SENT','ACCEPTED')
            """,
            cmd_id,
            result_code,
        )


async def mark_command_timeout(cmd_id: str):
    """
    Помечает команду как завершившуюся по таймауту (TIMEOUT).
    
    Защита от гонок: обновляет только если статус не является конечным (QUEUED/SENT/ACCEPTED).
    Не обновляет если команда уже в DONE/FAILED/TIMEOUT/SEND_FAILED.
    """
    await execute(
        """
        UPDATE commands
        SET status='TIMEOUT', failed_at=NOW(), 
            error_code='TIMEOUT', result_code=1, updated_at=NOW()
        WHERE cmd_id=$1 AND status IN ('QUEUED','SENT','ACCEPTED')
        """,
        cmd_id,
    )


async def mark_command_send_failed(cmd_id: str, error_message: str = None):
    """
    Помечает команду как не отправленную (SEND_FAILED).
    
    Защита от гонок: обновляет только если статус QUEUED.
    Не обновляет если команда уже отправлена (SENT/ACCEPTED) или завершена (DONE/FAILED/TIMEOUT).
    """
    await execute(
        """
        UPDATE commands
        SET status='SEND_FAILED', failed_at=NOW(), 
            error_code='SEND_FAILED', error_message=$2, result_code=1, updated_at=NOW()
        WHERE cmd_id=$1 AND status = 'QUEUED'
        """,
        cmd_id,
        error_message,
    )


async def mark_timeouts(seconds: int = 30):
    """Помечает команды без ответа как завершившиеся по таймауту."""
    await execute(
        """
        UPDATE commands
        SET status='TIMEOUT', failed_at=NOW(), 
            error_code='TIMEOUT', result_code=1, updated_at=NOW()
        WHERE status IN ('QUEUED','SENT','ACCEPTED')
          AND created_at < NOW() - ($1::text || ' seconds')::interval
        """,
        str(seconds),
    )


# Legacy функции для обратной совместимости
async def mark_command_ack(cmd_id: str):
    """Legacy: помечает команду как выполненную (использует DONE вместо ack)."""
    await mark_command_done(cmd_id)


def new_command_id() -> str:
    """Генерирует новый уникальный идентификатор команды."""
    return str(uuid.uuid4())


