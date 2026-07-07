"""Contextvars-хелперы для structured logging AE3-Lite."""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Optional

from common.trace_context import get_trace_id, set_trace_id

_LOG_CONTEXT_FIELDS = (
    "task_id",
    "zone_id",
    "stage",
    "correction_window_id",
    "cmd_id",
)

_context_vars: dict[str, contextvars.ContextVar[Any]] = {
    field: contextvars.ContextVar(f"ae3_log_{field}", default=None) for field in _LOG_CONTEXT_FIELDS
}

_filter_attached = False


def bind_log_context(
    *,
    task_id: int | str | None = None,
    zone_id: int | str | None = None,
    stage: str | None = None,
    correction_window_id: str | None = None,
    cmd_id: str | None = None,
    trace_id: str | None = None,
) -> contextvars.Token:
    """Устанавливает поля log-context в текущем async/task контексте.

    Возвращает token для сброса всех затронутых полей через ``reset_log_context``.
    ``trace_id`` синхронизируется с ``common.trace_context`` (без автогенерации).
    """
    tokens: list[tuple[str, contextvars.Token[Any]]] = []
    if trace_id is not None:
        set_trace_id(str(trace_id).strip() or None, allow_generate=False)
    for field, value in (
        ("task_id", task_id),
        ("zone_id", zone_id),
        ("stage", stage),
        ("correction_window_id", correction_window_id),
        ("cmd_id", cmd_id),
    ):
        if value is None:
            continue
        normalized = _normalize_field(field, value)
        if normalized is None:
            continue
        tokens.append((field, _context_vars[field].set(normalized)))
    return tokens


def reset_log_context(tokens: list[tuple[str, contextvars.Token[Any]]]) -> None:
    """Сбрасывает поля log-context, установленные ``bind_log_context``."""
    for field, token in reversed(tokens):
        _context_vars[field].reset(token)


@contextmanager
def log_context_scope(**kwargs: Any) -> Iterator[None]:
    """Context manager-обёртка над ``bind_log_context`` / ``reset_log_context``."""
    tokens = bind_log_context(**kwargs)
    try:
        yield
    finally:
        reset_log_context(tokens)


def get_log_context() -> dict[str, Any]:
    """Текущие значения log-context (для тестов и отладки)."""
    payload: dict[str, Any] = {}
    trace_id = get_trace_id()
    if trace_id:
        payload["trace_id"] = trace_id
    for field in _LOG_CONTEXT_FIELDS:
        value = _context_vars[field].get()
        if value is not None:
            payload[field] = value
    return payload


class Ae3LogContextFilter(logging.Filter):
    """Добавляет AE3 log-context поля в LogRecord для JSON/text форматтеров."""

    def filter(self, record: logging.LogRecord) -> bool:
        trace_id = get_trace_id()
        if trace_id and not hasattr(record, "trace_id"):
            record.trace_id = trace_id
        for field in _LOG_CONTEXT_FIELDS:
            if hasattr(record, field):
                continue
            value = _context_vars[field].get()
            if value is not None:
                setattr(record, field, value)
        return True


def attach_ae3_log_context_filter() -> None:
    """Подключает Ae3LogContextFilter к root logger (идемпотентно)."""
    global _filter_attached
    if _filter_attached:
        return
    logging.getLogger().addFilter(Ae3LogContextFilter())
    _filter_attached = True


def _normalize_field(field: str, value: Any) -> Any:
    if field in {"task_id", "zone_id"}:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            return None
        return normalized if normalized > 0 else None
    text = str(value or "").strip()
    return text or None
