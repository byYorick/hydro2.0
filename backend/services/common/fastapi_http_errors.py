"""Обогащение FastAPI HTTPException для human_error_message (history-logger, AE3)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from common.error_catalog import enrich_error_payload, present_error


def enrich_http_exception_content(exc: HTTPException) -> dict[str, Any]:
    """Тело JSON для exception handler (совместимо с Laravel proxy)."""
    detail = exc.detail
    if isinstance(detail, dict):
        enriched = enrich_error_payload(detail)
        return {
            "status": "error",
            **enriched,
            "detail": enriched,
        }
    if isinstance(detail, str):
        presentation = present_error(None, detail)
        return {
            "status": "error",
            "message": presentation["message"] or detail,
            "human_error_message": presentation["message"] or detail,
            "detail": detail,
        }
    return {"status": "error", "detail": detail}
