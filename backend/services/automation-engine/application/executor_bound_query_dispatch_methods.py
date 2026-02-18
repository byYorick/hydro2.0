"""Bound query/dispatch wrappers for SchedulerTaskExecutor."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from application.dispatch_merge import merge_command_dispatch_results as policy_merge_command_dispatch_results
from application.executor_constants import (
    AE_TWOTANK_SAFETY_GUARDS_ENABLED,
    ERR_TWO_TANK_CHANNEL_NOT_FOUND,
    ERR_TWO_TANK_COMMAND_FAILED,
    _runtime_scheduler_constant,
)
from application.sensor_mode_dispatch import (
    dispatch_sensor_mode_command_for_nodes as policy_dispatch_sensor_mode_command_for_nodes,
)
from application.two_tank_command_plan_core import (
    dispatch_two_tank_command_plan_core as policy_dispatch_two_tank_command_plan_core,
)
from domain.models.decision_models import DecisionOutcome
from domain.policies.target_evaluation_policy import (
    evaluate_ph_ec_targets as policy_evaluate_ph_ec_targets,
    is_value_within_pct as policy_is_value_within_pct,
)
from infrastructure.node_query_adapter import (
    fetch_zone_nodes as adapter_fetch_zone_nodes,
    resolve_online_node_for_channel as adapter_resolve_online_node_for_channel,
)
from infrastructure.telemetry_query_adapter import (
    find_zone_event_since as adapter_find_zone_event_since,
    read_latest_metric as adapter_read_latest_metric,
    read_level_switch as adapter_read_level_switch,
)
from scheduler_internal_enqueue import parse_iso_datetime


async def bound_get_zone_nodes(self, zone_id: int, node_types: Sequence[str]) -> List[Dict[str, Any]]:
    return await adapter_fetch_zone_nodes(
        fetch_fn=self.fetch_fn,
        zone_id=zone_id,
        node_types=node_types,
    )


async def bound_read_level_switch(
    self,
    *,
    zone_id: int,
    sensor_labels: Sequence[str],
    threshold: float,
) -> Dict[str, Any]:
    return await adapter_read_level_switch(
        fetch_fn=self.fetch_fn,
        parse_iso_datetime=parse_iso_datetime,
        canonicalize_label=self._canonical_sensor_label,
        zone_id=zone_id,
        sensor_labels=sensor_labels,
        threshold=threshold,
        telemetry_max_age_sec=self._telemetry_freshness_max_age_sec(),
    )


async def bound_read_latest_metric(self, *, zone_id: int, sensor_type: str) -> Dict[str, Any]:
    return await adapter_read_latest_metric(
        fetch_fn=self.fetch_fn,
        parse_iso_datetime=parse_iso_datetime,
        zone_id=zone_id,
        sensor_type=sensor_type,
        telemetry_max_age_sec=self._telemetry_freshness_max_age_sec(),
    )


def bound_is_value_within_pct(self, *, value: float, target: float, tolerance_pct: float) -> bool:
    return policy_is_value_within_pct(
        value=value,
        target=target,
        tolerance_pct=tolerance_pct,
    )


async def bound_evaluate_ph_ec_targets(
    self,
    *,
    zone_id: int,
    target_ph: float,
    target_ec: float,
    tolerance: Dict[str, float],
) -> Dict[str, Any]:
    return await policy_evaluate_ph_ec_targets(
        read_metric=self._read_latest_metric,
        zone_id=zone_id,
        target_ph=target_ph,
        target_ec=target_ec,
        tolerance=tolerance,
        telemetry_freshness_enforce=self._telemetry_freshness_enforce(),
    )


async def bound_find_zone_event_since(
    self,
    *,
    zone_id: int,
    event_types: Sequence[str],
    since: Optional[datetime],
) -> Optional[Dict[str, Any]]:
    return await adapter_find_zone_event_since(
        fetch_fn=self.fetch_fn,
        zone_id=zone_id,
        event_types=event_types,
        since=since,
    )


async def bound_resolve_online_node_for_channel(
    self,
    *,
    zone_id: int,
    channel: str,
    node_types: Sequence[str],
) -> Optional[Dict[str, Any]]:
    return await adapter_resolve_online_node_for_channel(
        fetch_fn=self.fetch_fn,
        zone_id=zone_id,
        channel=channel,
        node_types=node_types,
    )


async def bound_dispatch_sensor_mode_command_for_nodes(
    self,
    *,
    zone_id: int,
    context: Dict[str, Any],
    decision: DecisionOutcome,
    activate: bool,
    reason_code: str,
) -> Dict[str, Any]:
    return await policy_dispatch_sensor_mode_command_for_nodes(
        zone_id=zone_id,
        context=context,
        decision=decision,
        activate=activate,
        reason_code=reason_code,
        resolve_online_node_for_channel_fn=self._resolve_online_node_for_channel,
        publish_batch_fn=self._publish_batch,
    )


def bound_merge_command_dispatch_results(*results: Dict[str, Any]) -> Dict[str, Any]:
    return policy_merge_command_dispatch_results(
        *results,
        err_two_tank_command_failed=ERR_TWO_TANK_COMMAND_FAILED,
    )


async def bound_dispatch_two_tank_command_plan(
    self,
    *,
    zone_id: int,
    command_plan: Sequence[Dict[str, Any]],
    context: Dict[str, Any],
    decision: DecisionOutcome,
) -> Dict[str, Any]:
    return await self.command_dispatch.dispatch_command_plan(
        zone_id=zone_id,
        command_plan=command_plan,
        context=context,
        decision=decision,
        task_type="diagnostics",
    )


async def bound_dispatch_two_tank_command_plan_core(
    self,
    *,
    zone_id: int,
    command_plan: Sequence[Dict[str, Any]],
    context: Dict[str, Any],
    decision: DecisionOutcome,
) -> Dict[str, Any]:
    return await policy_dispatch_two_tank_command_plan_core(
        zone_id=zone_id,
        command_plan=command_plan,
        context=context,
        decision=decision,
        resolve_online_node_for_channel_fn=self._resolve_online_node_for_channel,
        publish_batch_fn=self._publish_batch,
        err_two_tank_channel_not_found=ERR_TWO_TANK_CHANNEL_NOT_FOUND,
        err_two_tank_command_failed=ERR_TWO_TANK_COMMAND_FAILED,
    )


def bound_two_tank_safety_guards_enabled() -> bool:
    return bool(_runtime_scheduler_constant("AE_TWOTANK_SAFETY_GUARDS_ENABLED", AE_TWOTANK_SAFETY_GUARDS_ENABLED))


__all__ = [
    "bound_dispatch_sensor_mode_command_for_nodes",
    "bound_dispatch_two_tank_command_plan",
    "bound_dispatch_two_tank_command_plan_core",
    "bound_evaluate_ph_ec_targets",
    "bound_find_zone_event_since",
    "bound_get_zone_nodes",
    "bound_is_value_within_pct",
    "bound_merge_command_dispatch_results",
    "bound_read_latest_metric",
    "bound_read_level_switch",
    "bound_resolve_online_node_for_channel",
    "bound_two_tank_safety_guards_enabled",
]
