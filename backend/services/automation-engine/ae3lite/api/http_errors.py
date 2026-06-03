"""HTTP-ошибки AE3 ingress с локализованным human_error_message."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from common.error_catalog import enrich_error_payload, present_error
from common.fastapi_http_errors import enrich_http_exception_content as _shared_enrich_http_exception_content


def api_error_detail(
    code: str,
    *,
    message: str | None = None,
    status_code: int = 400,
    **extra: Any,
) -> HTTPException:
    """HTTPException с detail, обогащённым каталогом error_codes.json."""
    presentation = present_error(code, message)
    detail: dict[str, Any] = {
        "status": "error",
        "error": presentation["code"] or _normalize_legacy(code),
        "code": presentation["code"] or _normalize_legacy(code),
        "message": presentation["message"],
        "human_error_message": presentation["human_error_message"],
        "title": presentation["title"],
        **extra,
    }
    detail = enrich_error_payload(detail)
    return HTTPException(status_code=status_code, detail=detail)


def _normalize_legacy(code: str) -> str:
    return str(code or "").strip().lower().replace("-", "_")


def enrich_http_exception_content(exc: HTTPException) -> dict[str, Any]:
    """Тело JSON для exception handler (совместимо с Laravel proxy)."""
    return _shared_enrich_http_exception_content(exc)
