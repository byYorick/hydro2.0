/**
 * @file storage_irrigation_fw_state.c
 * @brief Runtime state for storage_irrigation framework modules.
 */

#include "storage_irrigation_fw_internal.h"

bool g_storage_event_time_wait_logged = false;
bool g_level_switch_event_time_wait_logged = false;
bool g_level_switch_inputs_ready = false;

storage_irrigation_node_cmd_t g_cmd_queue[STORAGE_IRRIGATION_NODE_CMD_QUEUE_MAX] = {0};
size_t g_cmd_queue_head = 0;
size_t g_cmd_queue_tail = 0;
size_t g_cmd_queue_count = 0;
SemaphoreHandle_t g_cmd_queue_mutex = NULL;
QueueHandle_t g_cmd_work_queue = NULL;
TimerHandle_t g_cmd_retry_timer = NULL;

storage_irrigation_node_done_entry_t g_done_entries[STORAGE_IRRIGATION_NODE_DONE_QUEUE_MAX] = {0};
storage_irrigation_node_stage_guard_t g_stage_guards[3] = {0};
QueueHandle_t g_done_queue = NULL;
SemaphoreHandle_t g_actuator_mutex = NULL;
SemaphoreHandle_t g_level_switch_mutex = NULL;
storage_irrigation_node_actuator_runtime_t g_actuator_runtime[PUMP_DRIVER_MAX_CHANNELS] = {0};
storage_irrigation_node_level_switch_debounce_t g_level_switch_debounce[GPIO_NUM_MAX] = {0};
bool g_sensor_log_initialized[GPIO_NUM_MAX] = {0};
bool g_sensor_logged_state[GPIO_NUM_MAX] = {0};
bool g_level_switch_event_initialized[GPIO_NUM_MAX] = {0};
bool g_level_switch_event_published_state[GPIO_NUM_MAX] = {0};
size_t g_actuator_runtime_count = 0;
bool g_level_switch_event_session_connected = false;
storage_irrigation_node_fail_safe_config_t g_fail_safe_config = {
    .clean_fill_min_check_delay_ms = STORAGE_IRRIGATION_NODE_FAIL_SAFE_CLEAN_FILL_MIN_CHECK_DELAY_MS,
    .solution_fill_clean_min_check_delay_ms = STORAGE_IRRIGATION_NODE_FAIL_SAFE_SOLUTION_FILL_CLEAN_MIN_CHECK_DELAY_MS,
    .solution_fill_solution_min_check_delay_ms = STORAGE_IRRIGATION_NODE_FAIL_SAFE_SOLUTION_FILL_SOLUTION_MIN_CHECK_DELAY_MS,
    .recirculation_solution_min_guard_enabled = STORAGE_IRRIGATION_NODE_FAIL_SAFE_RECIRCULATION_STOP_ON_SOLUTION_MIN,
    .irrigation_solution_min_guard_enabled = STORAGE_IRRIGATION_NODE_FAIL_SAFE_IRRIGATION_STOP_ON_SOLUTION_MIN,
    .estop_debounce_ms = STORAGE_IRRIGATION_NODE_ESTOP_DEBOUNCE_MS,
};
storage_irrigation_node_clean_fill_guard_state_t g_clean_fill_guard = {0};
storage_irrigation_node_solution_fill_guard_state_t g_solution_fill_guard = {0};
storage_irrigation_node_binary_guard_state_t g_recirculation_guard = {0};
storage_irrigation_node_binary_guard_state_t g_irrigation_guard = {0};
storage_irrigation_node_estop_debounce_t g_estop_debounce = {0};
bool g_estop_input_ready = false;
bool g_estop_active = false;
bool g_estop_restore_valid = false;
bool g_estop_restore_states[PUMP_DRIVER_MAX_CHANNELS] = {0};


