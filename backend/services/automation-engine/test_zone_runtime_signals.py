from __future__ import annotations

import pytest

from services.resilience_contract import (
    INFRA_ZONE_BACKOFF_SKIP,
    INFRA_ZONE_DATA_UNAVAILABLE,
    INFRA_ZONE_DEGRADED_MODE,
    INFRA_ZONE_TARGETS_MISSING,
)
from services.zone_runtime_signals import emit_zone_recovered_signal


class _Logger:
    def info(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_emit_zone_recovered_signal_probes_backoff_once_on_cold_start():
    calls = []

    async def create_zone_event_safe_fn(**_kwargs):
        raise AssertionError("unexpected zone_recovered event for cold-start probe")

    async def send_infra_resolved_alert_fn(**kwargs):
        calls.append(dict(kwargs))
        return True

    zone_state = {"backoff_skip_alert_active": None}

    await emit_zone_recovered_signal(
        zone_id=6,
        previous_error_streak=0,
        zone_state=zone_state,
        create_zone_event_safe_fn=create_zone_event_safe_fn,
        send_infra_resolved_alert_fn=send_infra_resolved_alert_fn,
        logger=_Logger(),
    )

    assert len(calls) == 1
    assert calls[0]["code"] == INFRA_ZONE_BACKOFF_SKIP
    assert zone_state["backoff_skip_alert_active"] is False

    calls.clear()
    await emit_zone_recovered_signal(
        zone_id=6,
        previous_error_streak=0,
        zone_state=zone_state,
        create_zone_event_safe_fn=create_zone_event_safe_fn,
        send_infra_resolved_alert_fn=send_infra_resolved_alert_fn,
        logger=_Logger(),
    )
    assert calls == []


@pytest.mark.asyncio
async def test_emit_zone_recovered_signal_resolves_all_codes_after_real_recovery():
    calls = []
    events = []

    async def create_zone_event_safe_fn(**kwargs):
        events.append(dict(kwargs))
        return True

    async def send_infra_resolved_alert_fn(**kwargs):
        calls.append(dict(kwargs))
        return True

    zone_state = {"backoff_skip_alert_active": True}

    await emit_zone_recovered_signal(
        zone_id=6,
        previous_error_streak=4,
        zone_state=zone_state,
        create_zone_event_safe_fn=create_zone_event_safe_fn,
        send_infra_resolved_alert_fn=send_infra_resolved_alert_fn,
        logger=_Logger(),
    )

    assert len(events) == 1
    assert events[0]["event_type"] == "ZONE_RECOVERED"
    assert sorted(call["code"] for call in calls) == sorted(
        [
            INFRA_ZONE_DEGRADED_MODE,
            INFRA_ZONE_DATA_UNAVAILABLE,
            INFRA_ZONE_BACKOFF_SKIP,
            INFRA_ZONE_TARGETS_MISSING,
        ]
    )
    assert zone_state["backoff_skip_alert_active"] is False
