from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from domain.workflows.two_tank_irr_state_helpers import (
    request_irr_state_snapshot_best_effort,
    validate_irr_state_expected_vs_actual,
)


class _GatewayStub:
    def __init__(self, *, published: bool, effective_cmd_id: str | None) -> None:
        self.published = published
        self.effective_cmd_id = effective_cmd_id
        self.calls: list[dict] = []

    async def publish_controller_command(self, *, zone_id: int, command: dict) -> bool:
        self.calls.append({"zone_id": zone_id, "command": dict(command)})
        if self.effective_cmd_id is not None:
            command["cmd_id"] = self.effective_cmd_id
        else:
            command.pop("cmd_id", None)
        return self.published


class _ExecutorStub:
    def __init__(self, *, gateway: _GatewayStub) -> None:
        self.command_gateway = gateway

    async def _get_zone_nodes(self, zone_id: int, node_types: tuple[str, ...]) -> list[dict]:
        assert zone_id == 77
        assert node_types == ("irrig",)
        return [{"node_uid": "irr-node-1"}]


@pytest.mark.asyncio
async def test_request_irr_state_snapshot_returns_effective_cmd_id_from_gateway() -> None:
    gateway = _GatewayStub(published=True, effective_cmd_id="existing-cmd-123")
    executor = _ExecutorStub(gateway=gateway)

    cmd_id = await request_irr_state_snapshot_best_effort(
        executor,
        zone_id=77,
        workflow="solution_fill_check",
    )

    assert cmd_id == "existing-cmd-123"
    assert len(gateway.calls) == 1
    call = gateway.calls[0]
    assert call["zone_id"] == 77
    assert call["command"]["node_uid"] == "irr-node-1"
    assert call["command"]["channel"] == "storage_state"
    assert call["command"]["cmd"] == "state"
    assert call["command"]["params"] == {"dedupe_ttl_sec": 10}


@pytest.mark.asyncio
async def test_request_irr_state_snapshot_returns_none_when_gateway_did_not_set_cmd_id() -> None:
    gateway = _GatewayStub(published=True, effective_cmd_id=None)
    executor = _ExecutorStub(gateway=gateway)

    cmd_id = await request_irr_state_snapshot_best_effort(
        executor,
        zone_id=77,
        workflow="startup",
    )

    assert cmd_id is None


class _ValidationExecutorStub:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def _resolve_int(self, value: object, default: int, min_value: int) -> int:
        candidate = default if value is None else int(value)
        return max(min_value, candidate)

    async def fetch_fn(self, query: str, *args: object) -> list[dict]:
        _ = (query, args)
        return list(self._rows)


@pytest.mark.asyncio
async def test_validate_startup_allows_solution_fill_alternative_state() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    executor = _ValidationExecutorStub(
        rows=[
            {
                "payload_json": {
                    "cmd_id": "state-1",
                    "snapshot": {
                        "pump_main": True,
                        "valve_clean_supply": True,
                        "valve_solution_fill": True,
                        "valve_solution_supply": False,
                    },
                },
                "created_at": now,
            }
        ]
    )

    result = await validate_irr_state_expected_vs_actual(
        executor,
        zone_id=77,
        workflow="startup",
        runtime_cfg={"irr_state_wait_timeout_sec": 0, "irr_state_max_age_sec": 30},
        critical_expectations={"startup": {"pump_main": False}},
        requested_state_cmd_id=None,
    )

    assert result is None


@pytest.mark.asyncio
async def test_validate_startup_keeps_mismatch_for_non_allowed_state() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    executor = _ValidationExecutorStub(
        rows=[
            {
                "payload_json": {
                    "cmd_id": "state-2",
                    "snapshot": {
                        "pump_main": True,
                        "valve_clean_supply": False,
                        "valve_solution_fill": False,
                    },
                },
                "created_at": now - timedelta(seconds=1),
            }
        ]
    )

    result = await validate_irr_state_expected_vs_actual(
        executor,
        zone_id=77,
        workflow="startup",
        runtime_cfg={"irr_state_wait_timeout_sec": 0, "irr_state_max_age_sec": 30},
        critical_expectations={"startup": {"pump_main": False}},
        requested_state_cmd_id=None,
    )

    assert isinstance(result, dict)
    assert result.get("error_code") == "two_tank_irr_state_mismatch"
