"""Единый HTTP-шлюз команд к history-logger.

Второй копии в ae4/ нет: runtime вызывает только этот модуль.
Имя plan (irrigation_start и т.п.) в payload не отправляется.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

import httpx
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = frozenset(range(500, 600))
_TERMINAL_STATUSES = frozenset(
    {"DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT", "TIMEOUT", "SEND_FAILED"}
)
_FAIL_STATUSES = frozenset(
    {"NO_EFFECT", "ERROR", "INVALID", "BUSY", "TIMEOUT", "SEND_FAILED"}
)

_BREAKER_CLOSED = 0
_BREAKER_OPEN = 1
_BREAKER_HALF_OPEN = 2

_METRIC_CACHE: dict[str, tuple[Histogram, Counter, Gauge]] = {}


class CommandGatewayError(RuntimeError):
    """Транспорт или ответ history-logger непригодны."""


class CommandNotDoneError(RuntimeError):
    """Mutating-команда завершилась не статусом DONE."""

    def __init__(self, *, cmd_id: str, status: str, message: str) -> None:
        super().__init__(message)
        self.cmd_id = cmd_id
        self.status = status


@dataclass(frozen=True)
class GatewayPublishResult:
    cmd_id: str
    legacy_command_id: str
    status: str


def _metrics(prefix: str) -> tuple[Histogram, Counter, Gauge]:
    key = str(prefix or "ae").strip() or "ae"
    cached = _METRIC_CACHE.get(key)
    if cached is not None:
        return cached
    duration = Histogram(
        f"{key}_hl_request_duration_seconds",
        "Длительность HTTP-запросов к history-logger",
        ["path"],
    )
    errors = Counter(
        f"{key}_hl_request_errors_total",
        "Ошибки HTTP-запросов к history-logger",
        ["kind"],
    )
    breaker = Gauge(
        f"{key}_hl_breaker_state",
        "Состояние circuit breaker history-logger (0=closed, 1=open, 2=half-open)",
    )
    _METRIC_CACHE[key] = (duration, errors, breaker)
    return duration, errors, breaker


class _CircuitBreaker:
    def __init__(
        self,
        *,
        fail_threshold: int,
        open_sec: float,
        state_gauge: Gauge,
        now_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fail_threshold = max(1, int(fail_threshold))
        self._open_sec = max(0.1, float(open_sec))
        self._now_fn = now_fn
        self._consecutive_failures = 0
        self._state = _BREAKER_CLOSED
        self._opened_at = 0.0
        self._half_open_probe_in_flight = False
        self._state_gauge = state_gauge
        self._state_gauge.set(_BREAKER_CLOSED)

    def before_call(self) -> None:
        now = self._now_fn()
        if self._state == _BREAKER_OPEN:
            if now - self._opened_at >= self._open_sec:
                self._state = _BREAKER_HALF_OPEN
                self._half_open_probe_in_flight = False
                self._state_gauge.set(_BREAKER_HALF_OPEN)
            else:
                raise CommandGatewayError("hl_circuit_open")
        if self._state == _BREAKER_HALF_OPEN and self._half_open_probe_in_flight:
            raise CommandGatewayError("hl_circuit_open")
        if self._state == _BREAKER_HALF_OPEN:
            self._half_open_probe_in_flight = True

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._state = _BREAKER_CLOSED
        self._half_open_probe_in_flight = False
        self._state_gauge.set(_BREAKER_CLOSED)

    def record_failure(self) -> None:
        self._half_open_probe_in_flight = False
        if self._state == _BREAKER_HALF_OPEN:
            self._open()
            return
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._fail_threshold:
            self._open()

    def _open(self) -> None:
        self._state = _BREAKER_OPEN
        self._opened_at = self._now_fn()
        self._consecutive_failures = 0
        self._state_gauge.set(_BREAKER_OPEN)


class HistoryLoggerGateway:
    """Публикует команды только через POST /commands history-logger."""

    def __init__(
        self,
        *,
        metrics_prefix: str = "ae4",
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        source: str = "automation-engine",
        timeout_sec: float = 5.0,
        client: Optional[httpx.AsyncClient] = None,
        retry_backoff_sec: Optional[float] = None,
        max_retries: Optional[int] = None,
        breaker_fail_threshold: Optional[int] = None,
        breaker_open_sec: Optional[float] = None,
        poll_interval_sec: float = 0.2,
        poll_timeout_sec: float = 120.0,
        now_fn: Callable[[], float] = time.monotonic,
        status_reader: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self._base_url = str(
            base_url or os.getenv("HISTORY_LOGGER_URL", "http://history-logger:9300")
        ).rstrip("/")
        self._token = str(
            token
            or os.getenv("HISTORY_LOGGER_API_TOKEN")
            or os.getenv("PY_INGEST_TOKEN")
            or ""
        ).strip()
        self._source = source
        self._timeout_sec = float(timeout_sec)
        self._client = client
        self._retry_backoff_sec = max(
            0.0,
            float(
                retry_backoff_sec
                if retry_backoff_sec is not None
                else os.getenv("AE_HL_RETRY_BACKOFF_SEC", "0.5")
            ),
        )
        self._max_retries = max(
            0,
            int(
                max_retries
                if max_retries is not None
                else os.getenv("AE_HL_MAX_RETRIES", "1")
            ),
        )
        duration, errors, breaker_gauge = _metrics(metrics_prefix)
        self._duration = duration
        self._errors = errors
        self._breaker = _CircuitBreaker(
            fail_threshold=int(
                breaker_fail_threshold
                if breaker_fail_threshold is not None
                else os.getenv("AE_HL_BREAKER_FAIL_THRESHOLD", "5")
            ),
            open_sec=float(
                breaker_open_sec
                if breaker_open_sec is not None
                else os.getenv("AE_HL_BREAKER_OPEN_SEC", "15")
            ),
            state_gauge=breaker_gauge,
            now_fn=now_fn,
        )
        self._poll_interval_sec = max(0.05, float(poll_interval_sec))
        self._poll_timeout_sec = max(1.0, float(poll_timeout_sec))
        self._status_reader = status_reader

    async def publish(
        self,
        *,
        greenhouse_uid: str,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
        params: Mapping[str, Any],
        cmd_id: str,
    ) -> str:
        """Публикует команду и возвращает legacy command_id из ответа HL."""
        normalized_cmd = str(cmd or "").strip()
        if not normalized_cmd:
            raise CommandGatewayError("пустой cmd")
        # Имя plan в gateway не отправляется — только device cmd.
        payload = {
            "greenhouse_uid": greenhouse_uid,
            "zone_id": int(zone_id),
            "node_uid": node_uid,
            "channel": channel,
            "cmd": normalized_cmd,
            "params": dict(params),
            "source": self._source,
            "cmd_id": str(cmd_id).strip(),
        }
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        response = await self._post_with_retry("/commands", payload, headers)
        if response.status_code != 200:
            raise CommandGatewayError(self._extract_error_message(response))

        try:
            body = response.json()
        except ValueError as exc:
            raise CommandGatewayError("history-logger вернул некорректный JSON") from exc

        command_id = str(
            ((body.get("data") or {}) if isinstance(body, dict) else {}).get(
                "command_id"
            )
            or ""
        ).strip()
        if not command_id:
            raise CommandGatewayError("Ответ history-logger не содержит data.command_id")
        return command_id

    async def await_done(self, *, cmd_id: str) -> GatewayPublishResult:
        """Ждёт terminal-статус; успех только DONE."""
        deadline = time.monotonic() + self._poll_timeout_sec
        while time.monotonic() < deadline:
            status = await self._read_status(cmd_id=cmd_id)
            if status is None:
                await asyncio.sleep(self._poll_interval_sec)
                continue
            normalized = str(status).strip().upper()
            if normalized not in _TERMINAL_STATUSES:
                await asyncio.sleep(self._poll_interval_sec)
                continue
            if normalized == "DONE":
                return GatewayPublishResult(
                    cmd_id=cmd_id,
                    legacy_command_id="",
                    status=normalized,
                )
            if normalized in _FAIL_STATUSES:
                raise CommandNotDoneError(
                    cmd_id=cmd_id,
                    status=normalized,
                    message=(
                        f"Команда {cmd_id} завершилась статусом {normalized}, "
                        "ожидался DONE"
                    ),
                )
            await asyncio.sleep(self._poll_interval_sec)
        raise CommandNotDoneError(
            cmd_id=cmd_id,
            status="TIMEOUT",
            message=f"Таймаут ожидания DONE для команды {cmd_id}",
        )

    async def publish_and_await_done(
        self,
        *,
        greenhouse_uid: str,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
        params: Mapping[str, Any],
        cmd_id: str,
    ) -> GatewayPublishResult:
        legacy_id = await self.publish(
            greenhouse_uid=greenhouse_uid,
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
            params=params,
            cmd_id=cmd_id,
        )
        result = await self.await_done(cmd_id=cmd_id)
        return GatewayPublishResult(
            cmd_id=result.cmd_id,
            legacy_command_id=legacy_id,
            status=result.status,
        )

    async def _read_status(self, *, cmd_id: str) -> str | None:
        if self._status_reader is not None:
            value = self._status_reader(cmd_id)
            if asyncio.iscoroutine(value):
                value = await value
            if value is None:
                return None
            return str(value)
        from common.db import fetch

        rows = await fetch(
            "SELECT status FROM commands WHERE cmd_id = $1 LIMIT 1",
            cmd_id,
        )
        if not rows:
            return None
        return str(rows[0].get("status") or "")

    async def _post_with_retry(
        self,
        path: str,
        payload: Mapping[str, Any],
        headers: Mapping[str, str],
    ) -> httpx.Response:
        self._breaker.before_call()
        attempt = 0
        while True:
            started_at = time.monotonic()
            try:
                response = await self._post(path, payload, headers)
            except httpx.TimeoutException as exc:
                self._duration.labels(path=path).observe(time.monotonic() - started_at)
                if attempt >= self._max_retries:
                    self._errors.labels(kind="timeout").inc()
                    self._breaker.record_failure()
                    raise CommandGatewayError(
                        f"Таймаут запроса к history-logger: {path}"
                    ) from exc
                await self._sleep_before_retry(attempt=attempt)
                attempt += 1
                continue
            except httpx.RequestError as exc:
                self._duration.labels(path=path).observe(time.monotonic() - started_at)
                if attempt >= self._max_retries:
                    self._errors.labels(kind="transport").inc()
                    self._breaker.record_failure()
                    raise CommandGatewayError(
                        f"Транспортная ошибка history-logger: {exc}"
                    ) from exc
                await self._sleep_before_retry(attempt=attempt)
                attempt += 1
                continue

            self._duration.labels(path=path).observe(time.monotonic() - started_at)
            if response.status_code == 200:
                self._breaker.record_success()
                return response
            if response.status_code not in _RETRYABLE_STATUS_CODES:
                self._errors.labels(kind="4xx").inc()
                return response
            if attempt >= self._max_retries:
                self._errors.labels(kind="5xx").inc()
                self._breaker.record_failure()
                return response
            await self._sleep_before_retry(attempt=attempt)
            attempt += 1

    async def _sleep_before_retry(self, *, attempt: int) -> None:
        base_delay = self._retry_backoff_sec * (2**attempt)
        delay = max(0.0, base_delay * random.uniform(0.75, 1.25))
        if delay > 0:
            await asyncio.sleep(delay)

    async def _post(
        self,
        path: str,
        payload: Mapping[str, Any],
        headers: Mapping[str, str],
    ) -> httpx.Response:
        url = f"{self._base_url}{path}"
        if self._client is not None:
            return await self._client.post(url, json=dict(payload), headers=dict(headers))
        async with httpx.AsyncClient(timeout=self._timeout_sec) as client:
            return await client.post(url, json=dict(payload), headers=dict(headers))

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            text = (response.text or "").strip()
            return text or f"HTTP {response.status_code}"
        if isinstance(body, dict):
            for key in ("detail", "message", "error"):
                value = body.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return f"HTTP {response.status_code}"


def build_ae4_cmd_id(*, task_id: int, zone_id: int, step_no: int) -> str:
    """cmd_id новых команд AE4 начинается с ae4-."""
    return f"ae4-t{int(task_id)}-z{int(zone_id)}-s{int(step_no)}"


__all__ = [
    "CommandGatewayError",
    "CommandNotDoneError",
    "GatewayPublishResult",
    "HistoryLoggerGateway",
    "build_ae4_cmd_id",
]
