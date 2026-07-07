"""Unit tests for validate_scheduler_security_baseline."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from ae3lite.api.security import validate_scheduler_security_baseline
from ae3lite.api.validation import validate_scheduler_zone
import ae3lite.runtime.app as runtime_app_module


def _http_detail_code(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        return str(detail.get("code") or detail.get("error") or "")
    return str(detail)


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
    assert "not_configured" in _http_detail_code(exc_info.value)


def test_whitespace_only_token_returns_500() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _call(token="   ", auth_header="Bearer secret")
    assert exc_info.value.status_code == 500


# ── bad / missing token ───────────────────────────────────────────────────────

def test_wrong_token_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _call(token="secret", auth_header="Bearer wrong")
    assert exc_info.value.status_code == 401
    assert _http_detail_code(exc_info.value) == "unauthorized"


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
    assert _http_detail_code(exc_info.value) == "missing_trace_id"


def test_empty_trace_id_returns_422_when_required() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _call(require_trace_id=True, trace_id="")
    assert exc_info.value.status_code == 422


def test_present_trace_id_passes_when_required() -> None:
    _call(require_trace_id=True, trace_id="trace-abc-123")  # no exception


def test_trace_id_not_checked_when_not_required() -> None:
    _call(require_trace_id=False, trace_id=None)  # no exception


@pytest.mark.asyncio
async def test_validate_scheduler_zone_rejects_legacy_runtime() -> None:
    async def fetch_fn(_query: str, zone_id: int):
        return [{"id": zone_id, "automation_runtime": "legacy"}]

    with pytest.raises(HTTPException) as exc_info:
        await validate_scheduler_zone(
            7,
            fetch_fn=fetch_fn,
            logger=SimpleNamespace(error=lambda *args, **kwargs: None),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "start_cycle_unsupported_runtime"


def _build_state_test_app(monkeypatch: pytest.MonkeyPatch):
    async def _run_state(**kwargs):
        return {"zone_id": kwargs.get("zone_id", 7), "state": "READY"}

    bundle = SimpleNamespace(
        create_task_from_intent_use_case=None,
        solution_tank_startup_guard_use_case=None,
        get_zone_control_state_use_case=SimpleNamespace(run=lambda **kwargs: {"control_mode": "auto"}),
        request_manual_step_use_case=None,
        set_control_mode_use_case=None,
        get_zone_automation_state_use_case=SimpleNamespace(run=_run_state),
        task_status_read_model=None,
        zone_intent_repository=None,
        worker=SimpleNamespace(kick=lambda: None, recover_on_startup=lambda: None, drain_health=lambda: (True, "ok")),
        http_client=SimpleNamespace(aclose=lambda: None),
        history_logger_client=SimpleNamespace(),
    )
    monkeypatch.setattr(runtime_app_module, "build_ae3_runtime_bundle", lambda **_kwargs: bundle)

    async def fetch_fn(query: str, *args: object):
        if "FROM zones" in query:
            return [{"id": args[0], "automation_runtime": "ae3"}]
        return [{"ready": 1}]

    monkeypatch.setattr(runtime_app_module, "fetch", fetch_fn)
    cfg = SimpleNamespace(
        start_cycle_rate_limit_max_requests=30,
        start_cycle_rate_limit_window_sec=10,
        start_cycle_rate_limit_enabled=False,
        start_cycle_claim_stale_sec=60,
        start_cycle_running_stale_sec=300,
        db_dsn="",
        scheduler_security_baseline_enforce=True,
        scheduler_api_token="test-token",
        scheduler_require_trace_id=False,
        verbose_http_logging=False,
    )
    cfg.validate = lambda: None
    cfg.validated = 1
    return runtime_app_module.create_app(cfg)


@pytest.mark.asyncio
async def test_state_endpoint_requires_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_state_test_app(monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get("/zones/7/state")
        assert denied.status_code == 401
        assert denied.json()["code"] == "unauthorized"

        allowed = await client.get(
            "/zones/7/state",
            headers={"Authorization": "Bearer test-token"},
        )
        assert allowed.status_code == 200
        assert allowed.json()["state"] == "READY"


@pytest.mark.asyncio
async def test_unhandled_route_exception_returns_500_without_internal_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run_state_boom(**kwargs):
        raise RuntimeError("secret db password leak")

    bundle = SimpleNamespace(
        create_task_from_intent_use_case=None,
        solution_tank_startup_guard_use_case=None,
        get_zone_control_state_use_case=SimpleNamespace(run=lambda **kwargs: None),
        request_manual_step_use_case=None,
        set_control_mode_use_case=None,
        get_zone_automation_state_use_case=SimpleNamespace(run=_run_state_boom),
        task_status_read_model=None,
        zone_intent_repository=None,
        worker=SimpleNamespace(kick=lambda: None, recover_on_startup=lambda: None, drain_health=lambda: (True, "ok")),
        http_client=SimpleNamespace(aclose=lambda: None),
        history_logger_client=SimpleNamespace(),
    )
    monkeypatch.setattr(runtime_app_module, "build_ae3_runtime_bundle", lambda **_kwargs: bundle)

    async def fetch_fn(query: str, *args: object):
        if "FROM zones" in query:
            return [{"id": args[0], "automation_runtime": "ae3"}]
        return [{"ready": 1}]

    monkeypatch.setattr(runtime_app_module, "fetch", fetch_fn)
    cfg = SimpleNamespace(
        start_cycle_rate_limit_max_requests=30,
        start_cycle_rate_limit_window_sec=10,
        start_cycle_rate_limit_enabled=False,
        start_cycle_claim_stale_sec=60,
        start_cycle_running_stale_sec=300,
        db_dsn="",
        scheduler_security_baseline_enforce=True,
        scheduler_api_token="test-token",
        scheduler_require_trace_id=False,
        verbose_http_logging=False,
    )
    cfg.validate = lambda: None
    cfg.validated = 1
    app = runtime_app_module.create_app(cfg)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/zones/7/state",
            headers={"Authorization": "Bearer test-token", "X-Trace-Id": "trace-500-test"},
        )

    assert response.status_code == 500
    payload = response.json()
    assert payload["code"] == "ae3_internal_error"
    assert payload.get("trace_id") == "trace-500-test"
    assert "secret db password leak" not in response.text


@pytest.mark.asyncio
async def test_start_cycle_missing_idempotency_key_returns_catalog_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_state_test_app(monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/zones/7/start-cycle",
            headers={"Authorization": "Bearer test-token"},
            json={"source": "laravel_scheduler"},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "start_cycle_missing_idempotency_key"
