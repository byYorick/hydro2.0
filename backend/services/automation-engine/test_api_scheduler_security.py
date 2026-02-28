from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from ae2lite.api_scheduler_security import validate_scheduler_security_baseline


def _extract_trace_id(headers) -> str | None:
    return (headers.get("x-trace-id") or "").strip() or None


def test_scheduler_security_skipped_when_enforce_disabled():
    validate_scheduler_security_baseline(
        headers={},
        enforce=False,
        scheduler_api_token="",
        require_trace_id=True,
        extract_trace_id_from_headers_fn=_extract_trace_id,
    )


def test_scheduler_security_fails_when_token_not_configured():
    with pytest.raises(HTTPException) as exc:
        validate_scheduler_security_baseline(
            headers={"authorization": "Bearer token", "x-trace-id": "trace-1"},
            enforce=True,
            scheduler_api_token="",
            require_trace_id=True,
            extract_trace_id_from_headers_fn=_extract_trace_id,
        )

    assert exc.value.status_code == 500
    assert exc.value.detail == "scheduler_security_token_not_configured"


def test_scheduler_security_rejects_invalid_bearer():
    with pytest.raises(HTTPException) as exc:
        validate_scheduler_security_baseline(
            headers={"authorization": "Bearer wrong", "x-trace-id": "trace-1"},
            enforce=True,
            scheduler_api_token="expected-token",
            require_trace_id=True,
            extract_trace_id_from_headers_fn=_extract_trace_id,
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "unauthorized"


def test_scheduler_security_requires_trace_id_when_enabled():
    with pytest.raises(HTTPException) as exc:
        validate_scheduler_security_baseline(
            headers={"authorization": "Bearer expected-token"},
            enforce=True,
            scheduler_api_token="expected-token",
            require_trace_id=True,
            extract_trace_id_from_headers_fn=_extract_trace_id,
        )

    assert exc.value.status_code == 422
    assert exc.value.detail == "missing_trace_id"


def test_scheduler_security_accepts_valid_request():
    headers = SimpleNamespace(
        get=lambda key, default=None: {
            "authorization": "Bearer expected-token",
            "x-trace-id": "trace-ok",
        }.get(key, default)
    )
    validate_scheduler_security_baseline(
        headers=headers,
        enforce=True,
        scheduler_api_token="expected-token",
        require_trace_id=True,
        extract_trace_id_from_headers_fn=_extract_trace_id,
    )
