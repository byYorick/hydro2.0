"""Unit tests for validate_scheduler_security_baseline."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from ae3lite.api.security import validate_scheduler_security_baseline


def _call(
    *,
    enforce: bool = True,
    token: str = "secret",
    auth_header: str | None = "Bearer secret",
    require_trace_id: bool = False,
    trace_id: str | None = "trace-123",
) -> None:
    headers: dict[str, str] = {}
    if auth_header is not None:
        headers["authorization"] = auth_header
    validate_scheduler_security_baseline(
        headers=headers,
        enforce=enforce,
        scheduler_api_token=token,
        require_trace_id=require_trace_id,
        extract_trace_id_from_headers_fn=lambda h: trace_id,
    )


# ── enforce=False bypasses all checks ────────────────────────────────────────

def test_enforce_false_passes_even_without_token() -> None:
    _call(enforce=False, token="", auth_header=None, require_trace_id=True, trace_id=None)


def test_enforce_false_passes_with_wrong_token() -> None:
    _call(enforce=False, token="real-secret", auth_header="Bearer wrong")


# ── token not configured ──────────────────────────────────────────────────────

def test_empty_token_returns_500() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _call(token="", auth_header="Bearer anything")
    assert exc_info.value.status_code == 500
    assert "not_configured" in exc_info.value.detail


def test_whitespace_only_token_returns_500() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _call(token="   ", auth_header="Bearer secret")
    assert exc_info.value.status_code == 500


# ── bad / missing token ───────────────────────────────────────────────────────

def test_wrong_token_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _call(token="secret", auth_header="Bearer wrong")
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "unauthorized"


def test_missing_auth_header_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _call(token="secret", auth_header=None)
    assert exc_info.value.status_code == 401


def test_non_bearer_scheme_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _call(token="secret", auth_header="Basic secret")
    assert exc_info.value.status_code == 401


def test_bearer_without_space_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _call(token="secret", auth_header="Bearersecret")
    assert exc_info.value.status_code == 401


# ── valid token ───────────────────────────────────────────────────────────────

def test_correct_token_passes() -> None:
    _call(token="my-token", auth_header="Bearer my-token")  # no exception


def test_correct_token_with_special_chars() -> None:
    _call(token="tok!@#$%", auth_header="Bearer tok!@#$%")


# ── require_trace_id ──────────────────────────────────────────────────────────

def test_missing_trace_id_returns_422_when_required() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _call(require_trace_id=True, trace_id=None)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "missing_trace_id"


def test_empty_trace_id_returns_422_when_required() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _call(require_trace_id=True, trace_id="")
    assert exc_info.value.status_code == 422


def test_present_trace_id_passes_when_required() -> None:
    _call(require_trace_id=True, trace_id="trace-abc-123")  # no exception


def test_trace_id_not_checked_when_not_required() -> None:
    _call(require_trace_id=False, trace_id=None)  # no exception
