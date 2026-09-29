"""E245: нет канала стока в контракте — контур не стартует. Прошивки в diff нет."""

from __future__ import annotations

import pytest

import ae4.domain.drain_policy as drain_policy
from ae4.domain.drain_policy import (
    CONTRACT_DRAIN_TANK_EC_CHANNEL,
    CONTRACT_DRAIN_TANK_LEVEL_CHANNELS,
    drain_tank_channels_in_contract,
    has_drain_circuit,
    is_drain_tank_level_channel,
)


def test_e245_no_drain_channel_in_contract_circuit_does_not_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(drain_policy, "CONTRACT_DRAIN_TANK_LEVEL_CHANNELS", frozenset())
    monkeypatch.setattr(drain_policy, "CONTRACT_DRAIN_TANK_EC_CHANNEL", "")
    assert drain_tank_channels_in_contract() is False
    assert (
        has_drain_circuit(
            level_drain_min_bound=True,
            level_drain_max_bound=True,
            ec_drain_bound=True,
            has_feed_to_drain_steps=True,
        )
        is False
    )


def test_e245_contract_channel_names() -> None:
    """Имена зеркалят NODE_CHANNELS_REFERENCE.md §2.10 (WATER_LEVEL_SWITCH / EC)."""
    assert CONTRACT_DRAIN_TANK_LEVEL_CHANNELS == frozenset(
        {"level_drain_min", "level_drain_max"}
    )
    assert CONTRACT_DRAIN_TANK_EC_CHANNEL == "ec_drain_sensor"
    assert drain_tank_channels_in_contract() is True


def test_e245_valve_drain_is_not_drain_tank_level() -> None:
    assert is_drain_tank_level_channel("valve_drain") is False
    assert is_drain_tank_level_channel("drain") is False
    assert is_drain_tank_level_channel("level_drain_min") is True
