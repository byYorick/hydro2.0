"""Исполнение абстрактных задач расписания внутри automation-engine."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

from common.db import create_zone_event, fetch
from common.infra_alerts import send_infra_alert, send_infra_resolved_alert
from executor.dispatch_merge import merge_command_dispatch_results as policy_merge_command_dispatch_results
from executor.two_tank_command_plan_core import (
    dispatch_two_tank_command_plan_core as policy_dispatch_two_tank_command_plan_core,
)
from executor.decision_retry_enqueue import enqueue_decision_retry as policy_enqueue_decision_retry
from executor.task_events_persistence import persist_zone_event_safe as policy_persist_zone_event_safe
from executor.ventilation_climate_guards import (
    apply_ventilation_climate_guards as policy_apply_ventilation_climate_guards,
)
from executor.two_tank_runtime_config import (
    default_two_tank_command_plan as policy_default_two_tank_command_plan,
    normalize_command_plan as policy_normalize_command_plan,
    resolve_two_tank_runtime_config as policy_resolve_two_tank_runtime_config,
)
from executor.sensor_mode_dispatch import (
    dispatch_sensor_mode_command_for_nodes as policy_dispatch_sensor_mode_command_for_nodes,
)
from executor.executor_run import (
    run_scheduler_executor_execute as policy_run_scheduler_executor_execute,
)
from executor.scheduler_executor_bindings import apply_scheduler_executor_bindings
from executor.executor_init import (
    initialize_executor_components as policy_initialize_executor_components,
)
from executor.executor_constants import *  # noqa: F403
from executor.executor_constants import _env_bool as policy_env_bool
from executor.executor_method_delegates import (
    sync_zone_workflow_phase_core as policy_delegate_sync_zone_workflow_phase_core,
)
from executor.executor_small_delegates import (
    build_two_tank_runtime_payload as policy_delegate_build_two_tank_runtime_payload,
    execute_device_task_core as policy_delegate_execute_device_task_core,
    publish_batch as policy_delegate_publish_batch,
    update_zone_workflow_phase as policy_delegate_update_zone_workflow_phase,
)
from executor.executor_event_delegates import (
    emit_task_event as policy_delegate_emit_task_event,
)
from executor.executor_bound_two_tank_methods import (
    bound_build_two_tank_deps,
    bound_compensate_two_tank_start_enqueue_failure,
    bound_enqueue_two_tank_check,
    bound_merge_with_sensor_mode_deactivate,
    bound_try_start_two_tank_irrigation_recovery_from_irrigation_failure,
)
from executor.executor_bound_core_methods import (
    bound_create_zone_event_safe,
    bound_dispatch_diagnostics_workflow,
    bound_emit_task_event,
    bound_enqueue_decision_retry,
    bound_ensure_extended_outcome,
    bound_execute_diagnostics_task,
    bound_publish_batch,
    bound_sync_zone_workflow_phase_core,
    bound_update_zone_workflow_phase,
)
from executor.executor_bound_workflow_methods import (
    bound_execute_cycle_start_workflow,
    bound_execute_cycle_start_workflow_core,
    bound_execute_diagnostics,
    bound_execute_three_tank_startup_workflow,
    bound_execute_three_tank_startup_workflow_core,
    bound_execute_two_tank_startup_workflow,
    bound_execute_two_tank_startup_workflow_core,
)
from executor.executor_bound_refill_methods import (
    bound_build_refill_check_payload,
    bound_check_required_nodes_online,
    bound_read_clean_tank_level,
    bound_resolve_clean_tank_threshold,
    bound_resolve_refill_attempt,
    bound_resolve_refill_command,
    bound_resolve_refill_duration_ms,
    bound_resolve_refill_started_at,
    bound_resolve_refill_timeout_at,
    bound_resolve_required_node_types,
)
from executor.executor_bound_misc_methods import (
    bound_build_two_tank_check_payload,
    bound_build_two_tank_stop_not_confirmed_result,
    bound_emit_cycle_alert,
    bound_log_two_tank_safety_guard,
)
from executor.executor_bound_policy_static_methods import (
    bound_build_decision_retry_correlation_id,
    bound_canonical_sensor_label,
    bound_decide_action,
    bound_decide_irrigation_action,
    bound_extract_duration_sec,
    bound_extract_execution_config,
    bound_extract_nested_bool,
    bound_extract_nested_metric,
    bound_extract_next_due_at,
    bound_extract_payload_contract_version,
    bound_extract_refill_config,
    bound_extract_retry_attempt,
    bound_extract_topology,
    bound_extract_two_tank_chemistry_orchestration,
    bound_is_supported_payload_contract_version,
    bound_merge_dict_recursive,
    bound_normalize_labels,
    bound_normalize_node_type_list,
    bound_normalize_text_list,
    bound_normalize_workflow_phase,
    bound_normalize_workflow_stage,
    bound_validate_phase_transition,
    bound_resolve_command_name,
    bound_resolve_command_params,
    bound_resolve_float,
    bound_resolve_int,
    bound_safe_bool,
    bound_safe_float,
    bound_safe_int,
    bound_terminal_status_to_error_code,
    bound_to_optional_float,
    bound_with_decision_details,
)
from executor.executor_bound_workflow_input_methods import (
    bound_build_diagnostics_invalid_payload_result,
    bound_default_two_tank_command_plan,
    bound_extract_workflow,
    bound_is_cycle_start_workflow,
    bound_is_three_tank_startup_workflow,
    bound_is_two_tank_startup_workflow,
    bound_normalize_command_plan,
    bound_normalize_two_tank_workflow,
    bound_resolve_two_tank_runtime_config,
)
from executor.executor_bound_query_dispatch_methods import (
    bound_dispatch_sensor_mode_command_for_nodes,
    bound_dispatch_two_tank_command_plan,
    bound_dispatch_two_tank_command_plan_core,
    bound_evaluate_ph_ec_targets,
    bound_find_zone_event_since,
    bound_get_zone_nodes,
    bound_is_value_within_pct,
    bound_merge_command_dispatch_results,
    bound_read_latest_metric,
    bound_read_level_switch,
    bound_resolve_online_node_for_channel,
    bound_two_tank_safety_guards_enabled,
)
from executor.executor_bound_runtime_methods import (
    bound_apply_ventilation_climate_guards,
    bound_build_two_tank_runtime_payload,
    bound_execute_device_task,
    bound_execute_device_task_core,
)
from executor.executor_bound_phase_methods import (
    bound_build_workflow_state_payload,
    bound_derive_workflow_phase,
    bound_extract_workflow_hint,
    bound_requires_explicit_workflow,
    bound_resolve_workflow_stage_for_state_sync,
    bound_sync_zone_workflow_phase,
    bound_tank_state_machine_enabled,
    bound_telemetry_freshness_enforce,
    bound_telemetry_freshness_max_age_sec,
)
from executor.workflow_phase_policy import (
    WORKFLOW_PHASE_EVENT_TYPE,
    WORKFLOW_PHASE_IDLE,
    WORKFLOW_PHASE_IRRIGATING,
    WORKFLOW_PHASE_IRRIG_RECIRC,
    WORKFLOW_PHASE_READY,
    WORKFLOW_PHASE_TANK_FILLING,
    WORKFLOW_PHASE_TANK_RECIRC,
    WORKFLOW_PHASE_VALUES,
    WORKFLOW_STAGES_CANONICAL,
    WORKFLOW_STAGE_TO_PHASE,
    build_workflow_state_payload as policy_build_workflow_state_payload,
    derive_workflow_phase as policy_derive_workflow_phase,
    extract_workflow_hint as policy_extract_workflow_hint,
    normalize_workflow_phase as policy_normalize_workflow_phase,
    normalize_workflow_stage as policy_normalize_workflow_stage,
    resolve_workflow_stage_for_state_sync as policy_resolve_workflow_stage_for_state_sync,
)
from config.scheduler_task_mapping import SchedulerTaskMapping, get_task_mapping
from domain.models.decision_models import DecisionOutcome
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
from domain.policies.decision_detail_policy import (
    to_optional_float as policy_to_optional_float,
    with_decision_details as policy_with_decision_details,
)
from domain.policies.diagnostics_policy import (
    build_diagnostics_invalid_payload_result as policy_build_diagnostics_invalid_payload_result,
)
from domain.policies.normalization_policy import (
    canonical_sensor_label as policy_canonical_sensor_label,
    merge_dict_recursive as policy_merge_dict_recursive,
    normalize_labels as policy_normalize_labels,
    resolve_float as policy_resolve_float,
    resolve_int as policy_resolve_int,
)
from domain.policies.cycle_start_refill_policy import (
    normalize_node_type_list as policy_normalize_node_type_list,
    normalize_text_list as policy_normalize_text_list,
)
from domain.policies.command_mapping_policy import (
    extract_duration_sec as policy_extract_duration_sec,
    resolve_command_name as policy_resolve_command_name,
    resolve_command_params as policy_resolve_command_params,
    terminal_status_to_error_code as policy_terminal_status_to_error_code,
)
from domain.policies.outcome_policy import (
    build_decision_retry_correlation_id as policy_build_decision_retry_correlation_id,
    extract_two_tank_chemistry_orchestration as policy_extract_two_tank_chemistry_orchestration,
)
from domain.policies.outcome_enrichment_policy import (
    ensure_extended_outcome as policy_ensure_extended_outcome,
)
from domain.policies.target_evaluation_policy import (
    evaluate_ph_ec_targets as policy_evaluate_ph_ec_targets,
    is_value_within_pct as policy_is_value_within_pct,
)
from domain.policies.workflow_input_policy import (
    extract_execution_config as policy_extract_execution_config,
    extract_payload_contract_version as policy_extract_payload_contract_version,
    extract_refill_config as policy_extract_refill_config,
    extract_topology as policy_extract_topology,
    extract_workflow as policy_extract_workflow,
    is_supported_payload_contract_version as policy_is_supported_payload_contract_version,
    is_three_tank_startup_workflow as policy_is_three_tank_startup_workflow,
    is_two_tank_startup_workflow as policy_is_two_tank_startup_workflow,
    normalize_two_tank_workflow as policy_normalize_two_tank_workflow,
)
from infrastructure.command_bus import CommandBus
from infrastructure.node_query_adapter import (
    fetch_zone_nodes as adapter_fetch_zone_nodes,
    resolve_online_node_for_channel as adapter_resolve_online_node_for_channel,
)
from infrastructure.observability import log_structured
from infrastructure.telemetry_query_adapter import (
    find_zone_event_since as adapter_find_zone_event_since,
    read_latest_metric as adapter_read_latest_metric,
    read_level_switch as adapter_read_level_switch,
)
from infrastructure.workflow_state_store import WorkflowStateStore
from scheduler_internal_enqueue import enqueue_internal_scheduler_task, parse_iso_datetime

logger = logging.getLogger(__name__)


class SchedulerTaskExecutor:
    """Исполняет абстрактные задачи от scheduler через CommandBus."""

    def __init__(
        self,
        command_bus: CommandBus,
        zone_service: Optional[Any] = None,
        workflow_state_store: Optional[WorkflowStateStore] = None,
    ):
        policy_initialize_executor_components(
            executor=self,
            command_bus=command_bus,
            zone_service=zone_service,
            workflow_state_store=workflow_state_store,
            workflow_state_persist_enabled=policy_env_bool("AE_WORKFLOW_STATE_PERSIST_ENABLED", True),
            two_tank_topologies=TWO_TANK_TOPOLOGIES,
            three_tank_topologies=THREE_TANK_TOPOLOGIES,
            cycle_start_workflows=CYCLE_START_WORKFLOWS,
        )
        self.fetch_fn = fetch
        self.create_zone_event_fn = create_zone_event
        self.send_infra_alert_fn = send_infra_alert
        self.send_infra_resolved_alert_fn = send_infra_resolved_alert
        self.enqueue_internal_scheduler_task_fn = enqueue_internal_scheduler_task

    async def execute(
        self,
        *,
        zone_id: int,
        task_type: str,
        payload: Dict[str, Any],
        task_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return await policy_run_scheduler_executor_execute(
            executor=self,
            zone_id=zone_id,
            task_type=task_type,
            payload=payload,
            task_context=task_context,
            get_task_mapping_fn=get_task_mapping,
            send_infra_alert_fn=send_infra_alert,
            log_structured_fn=log_structured,
            logger_obj=logger,
            auto_logic_climate_guards_v1=AUTO_LOGIC_CLIMATE_GUARDS_V1,
            auto_logic_extended_outcome_v1=AUTO_LOGIC_EXTENDED_OUTCOME_V1,
            workflow_phase_irrigating=WORKFLOW_PHASE_IRRIGATING,
        )


apply_scheduler_executor_bindings(SchedulerTaskExecutor, globals())
