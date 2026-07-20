"""
Функции для работы с командами согласно единому контракту.

Используют новые статусы: QUEUED/SENT/ACK/DONE/NO_EFFECT/ERROR/INVALID/BUSY/TIMEOUT/SEND_FAILED
"""
import uuid
from .db import execute, fetch


class MarkCommandSentError(RuntimeError):
    """``mark_command_sent`` не смог атомарно перевести команду в SENT."""


# Terminal outcomes after a successful MQTT publish: treat mark_command_sent as
# race-idempotent success (do not roll status back, do not raise HTTP 500).
_MARK_SENT_IDEMPOTENT_TERMINAL = frozenset(
    {"DONE", "NO_EFFECT", "ERROR", "INVALID", "BUSY", "TIMEOUT"}
)


def _affected_rows(command_tag: str) -> int:
    try:
        return int(str(command_tag).split()[-1])
    except (TypeError, ValueError, IndexError):
        return 0


async def mark_command_sent(cmd_id: str, allow_resend: bool = True) -> bool:
    """
    Помечает команду как отправленную (SENT).

    Fail-closed: бросает ``MarkCommandSentError``, если UPDATE не затронул строку
    и статус не в идемпотентном наборе (SENT+sent_at / ACK / terminal).

    Защита от гонок: переводит только QUEUED/SEND_FAILED в SENT. Для device
    ACK-stub без ``sent_at`` заполняет timestamp, не откатывая статус в SENT.
    Уже ACK (с sent_at) или terminal после publish — идемпотентный success.
    """
    import logging

    logger = logging.getLogger(__name__)

    if allow_resend:
        result = await execute(
            """
            UPDATE commands
            SET status='SENT', sent_at=NOW(), updated_at=NOW()
            WHERE cmd_id=$1 AND status IN ('QUEUED', 'SEND_FAILED')
            """,
            cmd_id,
        )
        if _affected_rows(result) == 0:
            result = await execute(
                """
                UPDATE commands
                SET sent_at=NOW(), updated_at=NOW()
                WHERE cmd_id=$1 AND status = 'ACK' AND sent_at IS NULL
                """,
                cmd_id,
            )
    else:
        result = await execute(
            """
            UPDATE commands
            SET status='SENT', sent_at=NOW(), updated_at=NOW()
            WHERE cmd_id=$1 AND status = 'QUEUED'
            """,
            cmd_id,
        )

    if _affected_rows(result) > 0:
        logger.info("[MARK_COMMAND_SENT] Command %s delivery metadata persisted", cmd_id)
        return True

    rows = await fetch(
        "SELECT status, sent_at FROM commands WHERE cmd_id = $1",
        cmd_id,
    )
    if rows:
        status_val = str(rows[0].get("status") or "").strip().upper()
        sent_at = rows[0].get("sent_at")

        if status_val == "SENT" and sent_at is not None:
            logger.info(
                "[MARK_COMMAND_SENT] Command %s already SENT (idempotent)",
                cmd_id,
            )
            return True

        if status_val == "ACK":
            # Race: ACK (+ optional sent_at) already landed; backfill sent_at if null.
            if sent_at is None:
                await execute(
                    """
                    UPDATE commands
                    SET sent_at=NOW(), updated_at=NOW()
                    WHERE cmd_id=$1 AND status = 'ACK' AND sent_at IS NULL
                    """,
                    cmd_id,
                )
            logger.info(
                "[MARK_COMMAND_SENT] Command %s already ACK (idempotent)",
                cmd_id,
            )
            return True

        if status_val in _MARK_SENT_IDEMPOTENT_TERMINAL:
            logger.info(
                "[MARK_COMMAND_SENT] Command %s already terminal status=%s "
                "(idempotent after publish)",
                cmd_id,
                status_val,
            )
            return True

    logger.error(
        "[MARK_COMMAND_SENT] Failed to mark command as SENT: cmd_id=%s allow_resend=%s",
        cmd_id,
        allow_resend,
    )
    raise MarkCommandSentError(f"mark_command_sent_failed:cmd_id={cmd_id}")


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
