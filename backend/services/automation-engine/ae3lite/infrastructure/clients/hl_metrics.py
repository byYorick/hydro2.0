"""Prometheus-метрики HTTP-клиента history-logger (AE3-Lite)."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

HL_REQUEST_DURATION = Histogram(
    "ae3_hl_request_duration_seconds",
    "Длительность HTTP-запросов к history-logger",
    ["path"],
)

HL_REQUEST_ERRORS = Counter(
    "ae3_hl_request_errors_total",
    "Ошибки HTTP-запросов к history-logger",
    ["kind"],
)

HL_BREAKER_STATE = Gauge(
    "ae3_hl_breaker_state",
    "Состояние circuit breaker history-logger (0=closed, 1=open, 2=half-open)",
)

__all__ = [
    "HL_BREAKER_STATE",
    "HL_REQUEST_DURATION",
    "HL_REQUEST_ERRORS",
]
