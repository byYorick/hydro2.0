"""Unit tests for BaseStageHandler._checkpoint() hot-swap semantics (Phase 5.5).

Verifies the return contract without touching the real DB snapshot pipeline:
- live_reload_enabled=False → returns plan.runtime unchanged
- zone_id=0 → returns plan.runtime, result='disabled'
- DB-dependent paths → mocked at get_pool import boundary
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from _test_support_runtime_plan import make_runtime_plan
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.infrastructure import metrics as _metrics


NOW = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)


def _handler(*, live_reload_enabled: bool = False) -> BaseStageHandler:
    return BaseStageHandler(
        runtime_monitor=object(),
        command_gateway=object(),
        live_reload_enabled=live_reload_enabled,
    )


def _plan():
    runtime = make_runtime_plan()
    return SimpleNamespace(runtime=runtime)


def _task(zone_id: int = 1):
    return SimpleNamespace(
        zone_id=zone_id,
        id=100,
        current_stage="clean_fill_check",
        grow_cycle_id=10,
    )


@pytest.mark.asyncio
async def test_checkpoint_disabled_returns_current_runtime() -> None:
    plan = _plan()
    handler = _handler(live_reload_enabled=False)
    result = await handler._checkpoint(task=_task(), plan=plan, now=NOW)
    assert result is plan.runtime, "disabled checkpoint must return original runtime"


@pytest.mark.asyncio
async def test_checkpoint_zone_id_zero_returns_original_and_marks_disabled(monkeypatch) -> None:
    # Prevent DB access — zone_id<=0 short-circuits before get_pool call.
    plan = _plan()
    handler = _handler(live_reload_enabled=True)
    before = _metrics.CONFIG_HOT_RELOAD.labels(result="disabled")._value.get()
    result = await handler._checkpoint(task=_task(zone_id=0), plan=plan, now=NOW)
    after = _metrics.CONFIG_HOT_RELOAD.labels(result="disabled")._value.get()
    assert result is plan.runtime
    assert after - before == 1


@pytest.mark.asyncio
async def test_checkpoint_db_pool_failure_returns_original(monkeypatch) -> None:
    """When get_pool raises (DB misconfigured), checkpoint degrades gracefully."""

    async def _raising_get_pool():
        raise RuntimeError("DB pool not available")

    import common.db
    monkeypatch.setattr(common.db, "get_pool", _raising_get_pool)

    plan = _plan()
    handler = _handler(live_reload_enabled=True)
    result = await handler._checkpoint(task=_task(), plan=plan, now=NOW)
    assert result is plan.runtime


class _FakePool:
    def __init__(self, *, zone_row: dict | None) -> None:
        self._zone_row = zone_row

    def acquire(self):
        pool = self
        class _Ctx:
            async def __aenter__(self_inner):
                return _FakeConn(pool._zone_row)
            async def __aexit__(self_inner, *a):
                return False
        return _Ctx()


class _FakeConn:
    def __init__(self, zone_row: dict | None) -> None:
        self._zone_row = zone_row

    async def fetchrow(self, query: str, *args: Any):
        return self._zone_row


@pytest.mark.asyncio
async def test_checkpoint_locked_zone_no_swap(monkeypatch) -> None:
    pool = _FakePool(zone_row={
        "config_mode": "locked",
        "config_revision": 10,
        "live_until": None,
    })

    async def _get_pool():
        return pool

    import common.db
    monkeypatch.setattr(common.db, "get_pool", _get_pool)

    plan = _plan()
    handler = _handler(live_reload_enabled=True)
    result = await handler._checkpoint(task=_task(), plan=plan, now=NOW)
    assert result is plan.runtime, "locked zone must not hot-swap"


@pytest.mark.asyncio
async def test_checkpoint_revision_not_advanced_no_swap(monkeypatch) -> None:
    # Runtime has no bundle_revision → current=0; zone_row revision=0 → no advance.
    pool = _FakePool(zone_row={
        "config_mode": "live",
        "config_revision": 0,
        "live_until": None,
    })

    async def _get_pool():
        return pool

    import common.db
    monkeypatch.setattr(common.db, "get_pool", _get_pool)

    plan = _plan()
    handler = _handler(live_reload_enabled=True)
    result = await handler._checkpoint(task=_task(), plan=plan, now=NOW)
    assert result is plan.runtime
