"""
Утилиты для сквозной трассировки (trace_id) между сервисами.
"""
from __future__ import annotations

import contextvars
import uuid
from typing import Any, Iterable, Mapping, Optional, Sequence

_trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_id", default=None
)

_DEFAULT_HEADER_CANDIDATES: Sequence[str] = (
    "x-trace-id",
    "x-request-id",
    "trace-id",
)


def get_trace_id() -> Optional[str]:
    """Получить текущий trace_id из контекста."""
    return _trace_id_var.get()


def set_trace_id(trace_id: Optional[str] = None, *, allow_generate: bool = True) -> Optional[str]:
    """Установить trace_id (или сгенерировать новый)."""
    if trace_id:
        value = str(trace_id)
        _trace_id_var.set(value)
        return value
    if allow_generate:
        value = str(uuid.uuid4())[:12]
        _trace_id_var.set(value)
        return value
    return None


def clear_trace_id() -> None:
    """Очистить trace_id в текущем контексте."""
    _trace_id_var.set(None)


def extract_trace_id_from_headers(
    headers: Optional[Mapping[str, Any]],
    candidates: Optional[Iterable[str]] = None,
) -> Optional[str]:
    """Извлечь trace_id из HTTP заголовков (case-insensitive)."""
    if not headers:
        return None
    candidates = candidates or _DEFAULT_HEADER_CANDIDATES
    for name in candidates:
        try:
            value = headers.get(name)
        except AttributeError:
            value = None
        if not value:
            continue
        value_str = str(value).strip()
        if value_str:
            return value_str
    return None


def extract_trace_id_from_payload(
    payload: Optional[Mapping[str, Any]],
    *,
    keys: Optional[Iterable[str]] = None,
) -> Optional[str]:
    """Извлечь trace_id из payload по заданным ключам."""
    if not payload:
        return None
    keys = keys or ("trace_id", "traceId", "traceID")
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value).strip()
    return None


def set_trace_id_from_headers(
    headers: Optional[Mapping[str, Any]],
    *,
    fallback_generate: bool = True,
) -> Optional[str]:
    """Установить trace_id из заголовков (при отсутствии — сгенерировать)."""
    trace_id = extract_trace_id_from_headers(headers)
    return set_trace_id(trace_id, allow_generate=fallback_generate)


def set_trace_id_from_payload(
    payload: Optional[Mapping[str, Any]],
    *,
    keys: Optional[Iterable[str]] = None,
    fallback_generate: bool = False,
) -> Optional[str]:
    """Установить trace_id из payload (при отсутствии — опционально сгенерировать)."""
    trace_id = extract_trace_id_from_payload(payload, keys=keys)
    return set_trace_id(trace_id, allow_generate=fallback_generate)


def inject_trace_id_header(headers: Optional[Mapping[str, Any]] = None) -> dict:
    """Добавить X-Trace-Id в заголовки исходящего запроса."""
    merged = dict(headers or {})
    trace_id = get_trace_id()
    if trace_id and "X-Trace-Id" not in merged and "x-trace-id" not in merged:
        merged["X-Trace-Id"] = trace_id
    return merged
