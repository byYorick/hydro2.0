"""CommandBus alert emitters."""

from typing import Any, Optional

from common.infra_alerts import send_infra_alert
from services.resilience_contract import (
    INFRA_COMMAND_BUSY,
    INFRA_COMMAND_EFFECT_NOT_CONFIRMED,
    INFRA_COMMAND_FAILED,
    INFRA_COMMAND_INVALID,
    INFRA_COMMAND_NO_EFFECT,
    INFRA_COMMAND_SEND_FAILED,
    INFRA_COMMAND_TIMEOUT,
    INFRA_COMMAND_TRACKER_UNAVAILABLE,
)


async def emit_publish_failure_alert(
    command_bus: Any,
    *,
    code: str,
    zone_id: int,
    node_uid: str,
    channel: str,
    cmd: str,
    error: Optional[str],
    error_type: Optional[str],
    http_status: Optional[int] = None,
) -> None:
    severity = "critical" if code in {INFRA_COMMAND_SEND_FAILED, INFRA_COMMAND_TIMEOUT} else "error"
    await send_infra_alert(
        code=code,
        alert_type="Command Publish Failed",
        message=f"Не удалось отправить команду {cmd}: {error or code}",
        severity=severity,
        zone_id=zone_id,
        service="automation-engine",
        component="command_bus",
        node_uid=node_uid,
        channel=channel,
        cmd=cmd,
        error_type=error_type,
        details={
            "http_status": http_status,
            "error_message": error,
        },
    )


async def emit_closed_loop_failure_alert(
    command_bus: Any,
    *,
    zone_id: int,
    node_uid: str,
    channel: str,
    cmd: str,
    cmd_id: Optional[str],
    terminal_status: str,
    error: Optional[str],
) -> None:
    status = str(terminal_status or "").strip().upper() or "UNKNOWN"
    code_map = {
        "SEND_FAILED": (INFRA_COMMAND_SEND_FAILED, "critical"),
        "TRACKER_UNAVAILABLE": (INFRA_COMMAND_TRACKER_UNAVAILABLE, "error"),
        "TIMEOUT": (INFRA_COMMAND_TIMEOUT, "critical"),
        "ERROR": (INFRA_COMMAND_FAILED, "error"),
        "INVALID": (INFRA_COMMAND_INVALID, "error"),
        "BUSY": (INFRA_COMMAND_BUSY, "warning"),
        "NO_EFFECT": (INFRA_COMMAND_NO_EFFECT, "warning"),
    }
    code, severity = code_map.get(status, (INFRA_COMMAND_EFFECT_NOT_CONFIRMED, "error"))
    await send_infra_alert(
        code=code,
        alert_type="Command Closed-Loop Not Confirmed",
        message=f"Команда {cmd} не подтверждена DONE (status={status})",
        severity=severity,
        zone_id=zone_id,
        service="automation-engine",
        component="command_bus",
        node_uid=node_uid,
        channel=channel,
        cmd=cmd,
        error_type=status,
        details={
            "cmd_id": cmd_id,
            "terminal_status": status,
            "error_message": error,
        },
    )

