from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import api
from ae2lite.api_contracts import StartCycleRequest
from ae2lite.api_rate_limit import SlidingWindowRateLimiter


@pytest.mark.asyncio
async def test_zone_start_cycle_returns_429_when_rate_limited(monkeypatch):
    async def fake_validate_zone(_zone_id: int):
        return None

    async def fake_validate_security(_request):
        return None

    async def fake_claim_start_cycle_intent(*_args, **_kwargs):
        return {"decision": "deduplicated", "intent": {"id": 1, "status": "running"}}

    monkeypatch.setattr(api, "_validate_scheduler_zone", fake_validate_zone)
    monkeypatch.setattr(api, "_validate_scheduler_security_baseline", fake_validate_security)
    monkeypatch.setattr(api, "policy_claim_start_cycle_intent", fake_claim_start_cycle_intent)
    monkeypatch.setattr(api, "_AE_START_CYCLE_RATE_LIMIT_ENABLED", True)
    limiter = type("AlwaysDenyLimiter", (), {"check": lambda self, **_kwargs: False})()
    monkeypatch.setattr(api, "_start_cycle_rate_limiter", limiter)

    with pytest.raises(HTTPException) as exc:
        await api.zone_start_cycle(
            zone_id=15,
            request=SimpleNamespace(headers={"x-trace-id": "trace-rate-1"}),
            req=StartCycleRequest(
                source="laravel_scheduler",
                idempotency_key="sch:z15:irrigation:2026-02-22T10:00:00Z",
            ),
        )

    assert exc.value.status_code == 429
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("error") == "start_cycle_rate_limited"
    assert detail.get("zone_id") == 15


@pytest.mark.asyncio
async def test_zone_start_cycle_rate_limit_smoke_for_burst(monkeypatch):
    now = {"v": 0.0}

    def fake_now() -> float:
        return now["v"]

    async def fake_validate_zone(_zone_id: int):
        return None

    async def fake_validate_security(_request):
        return None

    async def fake_claim_start_cycle_intent(*_args, **_kwargs):
        return {"decision": "deduplicated", "intent": {"id": 2, "status": "running"}}

    monkeypatch.setattr(api, "_validate_scheduler_zone", fake_validate_zone)
    monkeypatch.setattr(api, "_validate_scheduler_security_baseline", fake_validate_security)
    monkeypatch.setattr(api, "policy_claim_start_cycle_intent", fake_claim_start_cycle_intent)
    monkeypatch.setattr(api, "_AE_START_CYCLE_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(
        api,
        "_start_cycle_rate_limiter",
        SlidingWindowRateLimiter(max_requests=2, window_sec=10.0, now_fn=fake_now),
    )

    req = StartCycleRequest(
        source="laravel_scheduler",
        idempotency_key="sch:z20:irrigation:2026-02-22T10:10:00Z",
    )
    request = SimpleNamespace(headers={"x-trace-id": "trace-rate-2"})

    first = await api.zone_start_cycle(zone_id=20, request=request, req=req)
    second = await api.zone_start_cycle(zone_id=20, request=request, req=req)
    assert first["data"]["accepted"] is True
    assert second["data"]["accepted"] is True

    with pytest.raises(HTTPException) as exc:
        await api.zone_start_cycle(zone_id=20, request=request, req=req)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_zone_start_cycle_rate_limit_cannot_be_bypassed_by_source_change(monkeypatch):
    now = {"v": 0.0}

    def fake_now() -> float:
        return now["v"]

    async def fake_validate_zone(_zone_id: int):
        return None

    async def fake_validate_security(_request):
        return None

    async def fake_claim_start_cycle_intent(*_args, **_kwargs):
        return {"decision": "deduplicated", "intent": {"id": 3, "status": "running"}}

    monkeypatch.setattr(api, "_validate_scheduler_zone", fake_validate_zone)
    monkeypatch.setattr(api, "_validate_scheduler_security_baseline", fake_validate_security)
    monkeypatch.setattr(api, "policy_claim_start_cycle_intent", fake_claim_start_cycle_intent)
    monkeypatch.setattr(api, "_AE_START_CYCLE_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(
        api,
        "_start_cycle_rate_limiter",
        SlidingWindowRateLimiter(max_requests=2, window_sec=10.0, now_fn=fake_now),
    )

    request = SimpleNamespace(headers={"x-trace-id": "trace-rate-3"})
    req_scheduler = StartCycleRequest(
        source="laravel_scheduler",
        idempotency_key="sch:z21:irrigation:2026-02-22T10:20:00Z",
    )
    req_other_source = StartCycleRequest(
        source="any_untrusted_source",
        idempotency_key="sch:z21:irrigation:2026-02-22T10:20:01Z",
    )

    first = await api.zone_start_cycle(zone_id=21, request=request, req=req_scheduler)
    second = await api.zone_start_cycle(zone_id=21, request=request, req=req_other_source)
    assert first["data"]["accepted"] is True
    assert second["data"]["accepted"] is True

    with pytest.raises(HTTPException) as exc:
        await api.zone_start_cycle(zone_id=21, request=request, req=req_scheduler)
    assert exc.value.status_code == 429
