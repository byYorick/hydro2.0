import uuid
from .db import execute


async def mark_command_sent(cmd_id: str):
    await execute(
        "UPDATE commands SET status='sent', sent_at=NOW(), updated_at=NOW() WHERE cmd_id=$1",
        cmd_id,
    )


async def mark_command_ack(cmd_id: str):
    await execute(
        """
        UPDATE commands
        SET status='ack', ack_at=NOW(), updated_at=NOW()
        WHERE cmd_id=$1 AND status IN ('pending','sent')
        """,
        cmd_id,
    )


async def mark_command_failed(cmd_id: str):
    await execute(
        """
        UPDATE commands
        SET status='failed', failed_at=NOW(), updated_at=NOW()
        WHERE cmd_id=$1 AND status IN ('pending','sent')
        """,
        cmd_id,
    )


async def mark_timeouts(seconds: int = 30):
    await execute(
        """
        UPDATE commands
        SET status='timeout', updated_at=NOW()
        WHERE status IN ('pending','sent')
          AND created_at < NOW() - ($1::text || ' seconds')::interval
        """,
        str(seconds),
    )


def new_command_id() -> str:
    return str(uuid.uuid4())


