"""Bound refill/cycle-start helper methods for SchedulerTaskExecutor."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Sequence

from application.refill_command_resolver import resolve_refill_command as policy_resolve_refill_command
from application.executor_constants import (
    CLEAN_TANK_FULL_THRESHOLD,
    CYCLE_START_REQUIRED_NODE_TYPES,
    REFILL_COMMAND_DURATION_SEC,
    REFILL_TIMEOUT_SEC,
)
from domain.policies.cycle_start_refill_policy import (
    build_refill_check_payload as policy_build_refill_check_payload,
    resolve_clean_tank_threshold as policy_resolve_clean_tank_threshold,
    resolve_refill_attempt as policy_resolve_refill_attempt,
    resolve_refill_duration_ms as policy_resolve_refill_duration_ms,
    resolve_refill_started_at as policy_resolve_refill_started_at,
    resolve_refill_timeout_at as policy_resolve_refill_timeout_at,
    resolve_required_node_types as policy_resolve_required_node_types,
)
from infrastructure.node_query_adapter import (
    check_required_nodes_online as adapter_check_required_nodes_online,
    resolve_refill_node as adapter_resolve_refill_node,
)
from infrastructure.telemetry_query_adapter import read_clean_tank_level as adapter_read_clean_tank_level
from scheduler_internal_enqueue import parse_iso_datetime


def bound_resolve_required_node_types(self, payload: Dict[str, Any]) -> Sequence[str]:
    execution = self._extract_execution_config(payload)
    override = execution.get("required_node_types")
    return policy_resolve_required_node_types(
        override=override,
        default=CYCLE_START_REQUIRED_NODE_TYPES,
    )


def bound_resolve_clean_tank_threshold(self, payload: Dict[str, Any]) -> float:
    execution = self._extract_execution_config(payload)
    refill_cfg = self._extract_refill_config(payload)
    return policy_resolve_clean_tank_threshold(
        execution_config=execution,
        refill_config=refill_cfg,
        default_threshold=CLEAN_TANK_FULL_THRESHOLD,
    )


def bound_resolve_refill_duration_ms(self, payload: Dict[str, Any]) -> int:
    execution = self._extract_execution_config(payload)
    refill_cfg = self._extract_refill_config(payload)
    return policy_resolve_refill_duration_ms(
        execution_config=execution,
        refill_config=refill_cfg,
        default_duration_sec=REFILL_COMMAND_DURATION_SEC,
    )


def bound_resolve_refill_attempt(self, payload: Dict[str, Any]) -> int:
    return policy_resolve_refill_attempt(payload=payload)


def bound_resolve_refill_started_at(self, payload: Dict[str, Any], now: datetime) -> datetime:
    return policy_resolve_refill_started_at(
        payload=payload,
        now=now,
        parse_iso_datetime=parse_iso_datetime,
    )


def bound_resolve_refill_timeout_at(
    self,
    payload: Dict[str, Any],
    started_at: datetime,
) -> datetime:
    execution = self._extract_execution_config(payload)
    refill_cfg = self._extract_refill_config(payload)
    return policy_resolve_refill_timeout_at(
        payload=payload,
        started_at=started_at,
        execution_config=execution,
        refill_config=refill_cfg,
        parse_iso_datetime=parse_iso_datetime,
        default_timeout_sec=REFILL_TIMEOUT_SEC,
    )


def bound_build_refill_check_payload(
    self,
    *,
    payload: Dict[str, Any],
    refill_started_at: datetime,
    refill_timeout_at: datetime,
    next_attempt: int,
) -> Dict[str, Any]:
    return policy_build_refill_check_payload(
        payload=payload,
        refill_started_at=refill_started_at,
        refill_timeout_at=refill_timeout_at,
        next_attempt=next_attempt,
    )


async def bound_check_required_nodes_online(
    self,
    zone_id: int,
    required_types: Sequence[str],
) -> Dict[str, Any]:
    return await adapter_check_required_nodes_online(
        fetch_fn=self.fetch_fn,
        zone_id=zone_id,
        required_types=required_types,
    )


async def bound_read_clean_tank_level(
    self,
    zone_id: int,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    threshold = self._resolve_clean_tank_threshold(payload)
    return await adapter_read_clean_tank_level(
        fetch_fn=self.fetch_fn,
        parse_iso_datetime=parse_iso_datetime,
        zone_id=zone_id,
        threshold=threshold,
        telemetry_max_age_sec=self._telemetry_freshness_max_age_sec(),
    )


async def bound_resolve_refill_command(
    self,
    zone_id: int,
    payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    return await policy_resolve_refill_command(
        zone_id=zone_id,
        payload=payload,
        extract_refill_config_fn=self._extract_refill_config,
        normalize_node_type_list_fn=self._normalize_node_type_list,
        normalize_text_list_fn=self._normalize_text_list,
        resolve_refill_node_fn=lambda **kwargs: adapter_resolve_refill_node(
            fetch_fn=self.fetch_fn,
            **kwargs,
        ),
        resolve_refill_duration_ms_fn=self._resolve_refill_duration_ms,
    )


__all__ = [
    "bound_build_refill_check_payload",
    "bound_check_required_nodes_online",
    "bound_read_clean_tank_level",
    "bound_resolve_clean_tank_threshold",
    "bound_resolve_refill_attempt",
    "bound_resolve_refill_command",
    "bound_resolve_refill_duration_ms",
    "bound_resolve_refill_started_at",
    "bound_resolve_refill_timeout_at",
    "bound_resolve_required_node_types",
]
