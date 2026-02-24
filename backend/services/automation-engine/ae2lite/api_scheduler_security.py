"""Security baseline checks for scheduler -> automation-engine ingress."""

from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import HTTPException


def validate_scheduler_security_baseline(
    *,
    headers: Any,
    enforce: bool,
    scheduler_api_token: str,
    require_trace_id: bool,
    extract_trace_id_from_headers_fn: Callable[[Any], Optional[str]],
) -> None:
    """Validate baseline scheduler ingress security.

    Baseline profile:
    - Authorization: Bearer <service-token>
    - X-Trace-Id (or equivalent candidate accepted by trace extractor)
    """
    if not enforce:
        return

    expected_token = str(scheduler_api_token or "").strip()
    if not expected_token:
        raise HTTPException(status_code=500, detail="scheduler_security_token_not_configured")

    auth_header = str(headers.get("authorization") or "").strip()
    if auth_header != f"Bearer {expected_token}":
        raise HTTPException(status_code=401, detail="unauthorized")

    if require_trace_id:
        trace_id = extract_trace_id_from_headers_fn(headers)
        if not trace_id:
            raise HTTPException(status_code=422, detail="missing_trace_id")


__all__ = ["validate_scheduler_security_baseline"]
