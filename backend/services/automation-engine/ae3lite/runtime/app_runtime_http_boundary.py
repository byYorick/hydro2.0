"""app runtime http boundary: explicit dependencies and invocation data."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ae3lite.api.http_errors import api_error_detail, enrich_http_exception_content
from common.error_catalog import enrich_error_payload, present_error
from common.trace_context import clear_trace_id, extract_trace_id_from_headers, get_trace_id, set_trace_id


@dataclass(frozen=True)
class AppRuntimeHttpBoundaryPorts:
    internal_error_response: Callable[..., Any]
    request_zone_id: Callable[..., Any]
    response_error_code: Callable[..., Any]
    utcnow: Callable[..., Any]
    logger: Callable[..., Any]
    send_infra_alert: Callable[..., Any]
    send_infra_exception_alert: Callable[..., Any]


class AppRuntimeHttpBoundary:
    def __init__(self, ports: AppRuntimeHttpBoundaryPorts) -> None:
        self._ports = ports

    def internal_error_response(self, trace_id: Optional[str]) -> JSONResponse:
        presentation = present_error("ae3_internal_error", None)
        payload = enrich_error_payload(
            {
                "status": "error",
                "code": presentation["code"] or "ae3_internal_error",
                "error": presentation["code"] or "ae3_internal_error",
                "message": presentation["message"],
                "human_error_message": presentation["human_error_message"],
                "title": presentation["title"],
                "trace_id": trace_id,
            }
        )
        headers = {"X-Trace-Id": trace_id} if trace_id else {}
        return JSONResponse(status_code=500, content=payload, headers=headers)

    def response_error_code(self, response: Any) -> str | None:
        body = getattr(response, "body", None)
        if not body:
            return None
        try:
            raw = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else str(body)
            payload = json.loads(raw)
            if isinstance(payload, dict):
                code = str(payload.get("error") or payload.get("code") or "").strip()
                return code or None
        except Exception:
            return None
        return None

    def request_zone_id(self, request: Request) -> int | None:
        raw_zone_id = request.path_params.get("zone_id")
        if raw_zone_id is None:
            return None
        try:
            zone_id = int(raw_zone_id)
        except (TypeError, ValueError):
            return None
        return zone_id if zone_id > 0 else None

    def bind_http_boundary(self, *, app: Any, runtime_config: Any) -> Any:
        @app.exception_handler(HTTPException)
        async def localized_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
            return JSONResponse(
                status_code=exc.status_code,
                content=enrich_http_exception_content(exc),
            )

        @app.exception_handler(RequestValidationError)
        async def request_validation_exception_handler(
            request: Request,
            exc: RequestValidationError,
        ) -> JSONResponse:
            del request
            code = "validation_error"
            for err in exc.errors():
                location = tuple(err.get("loc") or ())
                if "idempotency_key" in location and err.get("type") == "missing":
                    code = "start_cycle_missing_idempotency_key"
                    break
            http_exc = api_error_detail(code, status_code=422)
            return JSONResponse(
                status_code=422,
                content=enrich_http_exception_content(http_exc),
            )

        @app.exception_handler(Exception)
        async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
            del request
            if isinstance(exc, HTTPException):
                raise exc
            return self._ports.internal_error_response(get_trace_id())

        @app.middleware("http")
        async def trace_middleware(request: Request, call_next: Any) -> Any:
            trace_id = extract_trace_id_from_headers(request.headers)
            effective_trace_id = set_trace_id(trace_id, allow_generate=True)
            started_at = self._ports.utcnow()
            try:
                response = await call_next(request)
            except HTTPException:
                clear_trace_id()
                raise
            except Exception as exc:
                duration_ms = max(0.0, (self._ports.utcnow() - started_at).total_seconds() * 1000.0)
                self._ports.logger().error(
                    "Unhandled AE3 API exception: method=%s path=%s duration_ms=%.2f error=%s",
                    request.method,
                    request.url.path,
                    duration_ms,
                    exc,
                    exc_info=True,
                    extra={"trace_id": effective_trace_id},
                )
                try:
                    await self._ports.send_infra_exception_alert(
                        error=exc,
                        code="ae3_api_unhandled_exception",
                        alert_type="AE3 API Unhandled Exception",
                        severity="error",
                        zone_id=None,
                        service="automation-engine",
                        component=f"api:{request.url.path}",
                        details={
                            "method": request.method,
                            "path": request.url.path,
                            "duration_ms": round(duration_ms, 2),
                            "trace_id": effective_trace_id,
                        },
                    )
                except Exception:
                    self._ports.logger().warning("Не удалось отправить alert для исключения AE3 API", exc_info=True)
                response = self._ports.internal_error_response(effective_trace_id)
                clear_trace_id()
                return response

            duration_ms = max(0.0, (self._ports.utcnow() - started_at).total_seconds() * 1000.0)
            if effective_trace_id:
                response.headers["X-Trace-Id"] = effective_trace_id

            if runtime_config.verbose_http_logging or response.status_code >= 500:
                log_level = logging.ERROR if response.status_code >= 500 else logging.DEBUG
                self._ports.logger().log(
                    log_level,
                    "AE3 API request completed: method=%s path=%s status=%s duration_ms=%.2f",
                    request.method,
                    request.url.path,
                    response.status_code,
                    duration_ms,
                    extra={"trace_id": effective_trace_id},
                )

            if 400 <= response.status_code < 500:
                zone_id = self._ports.request_zone_id(request)
                error_code = self._ports.response_error_code(response)
                self._ports.logger().warning(
                    "AE3 API client error",
                    extra={
                        "path": request.url.path,
                        "status": response.status_code,
                        "error": error_code,
                        "trace_id": effective_trace_id,
                        "zone_id": zone_id,
                    },
                )

            if response.status_code >= 500:
                try:
                    await self._ports.send_infra_alert(
                        code="ae3_api_http_5xx",
                        alert_type="AE3 API HTTP 5xx",
                        message=f"AE3 API вернул HTTP {response.status_code} для {request.method} {request.url.path}",
                        severity="error",
                        zone_id=None,
                        service="automation-engine",
                        component=f"api:{request.url.path}",
                        error_type=f"http_{response.status_code}",
                        details={
                            "method": request.method,
                            "path": request.url.path,
                            "status_code": response.status_code,
                            "duration_ms": round(duration_ms, 2),
                            "trace_id": effective_trace_id,
                        },
                    )
                except Exception:
                    self._ports.logger().warning("Не удалось отправить alert для AE3 API HTTP 5xx", exc_info=True)

            clear_trace_id()
            return response
