"""
Correction Controller - универсальный контроллер для корректировки pH и EC.
Устраняет дублирование кода между pH и EC корректировкой.
"""

from enum import Enum
from typing import Any, Dict, Optional

from services.pid_state_manager import PidStateManager
from utils.adaptive_pid import AdaptivePid

from correction_controller_apply import (
    apply_correction_with_events,
    publish_controller_command_with_retry_method,
    trigger_ec_partial_batch_compensation_method,
    wait_command_done_method,
)
from correction_controller_check_core import check_and_correct_core
from correction_controller_helpers import (
    build_actuator_identity_for_controller,
    build_correction_command_payload,
    build_ec_component_batch_for_controller,
    build_pid_config_for_controller,
    calculate_amount_for_diff,
    determine_correction_type_for_diff,
    extract_nutrition_control_for_controller,
    get_correction_event_type_for_controller,
    get_dt_seconds_for_zone,
    get_latest_ec_value_for_zone,
    get_pid_for_zone,
    resolve_batch_dose_control_for_controller,
    resolve_ec_component_ratios_for_controller,
    resolve_nutrition_mode_for_controller,
    resolve_solution_volume_l_for_controller,
    save_all_pid_states_for_controller,
    select_actuator_for_correction,
)
from correction_controller_runtime_state import (
    evaluate_pending_effect_window,
    export_runtime_state_payload,
    is_anomaly_guard_enabled,
    log_skip_decision,
    normalize_int_key_map,
    register_pending_effect_window,
    resolve_anomaly_block_until,
    resolve_anomaly_min_delta,
    restore_runtime_state_payload,
)


class CorrectionType(Enum):
    """Тип корректировки."""

    PH = "ph"
    EC = "ec"


class CorrectionController:
    """Универсальный контроллер для корректировки pH/EC."""

    def __init__(self, correction_type: CorrectionType, pid_state_manager: Optional[PidStateManager] = None):
        self.correction_type = correction_type
        self.metric_name = correction_type.value.upper()
        self.event_prefix = correction_type.value.upper()
        self._pid_by_zone: Dict[int, AdaptivePid] = {}
        self._last_pid_tick: Dict[int, float] = {}
        self._last_target_by_zone: Dict[int, float] = {}
        self._last_target_ts_by_zone: Dict[int, float] = {}
        self.pid_state_manager = pid_state_manager or PidStateManager()
        self._freshness_check_failure_count: Dict[int, int] = {}
        self._pending_effect_window_by_zone: Dict[int, Dict[str, Any]] = {}
        self._no_effect_streak_by_zone: Dict[int, int] = {}
        self._anomaly_blocked_until_by_zone: Dict[int, float] = {}

    _log_skip = log_skip_decision
    _is_anomaly_guard_enabled = is_anomaly_guard_enabled
    _resolve_anomaly_min_delta = resolve_anomaly_min_delta
    _resolve_anomaly_block_until = resolve_anomaly_block_until
    _register_pending_effect_window = register_pending_effect_window
    _evaluate_pending_effect_window = evaluate_pending_effect_window
    _normalize_int_key_map = staticmethod(normalize_int_key_map)
    export_runtime_state = export_runtime_state_payload
    restore_runtime_state = restore_runtime_state_payload

    check_and_correct = check_and_correct_core
    apply_correction = apply_correction_with_events
    _publish_controller_command_with_retry = publish_controller_command_with_retry_method
    _trigger_ec_partial_batch_compensation = trigger_ec_partial_batch_compensation_method
    _wait_command_done = wait_command_done_method

    _get_pid = get_pid_for_zone
    save_all_states = save_all_pid_states_for_controller
    _get_dt_seconds = get_dt_seconds_for_zone
    _build_pid_config = build_pid_config_for_controller
    _select_actuator = select_actuator_for_correction
    _build_ec_component_batch = build_ec_component_batch_for_controller
    _build_actuator_identity = build_actuator_identity_for_controller
    _resolve_ec_component_ratios = resolve_ec_component_ratios_for_controller
    _resolve_nutrition_mode = resolve_nutrition_mode_for_controller
    _resolve_solution_volume_l = resolve_solution_volume_l_for_controller
    _build_correction_command = build_correction_command_payload
    _extract_nutrition_control = extract_nutrition_control_for_controller
    _resolve_batch_dose_control = resolve_batch_dose_control_for_controller
    _get_latest_ec_value = get_latest_ec_value_for_zone
    _determine_correction_type = determine_correction_type_for_diff
    _calculate_amount = calculate_amount_for_diff
    _get_correction_event_type = get_correction_event_type_for_controller

