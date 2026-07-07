"""Тонкий клиент AE3-Lite для публикации команд через history-logger."""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from typing import Any, Callable, Mapping, Optional

import httpx

from ae3lite.domain.errors import CommandPublishError
from ae3lite.infrastructure.clients.hl_metrics import (
    HL_BREAKER_STATE,
    HL_REQUEST_DURATION,
    HL_REQUEST_ERRORS,
)

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = frozenset(range(500, 600))

_BREAKER_CLOSED = 0
_BREAKER_OPEN = 1
_BREAKER_HALF_OPEN = 2


class _HlCircuitBreaker:
    """In-process circuit breaker для запросов к history-logger."""

    def __init__(
        self,
        *,
        fail_threshold: int,
        open_sec: float,
        now_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fail_threshold = max(1, int(fail_threshold))
        self._open_sec = max(0.1, float(open_sec))
        self._now_fn = now_fn
        self._consecutive_failures = 0
        self._state = _BREAKER_CLOSED
        self._opened_at = 0.0
        self._half_open_probe_in_flight = False
        HL_BREAKER_STATE.set(_BREAKER_CLOSED)

    def before_call(self) -> None:
        now = self._now_fn()
        if self._state == _BREAKER_OPEN:
            if now - self._opened_at >= self._open_sec:
                self._state = _BREAKER_HALF_OPEN
                self._half_open_probe_in_flight = False
                HL_BREAKER_STATE.set(_BREAKER_HALF_OPEN)
            else:
                HL_REQUEST_ERRORS.labels(kind="circuit_open").inc()
                raise CommandPublishError("hl_circuit_open")

        if self._state == _BREAKER_HALF_OPEN and self._half_open_probe_in_flight:
            HL_REQUEST_ERRORS.labels(kind="circuit_open").inc()
            raise CommandPublishError("hl_circuit_open")

        if self._state == _BREAKER_HALF_OPEN:
            self._half_open_probe_in_flight = True

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._state = _BREAKER_CLOSED
        self._half_open_probe_in_flight = False
        HL_BREAKER_STATE.set(_BREAKER_CLOSED)

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
        HL_BREAKER_STATE.set(_BREAKER_OPEN)


class HistoryLoggerClient:
    """Публикует команды только через endpoint `/commands` сервиса history-logger."""

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        source: str = "automation-engine",
        timeout_sec: float = 5.0,
        client: Optional[httpx.AsyncClient] = None,
        retry_backoff_sec: Optional[float] = None,
        max_retries: Optional[int] = None,
        breaker_fail_threshold: Optional[int] = None,
        breaker_open_sec: Optional[float] = None,
        now_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._base_url = str(base_url or os.getenv("HISTORY_LOGGER_URL", "http://history-logger:9300")).rstrip("/")
        self._token = str(token or os.getenv("HISTORY_LOGGER_API_TOKEN") or os.getenv("PY_INGEST_TOKEN") or "").strip()
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
            int(max_retries if max_retries is not None else os.getenv("AE_HL_MAX_RETRIES", "2")),
        )
        self._breaker = _HlCircuitBreaker(
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
            now_fn=now_fn,
        )

    async def publish(
        self,
        *,
        greenhouse_uid: str,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
        params: Mapping[str, Any],
        cmd_id: Optional[str] = None,
    ) -> str:
        payload = {
            "greenhouse_uid": greenhouse_uid,
            "zone_id": zone_id,
            "node_uid": node_uid,
            "channel": channel,
            "cmd": cmd,
            "params": dict(params),
            "source": self._source,
        }
        if cmd_id:
            payload["cmd_id"] = cmd_id
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        response = await self._post_with_retry("/commands", payload, headers)
        if response.status_code != 200:
            raise CommandPublishError(self._extract_error_message(response))

        try:
            body = response.json()
        except ValueError as exc:
            raise CommandPublishError("history-logger вернул некорректный JSON") from exc

        command_id = str(((body.get("data") or {}) if isinstance(body, dict) else {}).get("command_id") or "").strip()
        if not command_id:
            raise CommandPublishError("Ответ history-logger не содержит data.command_id")
        return command_id

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
                HL_REQUEST_DURATION.labels(path=path).observe(time.monotonic() - started_at)
                if attempt >= self._max_retries:
                    HL_REQUEST_ERRORS.labels(kind="timeout").inc()
                    self._breaker.record_failure()
                    raise CommandPublishError(
                        f"Запрос к history-logger завершился ошибкой: {self._format_request_error(exc=exc, path=path)}"
                    ) from exc
                await self._sleep_before_retry(path=path, attempt=attempt, reason=type(exc).__name__)
                attempt += 1
                continue
            except httpx.RequestError as exc:
                HL_REQUEST_DURATION.labels(path=path).observe(time.monotonic() - started_at)
                if attempt >= self._max_retries:
                    HL_REQUEST_ERRORS.labels(kind="transport").inc()
                    self._breaker.record_failure()
                    raise CommandPublishError(
                        f"Запрос к history-logger завершился ошибкой: {self._format_request_error(exc=exc, path=path)}"
                    ) from exc
                await self._sleep_before_retry(path=path, attempt=attempt, reason=type(exc).__name__)
                attempt += 1
                continue

            HL_REQUEST_DURATION.labels(path=path).observe(time.monotonic() - started_at)

            if response.status_code == 200:
                self._breaker.record_success()
                return response

            if response.status_code not in _RETRYABLE_STATUS_CODES:
                HL_REQUEST_ERRORS.labels(kind="4xx").inc()
                return response

            if attempt >= self._max_retries:
                HL_REQUEST_ERRORS.labels(kind="5xx").inc()
                self._breaker.record_failure()
                return response

            await self._sleep_before_retry(path=path, attempt=attempt, reason=f"http_{response.status_code}")
            attempt += 1

    async def _sleep_before_retry(self, *, path: str, attempt: int, reason: str) -> None:
        base_delay = self._retry_backoff_sec * (2**attempt)
        jitter_factor = random.uniform(0.75, 1.25)
        delay = max(0.0, base_delay * jitter_factor)
        logger.warning(
            "Повторный запрос к history-logger: path=%s attempt=%s reason=%s backoff_sec=%.2f",
            path,
            attempt + 1,
            reason,
            delay,
        )
        await asyncio.sleep(delay)

    async def _post(self, path: str, payload: Mapping[str, Any], headers: Mapping[str, str]) -> httpx.Response:
        if self._client is not None:
            return await self._client.post(f"{self._base_url}{path}", json=dict(payload), headers=dict(headers))
        async with httpx.AsyncClient(timeout=self._timeout_sec) as client:
            return await client.post(f"{self._base_url}{path}", json=dict(payload), headers=dict(headers))

    def _format_request_error(self, *, exc: httpx.RequestError, path: str) -> str:
        detail = str(exc).strip()
        request_url = ""
        if getattr(exc, "request", None) is not None and getattr(exc.request, "url", None) is not None:
            request_url = str(exc.request.url)
        else:
            request_url = f"{self._base_url}{path}"
        if detail:
            return f"{type(exc).__name__}: {detail} (url={request_url})"
        return f"{type(exc).__name__} (url={request_url})"

    def _extract_error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            detail = str(payload.get("detail") or payload.get("message") or "").strip()
            if detail:
                return detail
        text = str(response.text or "").strip()
        if text:
            return text
        return f"history-logger не смог опубликовать команду и вернул HTTP {response.status_code}"
