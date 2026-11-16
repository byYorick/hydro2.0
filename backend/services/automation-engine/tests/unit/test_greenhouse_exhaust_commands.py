from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import logging
import pytest

from ae3lite.greenhouse_climate.climate_tick_commands import ClimateTickCommands, ClimateTickCommandsPorts
from ae3lite.greenhouse_climate.decision_engine import ClimateDecision


def fan_tick():
    renewal = AsyncMock(return_value=True)
    terminal = AsyncMock(return_value="DONE")
    rows = [{"channel": "fan_A", "node_uid": "nd-one", "zone_id": 1, "greenhouse_uid": "gh-1"}]
    fetch = AsyncMock(return_value=rows)
    component = ClimateTickCommands(ClimateTickCommandsPorts(
        greenhouse_climate_command_failed_total=lambda: Mock(), greenhouse_climate_command_total=lambda: Mock(),
        lease_lost_status=lambda: "LEASE_LOST", lease_renew_transient_budget=lambda: 1, success_status=lambda: "DONE",
        renew_greenhouse_lease=renewal, wait_command_terminal=terminal, logger=lambda: logging.getLogger("fan-test"), fetch=fetch))
    publish = AsyncMock(return_value="fan-command")
    kwargs = dict(greenhouse_id=1, execution={}, state={"control_mode": "auto", "decision_factors": {"exhaust_on": False}},
                  decision=ClimateDecision(0, 0, 0, "test", {"exhaust_on": True}, False, False, ()), vents={},
                  lease_owner="worker", lease_ttl_sec=30, idempotency_key="tick-1", history_logger_client=SimpleNamespace(publish=publish))
    return component, kwargs, publish, renewal, terminal, fetch


@pytest.mark.asyncio
async def test_fan_only_tick_requires_current_lease():
    component, kwargs, publish, renewal, terminal, _ = fan_tick()
    renewal.return_value = False
    result = await component.execute_vent_commands(**kwargs)
    publish.assert_not_awaited()
    terminal.assert_not_awaited()
    assert result.command_failures == ["fan_A:LEASE_LOST"]


@pytest.mark.asyncio
async def test_fan_terminal_wait_is_lease_aware_and_failure_is_returned():
    component, kwargs, publish, renewal, terminal, _ = fan_tick()
    terminal.return_value = "ERROR"
    result = await component.execute_vent_commands(**kwargs)
    publish.assert_awaited_once()
    terminal.assert_awaited_once()
    assert terminal.await_args.kwargs["lease_renew"] is not None
    assert result.command_failures == ["fan_A:ERROR"]


@pytest.mark.asyncio
async def test_unconfirmed_renewal_never_starts_fan():
    component, kwargs, publish, renewal, _, _ = fan_tick()
    renewal.side_effect = ConnectionError("DB unavailable")
    result = await component.execute_vent_commands(**kwargs)
    publish.assert_not_awaited()
    assert result.command_failures == ["fan_A:LEASE_LOST"]
