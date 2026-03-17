"""Tests for the None-safe id extraction in compat_endpoints.py.

``bind_start_cycle_route`` builds 409 responses that include ``active_intent_id``
extracted via ``(lambda v: int(v) if v is not None else None)``.
This ensures that a missing ``id`` key → None (not 0) and a present integer
(including 0) is preserved correctly.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException

from ae3lite.api import bind_start_cycle_route
from ae3lite.api.contracts import StartCycleRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _idempotency_key(suffix: str = "abc") -> str:
    """Return an idempotency_key that satisfies min_length=8."""
    return f"sch:z7:{suffix}"


def _bind_with_claim(claim_return: dict) -> object:
    """Bind a start-cycle route whose claim fn returns the given dict, return endpoint."""
    app = FastAPI()

    async def validate_zone(_: int) -> None:
        return None

    async def validate_security(_: object) -> None:
        return None

    async def claim_intent(*, zone_id: int, req: object, now: object) -> dict:
        return claim_return

    async def mark_intent_terminal(**kwargs: object) -> None:
        return None

    bind_start_cycle_route(
        app,
        validate_scheduler_zone_fn=validate_zone,
        validate_scheduler_security_baseline_fn=validate_security,
        is_start_cycle_rate_limit_enabled_fn=lambda: False,
        start_cycle_rate_limit_check_fn=lambda _: True,
        start_cycle_rate_limit_window_sec_fn=lambda: 10,
        start_cycle_rate_limit_max_requests_fn=lambda: 30,
        claim_start_cycle_intent_fn=claim_intent,
        create_task_from_intent_fn=None,
        ensure_solution_tank_startup_reset_fn=None,
        kick_worker_fn=lambda: None,
        build_start_cycle_response_fn=lambda **kwargs: {},
        mark_intent_terminal_fn=mark_intent_terminal,
        logger=SimpleNamespace(
            warning=lambda *a, **kw: None,
            debug=lambda *a, **kw: None,
        ),
    )
    return next(r.endpoint for r in app.routes if r.path == "/zones/{zone_id}/start-cycle")


_FAKE_REQUEST = SimpleNamespace(
    headers={"authorization": "Bearer t", "x-trace-id": "trace-test"},
)


# ---------------------------------------------------------------------------
# zone_busy — active_intent_id extraction
# ---------------------------------------------------------------------------

class TestZoneBusyActiveIntentId:
    async def test_active_intent_id_none_when_intent_row_has_no_id(self) -> None:
        """Missing 'id' key in intent row → active_intent_id must be None, not 0."""
        endpoint = _bind_with_claim(
            {"decision": "zone_busy", "intent": {"status": "running"}}
        )
        req = StartCycleRequest(idempotency_key=_idempotency_key())

        with pytest.raises(HTTPException) as exc:
            await endpoint(zone_id=7, request=_FAKE_REQUEST, req=req)

        assert exc.value.status_code == 409
        detail = exc.value.detail
        assert detail["error"] == "start_cycle_zone_busy"
        assert detail["active_intent_id"] is None

    async def test_active_intent_id_preserved_as_positive_int(self) -> None:
        endpoint = _bind_with_claim(
            {"decision": "zone_busy", "intent": {"id": 42, "status": "running"}}
        )
        req = StartCycleRequest(idempotency_key=_idempotency_key())

        with pytest.raises(HTTPException) as exc:
            await endpoint(zone_id=7, request=_FAKE_REQUEST, req=req)

        assert exc.value.status_code == 409
        assert exc.value.detail["active_intent_id"] == 42

    async def test_active_intent_id_zero_preserved(self) -> None:
        """id=0 is a valid integer and must NOT be coerced to None.

        The fix uses ``int(v) if v is not None else None`` which correctly
        keeps 0 rather than treating it as falsy and returning None.
        """
        endpoint = _bind_with_claim(
            {"decision": "zone_busy", "intent": {"id": 0, "status": "running"}}
        )
        req = StartCycleRequest(idempotency_key=_idempotency_key())

        with pytest.raises(HTTPException) as exc:
            await endpoint(zone_id=7, request=_FAKE_REQUEST, req=req)

        assert exc.value.status_code == 409
        assert exc.value.detail["active_intent_id"] == 0

    async def test_zone_id_in_409_response_is_requested_zone(self) -> None:
        endpoint = _bind_with_claim(
            {"decision": "zone_busy", "intent": {"id": 99, "status": "running"}}
        )
        req = StartCycleRequest(idempotency_key=_idempotency_key())

        with pytest.raises(HTTPException) as exc:
            await endpoint(zone_id=7, request=_FAKE_REQUEST, req=req)

        assert exc.value.detail["zone_id"] == 7

    async def test_active_status_defaults_to_running_when_status_absent(self) -> None:
        endpoint = _bind_with_claim(
            {"decision": "zone_busy", "intent": {"id": 5}}
        )
        req = StartCycleRequest(idempotency_key=_idempotency_key())

        with pytest.raises(HTTPException) as exc:
            await endpoint(zone_id=7, request=_FAKE_REQUEST, req=req)

        assert exc.value.detail["active_status"] == "running"


# ---------------------------------------------------------------------------
# Other decisions
# ---------------------------------------------------------------------------

class TestOtherDecisions:
    async def test_missing_intent_returns_409(self) -> None:
        endpoint = _bind_with_claim({"decision": "missing", "intent": {}})
        req = StartCycleRequest(idempotency_key=_idempotency_key())

        with pytest.raises(HTTPException) as exc:
            await endpoint(zone_id=7, request=_FAKE_REQUEST, req=req)

        assert exc.value.status_code == 409
        assert exc.value.detail["error"] == "start_cycle_intent_not_found"

    async def test_unknown_decision_returns_503(self) -> None:
        endpoint = _bind_with_claim({"decision": "unknown_state", "intent": {}})
        req = StartCycleRequest(idempotency_key=_idempotency_key())

        with pytest.raises(HTTPException) as exc:
            await endpoint(zone_id=7, request=_FAKE_REQUEST, req=req)

        assert exc.value.status_code == 503
        assert exc.value.detail["error"] == "start_cycle_intent_claim_unavailable"
