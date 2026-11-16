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


@pytest.mark.asyncio
async def test_fan_ids_are_bounded_stable_and_distinct_across_nodes():
    component, kwargs, publish, _, _, fetch = fan_tick()
    fetch.return_value.append(dict(fetch.return_value[0], node_uid="nd-two", zone_id=2))
    kwargs["idempotency_key"] = "scheduler-tick-" * 100
    await component.execute_vent_commands(**kwargs)
    first = [call.kwargs["cmd_id"] for call in publish.await_args_list]
    assert len(first) == len(set(first)) == 2
    assert all(len(value.encode()) <= 128 for value in first)
    publish.reset_mock()
    await component.execute_vent_commands(**kwargs)
    assert [call.kwargs["cmd_id"] for call in publish.await_args_list] == first


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["ERROR", "TIMEOUT", "SEND_FAILED", "WAIT_FAILED"])
async def test_failed_fan_state_is_unknown_and_retried_next_tick(outcome):
    from dataclasses import replace
    component, kwargs, publish, _, terminal, _ = fan_tick()
    if outcome == "SEND_FAILED":
        publish.side_effect = ConnectionError("publish timeout")
    elif outcome == "WAIT_FAILED":
        terminal.side_effect = ConnectionError("DB down")
    else:
        terminal.return_value = outcome
    result = await component.execute_vent_commands(**kwargs)
    assert result.command_failures == [f"fan_A:{outcome}"]
    factors = dict(kwargs["decision"].factors)
    assert factors["exhaust_on"] is None
    assert list(factors["exhaust_confirmed"].values()) == [None]
    kwargs["state"] = {"control_mode": "auto", "decision_factors": factors}
    kwargs["decision"] = replace(kwargs["decision"], factors={"exhaust_on": True})
    kwargs["idempotency_key"] = "tick-2"
    publish.side_effect = None
    terminal.side_effect = None
    terminal.return_value = "DONE"
    result = await component.execute_vent_commands(**kwargs)
    assert not result.command_failures
    assert publish.await_count == 2
    assert kwargs["decision"].factors["exhaust_on"] is True


@pytest.mark.asyncio
async def test_partial_success_retries_only_unconfirmed_actuator_and_new_binding():
    from dataclasses import replace
    component, kwargs, publish, _, terminal, fetch = fan_tick()
    fetch.return_value.append(dict(fetch.return_value[0], node_uid="nd-two"))
    terminal.side_effect = ["DONE", "ERROR"]
    await component.execute_vent_commands(**kwargs)
    assert kwargs["decision"].factors["exhaust_on"] is None
    kwargs["state"]["decision_factors"] = dict(kwargs["decision"].factors)
    kwargs["decision"] = replace(kwargs["decision"], factors={"exhaust_on": True})
    kwargs["idempotency_key"] = "tick-2"
    terminal.side_effect = None
    terminal.return_value = "DONE"
    fetch.return_value.append(dict(fetch.return_value[0], node_uid="nd-three"))
    publish.reset_mock()
    result = await component.execute_vent_commands(**kwargs)
    assert not result.command_failures
    assert [call.kwargs["node_uid"] for call in publish.await_args_list] == ["nd-two", "nd-three"]
    assert kwargs["decision"].factors["exhaust_on"] is True


@pytest.mark.asyncio
async def test_failed_off_does_not_get_reported_as_off_and_is_retried():
    from dataclasses import replace
    component, kwargs, publish, _, terminal, _ = fan_tick()
    await component.execute_vent_commands(**kwargs)
    kwargs["state"]["decision_factors"] = dict(kwargs["decision"].factors)
    kwargs["decision"] = replace(kwargs["decision"], factors={"exhaust_on": False})
    terminal.return_value = "ERROR"
    result = await component.execute_vent_commands(**kwargs)
    assert result.command_failures == ["fan_A:ERROR"]
    assert kwargs["decision"].factors["exhaust_on"] is None
    kwargs["state"]["decision_factors"] = dict(kwargs["decision"].factors)
    kwargs["decision"] = replace(kwargs["decision"], factors={"exhaust_on": False})
    terminal.return_value = "DONE"
    publish.reset_mock()
    await component.execute_vent_commands(**kwargs)
    publish.assert_awaited_once()
    assert publish.await_args.kwargs["params"]["state"] is False
    assert kwargs["decision"].factors["exhaust_on"] is False


@pytest.mark.asyncio
async def test_bindings_lookup_failure_is_not_success():
    component, kwargs, publish, _, _, fetch = fan_tick()
    fetch.side_effect = ConnectionError("bindings unavailable")
    result = await component.execute_vent_commands(**kwargs)
    assert result.command_failures == ["exhaust:BINDINGS_UNAVAILABLE"]
    publish.assert_not_awaited()
