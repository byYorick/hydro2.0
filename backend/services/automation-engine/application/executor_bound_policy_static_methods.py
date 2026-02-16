"""Static policy wrappers for SchedulerTaskExecutor class assignment."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

from application.executor_constants import (
    AUTO_LOGIC_DECISION_V1,
    AUTO_LOGIC_NEW_SENSORS_V1,
    TERMINAL_STATUS_ERROR_CODES,
)
from application.workflow_phase_policy import WORKFLOW_PHASE_VALUES, WORKFLOW_STAGES_CANONICAL
from config.scheduler_task_mapping import SchedulerTaskMapping
from domain.models.decision_models import DecisionOutcome
from domain.policies.command_mapping_policy import (
    extract_duration_sec as policy_extract_duration_sec,
    resolve_command_name as policy_resolve_command_name,
    resolve_command_params as policy_resolve_command_params,
    terminal_status_to_error_code as policy_terminal_status_to_error_code,
)
from domain.policies.cycle_start_refill_policy import (
    normalize_node_type_list as policy_normalize_node_type_list,
    normalize_text_list as policy_normalize_text_list,
)
from domain.policies.decision_detail_policy import (
    to_optional_float as policy_to_optional_float,
    with_decision_details as policy_with_decision_details,
)
from domain.policies.decision_policy import (
    decide_action as policy_decide_action,
    decide_irrigation_action as policy_decide_irrigation_action,
    extract_nested_bool as policy_extract_nested_bool,
    extract_nested_metric as policy_extract_nested_metric,
    extract_next_due_at as policy_extract_next_due_at,
    extract_retry_attempt as policy_extract_retry_attempt,
    safe_bool as policy_safe_bool,
    safe_float as policy_safe_float,
    safe_int as policy_safe_int,
)
from domain.policies.normalization_policy import (
    canonical_sensor_label as policy_canonical_sensor_label,
    merge_dict_recursive as policy_merge_dict_recursive,
    normalize_labels as policy_normalize_labels,
    resolve_float as policy_resolve_float,
    resolve_int as policy_resolve_int,
)
from domain.policies.outcome_policy import (
    build_decision_retry_correlation_id as policy_build_decision_retry_correlation_id,
    extract_two_tank_chemistry_orchestration as policy_extract_two_tank_chemistry_orchestration,
)
from application.workflow_phase_policy import (
    normalize_workflow_phase as policy_normalize_workflow_phase,
    normalize_workflow_stage as policy_normalize_workflow_stage,
)
from domain.policies.workflow_input_policy import (
    extract_execution_config as policy_extract_execution_config,
    extract_payload_contract_version as policy_extract_payload_contract_version,
    extract_refill_config as policy_extract_refill_config,
    extract_topology as policy_extract_topology,
    is_supported_payload_contract_version as policy_is_supported_payload_contract_version,
)


def bound_decide_action(task_type: str, payload: Dict[str, Any]) -> DecisionOutcome:
    return policy_decide_action(
        task_type=task_type,
        payload=payload,
        auto_logic_decision_v1=AUTO_LOGIC_DECISION_V1,
        auto_logic_new_sensors_v1=AUTO_LOGIC_NEW_SENSORS_V1,
    )


def bound_safe_float(raw: Any) -> Optional[float]:
    return policy_safe_float(raw)


def bound_safe_int(raw: Any) -> Optional[int]:
    return policy_safe_int(raw)


def bound_safe_bool(raw: Any) -> Optional[bool]:
    return policy_safe_bool(raw)


def bound_extract_nested_metric(payload: Dict[str, Any], keys: Sequence[str]) -> Optional[float]:
    return policy_extract_nested_metric(payload, keys)


def bound_extract_nested_bool(payload: Dict[str, Any], keys: Sequence[str]) -> Optional[bool]:
    return policy_extract_nested_bool(payload, keys)


def bound_extract_retry_attempt(payload: Dict[str, Any]) -> int:
    return policy_extract_retry_attempt(payload)


def bound_decide_irrigation_action(payload: Dict[str, Any]) -> DecisionOutcome:
    return policy_decide_irrigation_action(
        payload=payload,
        auto_logic_new_sensors_v1=AUTO_LOGIC_NEW_SENSORS_V1,
    )


def bound_extract_next_due_at(*, decision: DecisionOutcome, result: Dict[str, Any]) -> Optional[str]:
    return policy_extract_next_due_at(decision=decision, result=result)


def bound_build_decision_retry_correlation_id(
    *,
    zone_id: int,
    task_type: str,
    parent_correlation_id: Optional[str],
    retry_attempt: Optional[int],
) -> str:
    return policy_build_decision_retry_correlation_id(
        zone_id=zone_id,
        task_type=task_type,
        parent_correlation_id=parent_correlation_id,
        retry_attempt=retry_attempt,
        unique_suffix_factory=lambda: uuid4().hex[:10],
    )


def bound_extract_two_tank_chemistry_orchestration(payload: Dict[str, Any]) -> Dict[str, Any]:
    return policy_extract_two_tank_chemistry_orchestration(payload)


def bound_normalize_workflow_stage(raw: Any) -> str:
    return policy_normalize_workflow_stage(raw, allowed_values=WORKFLOW_STAGES_CANONICAL)


def bound_normalize_workflow_phase(raw: Any) -> str:
    return policy_normalize_workflow_phase(raw, allowed_values=WORKFLOW_PHASE_VALUES)


def bound_terminal_status_to_error_code(status: str) -> str:
    return policy_terminal_status_to_error_code(
        status,
        error_codes=TERMINAL_STATUS_ERROR_CODES,
    )


def bound_extract_duration_sec(payload: Dict[str, Any], mapping: SchedulerTaskMapping) -> Optional[float]:
    return policy_extract_duration_sec(payload, mapping)


def bound_resolve_command_name(payload: Dict[str, Any], mapping: SchedulerTaskMapping) -> Optional[str]:
    return policy_resolve_command_name(payload, mapping)


def bound_resolve_command_params(payload: Dict[str, Any], mapping: SchedulerTaskMapping) -> Dict[str, Any]:
    return policy_resolve_command_params(payload, mapping)


def bound_extract_execution_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    return policy_extract_execution_config(payload)


def bound_extract_refill_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    return policy_extract_refill_config(payload)


def bound_extract_payload_contract_version(payload: Dict[str, Any]) -> str:
    return policy_extract_payload_contract_version(payload)


def bound_is_supported_payload_contract_version(contract_version: str) -> bool:
    return policy_is_supported_payload_contract_version(contract_version)


def bound_extract_topology(payload: Dict[str, Any]) -> str:
    return policy_extract_topology(payload)


def bound_to_optional_float(raw: Any) -> Optional[float]:
    return policy_to_optional_float(raw)


def bound_with_decision_details(decision: DecisionOutcome, patch: Dict[str, Any]) -> DecisionOutcome:
    return policy_with_decision_details(decision, patch)


def bound_resolve_int(raw: Any, default: int, minimum: int) -> int:
    return policy_resolve_int(raw=raw, default=default, minimum=minimum)


def bound_resolve_float(raw: Any, default: float, minimum: float, maximum: float) -> float:
    return policy_resolve_float(raw=raw, default=default, minimum=minimum, maximum=maximum)


def bound_normalize_labels(raw: Any, default: Sequence[str]) -> List[str]:
    return policy_normalize_labels(raw=raw, default=default)


def bound_canonical_sensor_label(raw: Any) -> str:
    return policy_canonical_sensor_label(raw)


def bound_merge_dict_recursive(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    return policy_merge_dict_recursive(base=base, patch=patch)


def bound_normalize_text_list(raw: Any, default: Sequence[str]) -> List[str]:
    return policy_normalize_text_list(raw=raw, default=default)


def bound_normalize_node_type_list(raw: Any, default: Sequence[str]) -> List[str]:
    return policy_normalize_node_type_list(raw=raw, default=default)


__all__ = [
    "bound_build_decision_retry_correlation_id",
    "bound_canonical_sensor_label",
    "bound_decide_action",
    "bound_decide_irrigation_action",
    "bound_extract_duration_sec",
    "bound_extract_execution_config",
    "bound_extract_nested_bool",
    "bound_extract_nested_metric",
    "bound_extract_next_due_at",
    "bound_extract_payload_contract_version",
    "bound_extract_refill_config",
    "bound_extract_retry_attempt",
    "bound_extract_topology",
    "bound_extract_two_tank_chemistry_orchestration",
    "bound_is_supported_payload_contract_version",
    "bound_merge_dict_recursive",
    "bound_normalize_labels",
    "bound_normalize_node_type_list",
    "bound_normalize_text_list",
    "bound_normalize_workflow_phase",
    "bound_normalize_workflow_stage",
    "bound_resolve_command_name",
    "bound_resolve_command_params",
    "bound_resolve_float",
    "bound_resolve_int",
    "bound_safe_bool",
    "bound_safe_float",
    "bound_safe_int",
    "bound_terminal_status_to_error_code",
    "bound_to_optional_float",
    "bound_with_decision_details",
]
