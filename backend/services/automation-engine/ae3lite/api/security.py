"""Security baseline checks for AE3-Lite ingress."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException

_logger = logging.getLogger(__name__)


def validate_scheduler_security_baseline(
    *,
    headers: Any,
    enforce: bool,
    scheduler_api_token: str,
    require_trace_id: bool,
    extract_trace_id_from_headers_fn: Callable[[Any], Optional[str]],
) -> None:
    if not enforce:
        return

    expected_token = str(scheduler_api_token or "").strip()
    if not expected_token:
        _logger.error("AE3 security: scheduler_api_token is not configured — rejecting with 500")
        raise HTTPException(status_code=500, detail="scheduler_security_token_not_configured")

    auth_header = str(headers.get("authorization") or "").strip()
    if auth_header != f"Bearer {expected_token}":
        _logger.warning("AE3 security: unauthorized request rejected (bad or missing token)")
        raise HTTPException(status_code=401, detail="unauthorized")

    if require_trace_id:
        trace_id = extract_trace_id_from_headers_fn(headers)
        if not trace_id:
            _logger.warning("AE3 security: request rejected — X-Trace-Id header missing")
            raise HTTPException(status_code=422, detail="missing_trace_id")


__all__ = ["validate_scheduler_security_baseline"]
