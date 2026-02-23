from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.resilience_contract import (
    INFRA_CORRECTION_FLAGS_MISSING,
    INFRA_CORRECTION_FLAGS_STALE,
    REASON_CORRECTION_GATING_PASSED,
    REASON_CORRECTION_MISSING_FLAGS,
    REASON_CORRECTION_STALE_FLAGS,
)
from services.zone_correction_signals import resolve_correction_gating_signals


class _Logger:
    def info(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_resolve_correction_gating_signals_resolves_both_on_gating_passed():
    calls = []

    async def fake_send_infra_resolved_alert_fn(**kwargs):
        calls.append(kwargs)
        return True

    zone_state = {
        "correction_missing_flags_active": True,
        "correction_stale_flags_active": True,
        "last_missing_correction_flags_report_at": datetime.now(timezone.utc),
        "last_stale_correction_flags_report_at": datetime.now(timezone.utc),
    }

    await resolve_correction_gating_signals(
        zone_id=12,
        reason_code=REASON_CORRECTION_GATING_PASSED,
        zone_state=zone_state,
        send_infra_resolved_alert_fn=fake_send_infra_resolved_alert_fn,
        logger=_Logger(),
    )

    assert sorted(call["code"] for call in calls) == [
        INFRA_CORRECTION_FLAGS_MISSING,
        INFRA_CORRECTION_FLAGS_STALE,
    ]
    assert zone_state["correction_missing_flags_active"] is False
    assert zone_state["correction_stale_flags_active"] is False
    assert zone_state["last_missing_correction_flags_report_at"] is None
    assert zone_state["last_stale_correction_flags_report_at"] is None


@pytest.mark.asyncio
async def test_resolve_correction_gating_signals_probes_once_after_cold_start():
    calls = []

    async def fake_send_infra_resolved_alert_fn(**kwargs):
        calls.append(kwargs)
        return True

    zone_state = {
        "correction_missing_flags_active": None,
        "correction_stale_flags_active": None,
        "last_missing_correction_flags_report_at": None,
        "last_stale_correction_flags_report_at": None,
    }

    await resolve_correction_gating_signals(
        zone_id=12,
        reason_code=REASON_CORRECTION_GATING_PASSED,
        zone_state=zone_state,
        send_infra_resolved_alert_fn=fake_send_infra_resolved_alert_fn,
        logger=_Logger(),
    )
    assert sorted(call["code"] for call in calls) == [
        INFRA_CORRECTION_FLAGS_MISSING,
        INFRA_CORRECTION_FLAGS_STALE,
    ]

    calls.clear()
    await resolve_correction_gating_signals(
        zone_id=12,
        reason_code=REASON_CORRECTION_GATING_PASSED,
        zone_state=zone_state,
        send_infra_resolved_alert_fn=fake_send_infra_resolved_alert_fn,
        logger=_Logger(),
    )
    assert calls == []


@pytest.mark.asyncio
async def test_resolve_correction_gating_signals_keeps_stale_active_when_stale_reason():
    calls = []

    async def fake_send_infra_resolved_alert_fn(**kwargs):
        calls.append(kwargs)
        return True

    zone_state = {
        "correction_missing_flags_active": True,
        "correction_stale_flags_active": True,
        "last_missing_correction_flags_report_at": datetime.now(timezone.utc),
        "last_stale_correction_flags_report_at": datetime.now(timezone.utc),
    }

    await resolve_correction_gating_signals(
        zone_id=12,
        reason_code=REASON_CORRECTION_STALE_FLAGS,
        zone_state=zone_state,
        send_infra_resolved_alert_fn=fake_send_infra_resolved_alert_fn,
        logger=_Logger(),
    )

    assert [call["code"] for call in calls] == [INFRA_CORRECTION_FLAGS_MISSING]
    assert zone_state["correction_missing_flags_active"] is False
    assert zone_state["correction_stale_flags_active"] is True
    assert zone_state["last_missing_correction_flags_report_at"] is None
    assert zone_state["last_stale_correction_flags_report_at"] is not None


@pytest.mark.asyncio
async def test_resolve_correction_gating_signals_keeps_missing_active_when_missing_reason():
    calls = []

    async def fake_send_infra_resolved_alert_fn(**kwargs):
        calls.append(kwargs)
        return True

    zone_state = {
        "correction_missing_flags_active": True,
        "correction_stale_flags_active": True,
        "last_missing_correction_flags_report_at": datetime.now(timezone.utc),
        "last_stale_correction_flags_report_at": datetime.now(timezone.utc),
    }

    await resolve_correction_gating_signals(
        zone_id=12,
        reason_code=REASON_CORRECTION_MISSING_FLAGS,
        zone_state=zone_state,
        send_infra_resolved_alert_fn=fake_send_infra_resolved_alert_fn,
        logger=_Logger(),
    )

    assert [call["code"] for call in calls] == [INFRA_CORRECTION_FLAGS_STALE]
    assert zone_state["correction_missing_flags_active"] is True
    assert zone_state["correction_stale_flags_active"] is False
    assert zone_state["last_missing_correction_flags_report_at"] is not None
    assert zone_state["last_stale_correction_flags_report_at"] is None
