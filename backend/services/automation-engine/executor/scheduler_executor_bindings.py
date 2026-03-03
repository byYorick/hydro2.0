"""Binding helpers for SchedulerTaskExecutor."""

from __future__ import annotations

from typing import Any, Dict, Type


def apply_scheduler_executor_bindings(cls: Type[Any], symbols: Dict[str, Any]) -> None:
    cls._enqueue_two_tank_check = symbols["bound_enqueue_two_tank_check"]
    cls._create_zone_event_safe = symbols["bound_create_zone_event_safe"]
    cls._sync_zone_workflow_phase_core = symbols["bound_sync_zone_workflow_phase_core"]
    cls._emit_task_event = symbols["bound_emit_task_event"]
    cls._update_zone_workflow_phase = symbols["bound_update_zone_workflow_phase"]
    cls._publish_batch = symbols["bound_publish_batch"]
    cls._enqueue_decision_retry = symbols["bound_enqueue_decision_retry"]
    cls._ensure_extended_outcome = symbols["bound_ensure_extended_outcome"]
    cls._execute_diagnostics_task = symbols["bound_execute_diagnostics_task"]
    cls._dispatch_diagnostics_workflow = symbols["bound_dispatch_diagnostics_workflow"]
    cls._compensate_two_tank_start_enqueue_failure = symbols["bound_compensate_two_tank_start_enqueue_failure"]
    cls._merge_with_sensor_mode_deactivate = symbols["bound_merge_with_sensor_mode_deactivate"]
    cls._build_two_tank_deps = symbols["bound_build_two_tank_deps"]
    cls._try_start_two_tank_irrigation_recovery_from_irrigation_failure = (
        symbols["bound_try_start_two_tank_irrigation_recovery_from_irrigation_failure"]
    )
    cls._execute_two_tank_startup_workflow = symbols["bound_execute_two_tank_startup_workflow"]
    cls._execute_two_tank_startup_workflow_core = symbols["bound_execute_two_tank_startup_workflow_core"]
    cls._execute_three_tank_startup_workflow = symbols["bound_execute_three_tank_startup_workflow"]
    cls._execute_three_tank_startup_workflow_core = symbols["bound_execute_three_tank_startup_workflow_core"]
    cls._execute_cycle_start_workflow = symbols["bound_execute_cycle_start_workflow"]
    cls._execute_cycle_start_workflow_core = symbols["bound_execute_cycle_start_workflow_core"]
    cls._execute_diagnostics = symbols["bound_execute_diagnostics"]
    cls._resolve_required_node_types = symbols["bound_resolve_required_node_types"]
    cls._resolve_clean_tank_threshold = symbols["bound_resolve_clean_tank_threshold"]
    cls._resolve_refill_duration_ms = symbols["bound_resolve_refill_duration_ms"]
    cls._resolve_refill_attempt = symbols["bound_resolve_refill_attempt"]
    cls._resolve_refill_started_at = symbols["bound_resolve_refill_started_at"]
    cls._resolve_refill_timeout_at = symbols["bound_resolve_refill_timeout_at"]
    cls._build_refill_check_payload = symbols["bound_build_refill_check_payload"]
    cls._check_required_nodes_online = symbols["bound_check_required_nodes_online"]
    cls._read_clean_tank_level = symbols["bound_read_clean_tank_level"]
    cls._resolve_refill_command = symbols["bound_resolve_refill_command"]
    cls._emit_cycle_alert = symbols["bound_emit_cycle_alert"]
    cls._build_two_tank_check_payload = symbols["bound_build_two_tank_check_payload"]
    cls._log_two_tank_safety_guard = symbols["bound_log_two_tank_safety_guard"]
    cls._build_two_tank_stop_not_confirmed_result = symbols["bound_build_two_tank_stop_not_confirmed_result"]
    cls._decide_action = staticmethod(symbols["bound_decide_action"])
    cls._safe_float = staticmethod(symbols["bound_safe_float"])
    cls._safe_int = staticmethod(symbols["bound_safe_int"])
    cls._safe_bool = staticmethod(symbols["bound_safe_bool"])
    cls._extract_nested_metric = staticmethod(symbols["bound_extract_nested_metric"])
    cls._extract_nested_bool = staticmethod(symbols["bound_extract_nested_bool"])
    cls._extract_retry_attempt = staticmethod(symbols["bound_extract_retry_attempt"])
    cls._decide_irrigation_action = staticmethod(symbols["bound_decide_irrigation_action"])
    cls._extract_next_due_at = staticmethod(symbols["bound_extract_next_due_at"])
    cls._build_decision_retry_correlation_id = staticmethod(symbols["bound_build_decision_retry_correlation_id"])
    cls._extract_two_tank_chemistry_orchestration = staticmethod(
        symbols["bound_extract_two_tank_chemistry_orchestration"]
    )
    cls._normalize_workflow_stage = staticmethod(symbols["bound_normalize_workflow_stage"])
    cls._normalize_workflow_phase = staticmethod(symbols["bound_normalize_workflow_phase"])
    cls._terminal_status_to_error_code = staticmethod(symbols["bound_terminal_status_to_error_code"])
    cls._extract_duration_sec = staticmethod(symbols["bound_extract_duration_sec"])
    cls._resolve_command_name = staticmethod(symbols["bound_resolve_command_name"])
    cls._resolve_command_params = staticmethod(symbols["bound_resolve_command_params"])
    cls._extract_execution_config = staticmethod(symbols["bound_extract_execution_config"])
    cls._extract_refill_config = staticmethod(symbols["bound_extract_refill_config"])
    cls._extract_payload_contract_version = staticmethod(symbols["bound_extract_payload_contract_version"])
    cls._is_supported_payload_contract_version = staticmethod(symbols["bound_is_supported_payload_contract_version"])
    cls._extract_topology = staticmethod(symbols["bound_extract_topology"])
    cls._to_optional_float = staticmethod(symbols["bound_to_optional_float"])
    cls._with_decision_details = staticmethod(symbols["bound_with_decision_details"])
    cls._resolve_int = staticmethod(symbols["bound_resolve_int"])
    cls._resolve_float = staticmethod(symbols["bound_resolve_float"])
    cls._normalize_labels = staticmethod(symbols["bound_normalize_labels"])
    cls._canonical_sensor_label = staticmethod(symbols["bound_canonical_sensor_label"])
    cls._merge_dict_recursive = staticmethod(symbols["bound_merge_dict_recursive"])
    cls._normalize_text_list = staticmethod(symbols["bound_normalize_text_list"])
    cls._normalize_node_type_list = staticmethod(symbols["bound_normalize_node_type_list"])
    cls._extract_workflow = symbols["bound_extract_workflow"]
    cls._is_cycle_start_workflow = symbols["bound_is_cycle_start_workflow"]
    cls._normalize_two_tank_workflow = symbols["bound_normalize_two_tank_workflow"]
    cls._is_two_tank_startup_workflow = symbols["bound_is_two_tank_startup_workflow"]
    cls._is_three_tank_startup_workflow = symbols["bound_is_three_tank_startup_workflow"]
    cls._default_two_tank_command_plan = symbols["bound_default_two_tank_command_plan"]
    cls._normalize_command_plan = symbols["bound_normalize_command_plan"]
    cls._resolve_two_tank_runtime_config = symbols["bound_resolve_two_tank_runtime_config"]
    cls._build_diagnostics_invalid_payload_result = symbols["bound_build_diagnostics_invalid_payload_result"]
    cls._get_zone_nodes = symbols["bound_get_zone_nodes"]
    cls._read_level_switch = symbols["bound_read_level_switch"]
    cls._read_latest_metric = symbols["bound_read_latest_metric"]
    cls._is_value_within_pct = symbols["bound_is_value_within_pct"]
    cls._evaluate_ph_ec_targets = symbols["bound_evaluate_ph_ec_targets"]
    cls._find_zone_event_since = symbols["bound_find_zone_event_since"]
    cls._resolve_online_node_for_channel = symbols["bound_resolve_online_node_for_channel"]
    cls._dispatch_sensor_mode_command_for_nodes = symbols["bound_dispatch_sensor_mode_command_for_nodes"]
    cls._merge_command_dispatch_results = staticmethod(symbols["bound_merge_command_dispatch_results"])
    cls._dispatch_two_tank_command_plan = symbols["bound_dispatch_two_tank_command_plan"]
    cls._dispatch_two_tank_command_plan_core = symbols["bound_dispatch_two_tank_command_plan_core"]
    cls._two_tank_safety_guards_enabled = staticmethod(symbols["bound_two_tank_safety_guards_enabled"])
    cls._execute_device_task = symbols["bound_execute_device_task"]
    cls._execute_device_task_core = symbols["bound_execute_device_task_core"]
    cls._apply_ventilation_climate_guards = symbols["bound_apply_ventilation_climate_guards"]
    cls._build_two_tank_runtime_payload = symbols["bound_build_two_tank_runtime_payload"]
    cls._requires_explicit_workflow = staticmethod(symbols["bound_requires_explicit_workflow"])
    cls._tank_state_machine_enabled = staticmethod(symbols["bound_tank_state_machine_enabled"])
    cls._telemetry_freshness_enforce = staticmethod(symbols["bound_telemetry_freshness_enforce"])
    cls._telemetry_freshness_max_age_sec = staticmethod(symbols["bound_telemetry_freshness_max_age_sec"])
    cls._extract_workflow_hint = staticmethod(symbols["bound_extract_workflow_hint"])
    cls._derive_workflow_phase = staticmethod(symbols["bound_derive_workflow_phase"])
    cls._build_workflow_state_payload = staticmethod(symbols["bound_build_workflow_state_payload"])
    cls._resolve_workflow_stage_for_state_sync = staticmethod(symbols["bound_resolve_workflow_stage_for_state_sync"])
    cls._validate_phase_transition = staticmethod(symbols["bound_validate_phase_transition"])
    cls._sync_zone_workflow_phase = symbols["bound_sync_zone_workflow_phase"]


__all__ = ["apply_scheduler_executor_bindings"]
