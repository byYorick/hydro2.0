from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import api
from ae2lite.api_contracts import StartCycleRequest


@pytest.mark.asyncio
async def test_start_cycle_returns_401_on_invalid_scheduler_token(monkeypatch):
    async def fake_validate_zone(_zone_id: int):
        return None

    monkeypatch.setattr(api, "_validate_scheduler_zone", fake_validate_zone)
    monkeypatch.setattr(api, "_AE_SCHEDULER_SECURITY_BASELINE_ENFORCE", True)
    monkeypatch.setattr(api, "_AE_SCHEDULER_REQUIRE_TRACE_ID", True)
    monkeypatch.setattr(api, "_AE_SCHEDULER_API_TOKEN", "expected-token")

    with pytest.raises(HTTPException) as exc:
        await api.zone_start_cycle(
            zone_id=42,
            request=SimpleNamespace(headers={"authorization": "Bearer wrong-token", "x-trace-id": "trace-401"}),
            req=StartCycleRequest(source="laravel_scheduler", idempotency_key="security-int-401"),
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "unauthorized"


@pytest.mark.asyncio
async def test_start_cycle_returns_422_when_trace_id_missing(monkeypatch):
    async def fake_validate_zone(_zone_id: int):
        return None

    monkeypatch.setattr(api, "_validate_scheduler_zone", fake_validate_zone)
    monkeypatch.setattr(api, "_AE_SCHEDULER_SECURITY_BASELINE_ENFORCE", True)
    monkeypatch.setattr(api, "_AE_SCHEDULER_REQUIRE_TRACE_ID", True)
    monkeypatch.setattr(api, "_AE_SCHEDULER_API_TOKEN", "expected-token")

    with pytest.raises(HTTPException) as exc:
        await api.zone_start_cycle(
            zone_id=42,
            request=SimpleNamespace(headers={"authorization": "Bearer expected-token"}),
            req=StartCycleRequest(source="laravel_scheduler", idempotency_key="security-int-422"),
        )

    assert exc.value.status_code == 422
    assert exc.value.detail == "missing_trace_id"
