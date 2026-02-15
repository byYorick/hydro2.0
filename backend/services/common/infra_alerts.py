"""
Вспомогательные функции для публикации инфраструктурных алертов.

Цель:
- единый формат details для ошибок Python-сервисов;
- единая проверка feature-flag;
- минимизация дублирования кода в automation-engine/history-logger/scheduler.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from .alert_queue import send_alert_to_laravel
from .trace_context import get_trace_id
from .utils.time import utcnow

logger = logging.getLogger(__name__)

_TRUE_VALUES = {"1", "true", "yes", "on"}


def infra_alerts_enabled() -> bool:
    """Глобальный feature-flag публикации инфраструктурных алертов."""
    raw = str(os.getenv("INFRA_ALERTS_ENABLED", "1")).strip().lower()
    return raw in _TRUE_VALUES


def _normalize_severity(value: Optional[str], code: str) -> str:
    if value:
        lowered = value.lower().strip()
        if lowered in {"info", "warning", "error", "critical"}:
            return lowered

    code_lower = code.lower()
    if "timeout" in code_lower or "send_failed" in code_lower:
        return "critical"
    if "failed" in code_lower or "error" in code_lower:
        return "error"
    return "warning"


def _build_dedupe_key(
    *,
    code: str,
    zone_id: Optional[int],
    service: Optional[str],
    component: Optional[str],
    node_uid: Optional[str],
    channel: Optional[str],
    cmd: Optional[str],
    error_type: Optional[str],
) -> str:
    return "|".join(
        [
            code or "infra_unknown_error",
            str(zone_id or "global"),
            service or "unknown_service",
            component or "unknown_component",
            node_uid or "unknown_node",
            channel or "unknown_channel",
            cmd or "unknown_cmd",
            error_type or "unknown_error_type",
        ]
    )


async def send_infra_alert(
    *,
    code: str,
    message: str,
    zone_id: Optional[int] = None,
    alert_type: str = "Infrastructure Error",
    severity: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    service: Optional[str] = None,
    component: Optional[str] = None,
    node_uid: Optional[str] = None,
    hardware_id: Optional[str] = None,
    channel: Optional[str] = None,
    cmd: Optional[str] = None,
    error_type: Optional[str] = None,
    ts_device: Optional[str] = None,
) -> bool:
    """
    Публикует инфраструктурный алерт в Laravel alerts API.
    Возвращает True, если алерт доставлен сразу; False — если ушел в очередь/ошибка.
    """
    if not infra_alerts_enabled():
        logger.debug(
            "[INFRA_ALERT] Feature flag disabled, skip alert",
            extra={"code": code, "zone_id": zone_id},
        )
        return False

    normalized_severity = _normalize_severity(severity, code)
    trace_id = get_trace_id()

    payload_details = dict(details) if isinstance(details, dict) else {}
    payload_details.update(
        {
            "message": message,
            "service": service,
            "component": component,
            "error_type": error_type,
            "channel": channel,
            "cmd": cmd,
            "trace_id": trace_id,
            "detected_at": utcnow().isoformat(),
            "dedupe_key": _build_dedupe_key(
                code=code,
                zone_id=zone_id,
                service=service,
                component=component,
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
                error_type=error_type,
            ),
        }
    )

    # Чистим пустые значения для компактного payload
    payload_details = {k: v for k, v in payload_details.items() if v is not None}

    try:
        return await send_alert_to_laravel(
            zone_id=zone_id,
            source="infra",
            code=code,
            type=alert_type,
            status="ACTIVE",
            details=payload_details,
            node_uid=node_uid,
            hardware_id=hardware_id,
            severity=normalized_severity,
            ts_device=ts_device,
        )
    except Exception as exc:
        logger.error(
            "[INFRA_ALERT] Failed to publish infrastructure alert: %s",
            exc,
            exc_info=True,
            extra={"code": code, "zone_id": zone_id},
        )
        return False


async def send_infra_exception_alert(
    *,
    error: Exception,
    code: str = "infra_unknown_error",
    zone_id: Optional[int] = None,
    alert_type: str = "Infrastructure Error",
    severity: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    service: Optional[str] = None,
    component: Optional[str] = None,
    node_uid: Optional[str] = None,
    hardware_id: Optional[str] = None,
    channel: Optional[str] = None,
    cmd: Optional[str] = None,
    error_type: Optional[str] = None,
    ts_device: Optional[str] = None,
) -> bool:
    """Удобный wrapper для отправки alert по объекту Exception."""
    details_with_error = dict(details) if isinstance(details, dict) else {}
    details_with_error.setdefault("error_message", str(error))
    resolved_error_type = str(error_type).strip() if isinstance(error_type, str) and error_type.strip() else type(error).__name__

    return await send_infra_alert(
        code=code,
        message=str(error),
        zone_id=zone_id,
        alert_type=alert_type,
        severity=severity,
        details=details_with_error,
        service=service,
        component=component,
        node_uid=node_uid,
        hardware_id=hardware_id,
        channel=channel,
        cmd=cmd,
        error_type=resolved_error_type,
        ts_device=ts_device,
    )


async def send_infra_resolved_alert(
    *,
    code: str,
    message: str,
    zone_id: Optional[int] = None,
    alert_type: str = "Infrastructure Error",
    details: Optional[Dict[str, Any]] = None,
    service: Optional[str] = None,
    component: Optional[str] = None,
    node_uid: Optional[str] = None,
    hardware_id: Optional[str] = None,
    channel: Optional[str] = None,
    cmd: Optional[str] = None,
    ts_device: Optional[str] = None,
) -> bool:
    """
    Публикует RESOLVED-статус для инфраструктурного алерта.
    Используется для явного закрытия инцидента при восстановлении.
    """
    if not infra_alerts_enabled():
        logger.debug(
            "[INFRA_ALERT] Feature flag disabled, skip resolved alert",
            extra={"code": code, "zone_id": zone_id},
        )
        return False

    trace_id = get_trace_id()
    payload_details = dict(details) if isinstance(details, dict) else {}
    payload_details.update(
        {
            "message": message,
            "service": service,
            "component": component,
            "channel": channel,
            "cmd": cmd,
            "trace_id": trace_id,
            "resolved_at": utcnow().isoformat(),
            "dedupe_key": _build_dedupe_key(
                code=code,
                zone_id=zone_id,
                service=service,
                component=component,
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
                error_type="resolved",
            ),
        }
    )
    payload_details = {k: v for k, v in payload_details.items() if v is not None}

    try:
        return await send_alert_to_laravel(
            zone_id=zone_id,
            source="infra",
            code=code,
            type=alert_type,
            status="RESOLVED",
            details=payload_details,
            node_uid=node_uid,
            hardware_id=hardware_id,
            severity="info",
            ts_device=ts_device,
        )
    except Exception as exc:
        logger.error(
            "[INFRA_ALERT] Failed to publish resolved infrastructure alert: %s",
            exc,
            exc_info=True,
            extra={"code": code, "zone_id": zone_id},
        )
        return False
