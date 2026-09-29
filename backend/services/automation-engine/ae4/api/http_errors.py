"""HTTP-ошибки ingress AE 1.0.0."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from common.error_catalog import enrich_error_payload, present_error
from common.fastapi_http_errors import enrich_http_exception_content as _shared_enrich


def api_error_detail(
    code: str,
    *,
    message: str | None = None,
    status_code: int = 400,
    **extra: Any,
) -> HTTPException:
    presentation = present_error(code, message)
    detail: dict[str, Any] = {
        "status": "error",
        "error": presentation["code"] or _normalize(code),
        "code": presentation["code"] or _normalize(code),
        "message": presentation["message"],
        "human_error_message": presentation["human_error_message"],
        "title": presentation["title"],
        **extra,
    }
    detail = enrich_error_payload(detail)
    return HTTPException(status_code=status_code, detail=detail)


def _normalize(code: str) -> str:
    return str(code or "").strip().lower().replace("-", "_")


def enrich_http_exception_content(exc: HTTPException) -> dict[str, Any]:
    return _shared_enrich(exc)


__all__ = ["api_error_detail", "enrich_http_exception_content"]
