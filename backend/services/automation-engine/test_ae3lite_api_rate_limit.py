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
