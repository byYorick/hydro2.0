"""Отчёты о сбоях, которые модуль отдаёт исполнителю, а наружу шлёт только он."""

from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Mapping

from common.biz_alerts import send_biz_alert

_logger = logging.getLogger(__name__)

_buffer: ContextVar[list["UpwardReport"] | None] = ContextVar(
    "ae3_upward_reports",
    default=None,
)


@dataclass(frozen=True)
class UpwardReport:
    code: str
    message: str
    severity: str = "warning"
    zone_id: int | None = None
    alert_type: str | None = None
    dedupe_key: str | None = None
    node_uid: str | None = None
    details: Mapping[str, Any] | None = None
    scope_parts: tuple[str, ...] = ()


def open_upward_capture() -> Token[list[UpwardReport] | None]:
    return _buffer.set([])


def close_upward_capture(token: Token[list[UpwardReport] | None]) -> None:
    _buffer.reset(token)


def drain_upward_reports() -> tuple[UpwardReport, ...]:
    current = _buffer.get()
    if not current:
        _buffer.set([])
        return ()
    _buffer.set([])
    return tuple(current)


async def note_upward_report(**kwargs: Any) -> None:
    """Кладёт отчёт в буфер текущего тика. Наружу не отправляет."""
    scope = kwargs.get("scope_parts") or ()
    if isinstance(scope, str):
        scope_parts = (scope,)
    else:
        scope_parts = tuple(scope)
    details = kwargs.get("details")
    report = UpwardReport(
        code=str(kwargs.get("code") or ""),
        message=str(kwargs.get("message") or ""),
        severity=str(kwargs.get("severity") or "warning"),
        zone_id=kwargs.get("zone_id"),
        alert_type=kwargs.get("alert_type"),
        dedupe_key=kwargs.get("dedupe_key"),
        node_uid=kwargs.get("node_uid"),
        details=dict(details) if isinstance(details, Mapping) else None,
        scope_parts=scope_parts,
    )
    current = _buffer.get()
    if current is None:
        current = []
        _buffer.set(current)
    current.append(report)


async def publish_upward_reports(reports: tuple[UpwardReport, ...] | list[UpwardReport]) -> None:
    """Единственная отправка доменных biz-alert из исполнителя."""
    for report in reports:
        payload: dict[str, Any] = {
            "code": report.code,
            "message": report.message,
            "severity": report.severity,
        }
        if report.zone_id is not None:
            payload["zone_id"] = report.zone_id
        if report.alert_type:
            payload["alert_type"] = report.alert_type
        if report.dedupe_key:
            payload["dedupe_key"] = report.dedupe_key
        if report.node_uid:
            payload["node_uid"] = report.node_uid
        if report.details:
            payload["details"] = dict(report.details)
        if report.scope_parts:
            payload["scope_parts"] = report.scope_parts
        try:
            await send_biz_alert(**payload)
        except Exception:
            _logger.warning(
                "AE3 исполнитель не смог отправить upward report code=%s",
                report.code,
                exc_info=True,
            )
