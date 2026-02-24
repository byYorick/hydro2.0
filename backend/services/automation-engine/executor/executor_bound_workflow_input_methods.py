"""Bound workflow-input/runtime methods for SchedulerTaskExecutor."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from executor.executor_constants import (
    AE_LEGACY_WORKFLOW_DEFAULT_ENABLED,
    REFILL_CHECK_DELAY_SEC,
    _runtime_scheduler_constant,
)
from executor.two_tank_runtime_config import (
    default_two_tank_command_plan as policy_default_two_tank_command_plan,
    normalize_command_plan as policy_normalize_command_plan,
    resolve_two_tank_runtime_config as policy_resolve_two_tank_runtime_config,
)
from domain.policies.diagnostics_policy import (
    build_diagnostics_invalid_payload_result as policy_build_diagnostics_invalid_payload_result,
)
from domain.policies.workflow_input_policy import (
    extract_workflow as policy_extract_workflow,
    is_three_tank_startup_workflow as policy_is_three_tank_startup_workflow,
    is_two_tank_startup_workflow as policy_is_two_tank_startup_workflow,
    normalize_two_tank_workflow as policy_normalize_two_tank_workflow,
)
def bound_extract_workflow(self, payload: Dict[str, Any]) -> str:
    legacy_workflow_default_enabled = bool(
        _runtime_scheduler_constant(
            "AE_LEGACY_WORKFLOW_DEFAULT_ENABLED",
            AE_LEGACY_WORKFLOW_DEFAULT_ENABLED,
        )
    )
    return policy_extract_workflow(
        payload=payload,
        legacy_workflow_default_enabled=legacy_workflow_default_enabled,
        requires_explicit_workflow=self._requires_explicit_workflow,
    )


def bound_is_cycle_start_workflow(self, payload: Dict[str, Any]) -> bool:
    workflow = self._extract_workflow(payload)
    return workflow in {"cycle_start", "refill_check"}


def bound_normalize_two_tank_workflow(self, payload: Dict[str, Any]) -> str:
    workflow = self._extract_workflow(payload)
    return policy_normalize_two_tank_workflow(workflow)


def bound_is_two_tank_startup_workflow(self, payload: Dict[str, Any]) -> bool:
    topology = self._extract_topology(payload)
    workflow = self._normalize_two_tank_workflow(payload)
    return policy_is_two_tank_startup_workflow(topology=topology, workflow=workflow)


def bound_is_three_tank_startup_workflow(self, payload: Dict[str, Any]) -> bool:
    topology = self._extract_topology(payload)
    workflow = self._extract_workflow(payload)
    return policy_is_three_tank_startup_workflow(topology=topology, workflow=workflow)


def bound_default_two_tank_command_plan(self, plan_name: str) -> List[Dict[str, Any]]:
    return policy_default_two_tank_command_plan(plan_name)


def bound_normalize_command_plan(
    self,
    raw: Any,
    *,
    default_plan: Sequence[Dict[str, Any]],
    default_node_types: Sequence[str],
    default_allow_no_effect: bool = False,
) -> List[Dict[str, Any]]:
    return policy_normalize_command_plan(
        raw,
        default_plan=default_plan,
        default_node_types=default_node_types,
        default_allow_no_effect=default_allow_no_effect,
        normalize_node_type_list_fn=self._normalize_node_type_list,
    )


def bound_resolve_two_tank_runtime_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    return policy_resolve_two_tank_runtime_config(
        payload,
        refill_check_delay_sec=REFILL_CHECK_DELAY_SEC,
        extract_execution_config_fn=self._extract_execution_config,
        normalize_node_type_list_fn=self._normalize_node_type_list,
        resolve_int_fn=self._resolve_int,
        resolve_float_fn=self._resolve_float,
        normalize_labels_fn=self._normalize_labels,
    )


def bound_build_diagnostics_invalid_payload_result(
    self,
    *,
    reason_code: str,
    reason: str,
    payload_contract_version: str,
) -> Dict[str, Any]:
    return policy_build_diagnostics_invalid_payload_result(
        reason_code=reason_code,
        reason=reason,
        payload_contract_version=payload_contract_version,
    )


__all__ = [
    "bound_build_diagnostics_invalid_payload_result",
    "bound_default_two_tank_command_plan",
    "bound_extract_workflow",
    "bound_is_cycle_start_workflow",
    "bound_is_three_tank_startup_workflow",
    "bound_is_two_tank_startup_workflow",
    "bound_normalize_command_plan",
    "bound_normalize_two_tank_workflow",
    "bound_resolve_two_tank_runtime_config",
]
