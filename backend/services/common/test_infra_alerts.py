from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from common.infra_alerts import send_infra_alert, send_infra_resolved_alert


@pytest.mark.asyncio
async def test_send_infra_alert_includes_cycle_and_intent_in_dedupe_key(monkeypatch):
    monkeypatch.setenv("INFRA_ALERTS_ENABLED", "1")

    with patch("common.infra_alerts._publisher.raise_active", new_callable=AsyncMock) as mock_raise:
        mock_raise.return_value = True

        sent = await send_infra_alert(
            code="infra_test_code",
            message="test",
            zone_id=8,
            alert_type="Test Alert",
            severity="warning",
            service="automation-engine",
            component="correction_controller",
            node_uid="nd-test",
            channel="pump_main",
            cmd="run_pump",
            error_type="test_error",
            cycle_id=321,
            intent_id="intent-321",
            details={"scope": "test"},
        )

        assert sent is True
        kwargs = mock_raise.call_args.kwargs
        assert kwargs["details"]["cycle_id"] == 321
        assert kwargs["details"]["intent_id"] == "intent-321"
        assert "cycle:321" in kwargs["details"]["dedupe_key"]
        assert "intent:intent-321" in kwargs["details"]["dedupe_key"]


@pytest.mark.asyncio
async def test_send_infra_resolved_alert_uses_same_dedupe_key_as_active(monkeypatch):
    monkeypatch.setenv("INFRA_ALERTS_ENABLED", "1")
    calls = []

    async def _send_alert_to_laravel(**kwargs):
        calls.append(kwargs)
        return True

    with patch("common.infra_alerts._publisher.raise_active", side_effect=_send_alert_to_laravel), \
         patch("common.infra_alerts._publisher.resolve", side_effect=_send_alert_to_laravel):
        await send_infra_alert(
            code="infra_test_code",
            message="active",
            zone_id=8,
            alert_type="Test Alert",
            severity="warning",
            service="automation-engine",
            component="correction_controller",
            node_uid="nd-test",
            channel="pump_main",
            cmd="run_pump",
            error_type="test_error",
            cycle_id=11,
            intent_id="intent-11",
            details={"scope": "test"},
        )
        await send_infra_resolved_alert(
            code="infra_test_code",
            message="resolved",
            zone_id=8,
            alert_type="Test Alert",
            service="automation-engine",
            component="correction_controller",
            node_uid="nd-test",
            channel="pump_main",
            cmd="run_pump",
            error_type="test_error",
            cycle_id=11,
            intent_id="intent-11",
            details={"scope": "test"},
        )

    assert len(calls) == 2
    active_key = calls[0]["details"]["dedupe_key"]
    resolved_key = calls[1]["details"]["dedupe_key"]
    assert active_key == resolved_key
