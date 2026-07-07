"""Unit tests for SlidingWindowRateLimiter."""
from __future__ import annotations

import pytest

from ae3lite.api.rate_limit import SlidingWindowRateLimiter


def _make(max_requests: int = 3, window_sec: float = 10.0) -> tuple[SlidingWindowRateLimiter, list[float]]:
    ts = [0.0]
    rl = SlidingWindowRateLimiter(max_requests=max_requests, window_sec=window_sec, now_fn=lambda: ts[0])
    return rl, ts


# ── basic allow / block ───────────────────────────────────────────────────────

def test_allows_requests_within_limit() -> None:
    rl, _ = _make(max_requests=3)
    assert rl.check(zone_id=1) is True
    assert rl.check(zone_id=1) is True
    assert rl.check(zone_id=1) is True


def test_blocks_after_max_requests_exceeded() -> None:
    rl, _ = _make(max_requests=2)
    assert rl.check(zone_id=1) is True
    assert rl.check(zone_id=1) is True
    assert rl.check(zone_id=1) is False


def test_block_does_not_advance_counter() -> None:
    """A rejected request must not be counted (idempotency)."""
    rl, _ = _make(max_requests=1)
    assert rl.check(zone_id=1) is True   # fills limit
    assert rl.check(zone_id=1) is False  # blocked, not counted
    assert rl.check(zone_id=1) is False  # still blocked


# ── window expiry ─────────────────────────────────────────────────────────────

def test_allows_again_after_window_expires() -> None:
    rl, ts = _make(max_requests=1, window_sec=10.0)
    assert rl.check(zone_id=1) is True
    assert rl.check(zone_id=1) is False  # blocked
    ts[0] = 11.0                         # move past window
    assert rl.check(zone_id=1) is True   # allowed again


def test_partial_window_still_blocks() -> None:
    rl, ts = _make(max_requests=1, window_sec=10.0)
    assert rl.check(zone_id=1) is True
    ts[0] = 5.0  # still within window
    assert rl.check(zone_id=1) is False


# ── per-zone isolation ────────────────────────────────────────────────────────

def test_zones_are_independent() -> None:
    rl, _ = _make(max_requests=1)
    assert rl.check(zone_id=1) is True
    assert rl.check(zone_id=1) is False  # zone 1 blocked
    assert rl.check(zone_id=2) is True   # zone 2 not affected
    assert rl.check(zone_id=2) is False  # zone 2 now also blocked


def test_large_zone_ids_work() -> None:
    rl, _ = _make(max_requests=1)
    assert rl.check(zone_id=999999) is True
    assert rl.check(zone_id=999999) is False


# ── disabled limiter ─────────────────────────────────────────────────────────

def test_disabled_when_max_requests_zero() -> None:
    rl, _ = _make(max_requests=0)
    for _ in range(100):
        assert rl.check(zone_id=1) is True


def test_disabled_when_window_sec_zero() -> None:
    rl, _ = _make(window_sec=0.0)
    for _ in range(100):
        assert rl.check(zone_id=1) is True


# ── sweep stale entries ───────────────────────────────────────────────────────

def test_sweep_removes_stale_entries() -> None:
    """After window expires, internal event queues are cleaned up during sweep."""
    rl, ts = _make(max_requests=2, window_sec=5.0)
    rl.check(zone_id=10)
    rl.check(zone_id=20)
    ts[0] = 6.0  # triggers sweep on next check
    rl.check(zone_id=99)
    # After sweep, zone 10 and 20 are stale — their events should be gone.
    # zone 10 should now be allowed again:
    assert rl.check(zone_id=10) is True


def test_multiple_zones_swept_after_window() -> None:
    rl, ts = _make(max_requests=1, window_sec=3.0)
    for zone in range(1, 6):
        rl.check(zone_id=zone)  # fill each zone
    ts[0] = 4.0  # expire all
    for zone in range(1, 6):
        assert rl.check(zone_id=zone) is True  # all should be allowed again


# ── source parameter is ignored ──────────────────────────────────────────────

def test_source_parameter_has_no_effect() -> None:
    rl, _ = _make(max_requests=1)
    assert rl.check(zone_id=1, source="scheduler") is True
    assert rl.check(zone_id=1, source="api") is False  # same zone, blocked


def test_evicts_lru_when_max_keys_exceeded() -> None:
    rl = SlidingWindowRateLimiter(max_requests=1, window_sec=10.0, max_keys=2)
    assert rl.check(zone_id=1) is True
    assert rl.check(zone_id=2) is True
    assert rl.check(zone_id=3) is True
    assert 1 not in rl._events
    assert rl.check(zone_id=1) is True


@pytest.mark.asyncio
async def test_state_endpoint_rate_limit_returns_429(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from httpx import ASGITransport, AsyncClient

    import ae3lite.runtime.app as runtime_app_module

    async def _run_state(**kwargs):
        return {"zone_id": kwargs.get("zone_id", 7), "state": "READY"}

    bundle = SimpleNamespace(
        create_task_from_intent_use_case=None,
        solution_tank_startup_guard_use_case=None,
        get_zone_control_state_use_case=SimpleNamespace(run=lambda **kwargs: None),
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
        start_cycle_rate_limit_enabled=True,
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
    headers = {"Authorization": "Bearer test-token"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(60):
            response = await client.get("/zones/7/state", headers=headers)
            assert response.status_code == 200
        blocked = await client.get("/zones/7/state", headers=headers)

    assert blocked.status_code == 429
    assert blocked.json()["code"] == "start_cycle_rate_limited"
