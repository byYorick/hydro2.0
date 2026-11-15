"""Typed records shared by the component boundaries."""

from __future__ import annotations


class _GreenhouseLeaseStop(Exception):
    """Подтверждённая потеря greenhouse lease или исчерпанный транспортный бюджет."""


from datetime import datetime
from typing import Any, Mapping, NamedTuple

from ae3lite.greenhouse_climate.decision_engine import ClimateDecision


class ClimateTickPlan(NamedTuple):
    execution: Mapping[str, Any]
    snapshot: Mapping[str, Any]
    vents: Mapping[str, Mapping[str, Any]]
    active_override_id: int | None
    decision: ClimateDecision
    active_alerts: list[str]
    next_tick_at: datetime


class ClimateCommandResult(NamedTuple):
    left_cmd_id: str | None
    right_cmd_id: str | None
    left_done: bool
    right_done: bool
    command_failures: list[str]
