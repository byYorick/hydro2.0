/**
 * @file storage_irrigation_fw_internal.h
 * @brief Shared types, constants and runtime state for storage_irrigation framework modules.
 */

#ifndef STORAGE_IRRIGATION_FW_INTERNAL_H
#define STORAGE_IRRIGATION_FW_INTERNAL_H

#include "storage_irrigation_node_config.h"
#include "pump_driver.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/timers.h"
#include "cJSON.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define STORAGE_IRRIGATION_FW_TAG "storage_irrigation_fw"
#define STORAGE_IRRIGATION_NODE_PUMP_MAIN_DRY_RUN_MAX_MS 3000U
#define STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_DEBOUNCE_US \
    ((int64_t)STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_DEBOUNCE_MS * 1000LL)

typedef struct {
    const storage_irrigation_node_actuator_channel_t *cfg;
    bool state;
} storage_irrigation_node_actuator_runtime_t;

typedef struct {
    char channel_name[PUMP_DRIVER_MAX_CHANNEL_NAME_LEN];
    char cmd_id[STORAGE_IRRIGATION_NODE_CMD_ID_LEN];
    uint32_t duration_ms;
} storage_irrigation_node_cmd_t;

typedef struct {
    char channel_name[PUMP_DRIVER_MAX_CHANNEL_NAME_LEN];
    char cmd_id[STORAGE_IRRIGATION_NODE_CMD_ID_LEN];
    float current_ma;
    bool current_valid;
    bool auto_off;
    uint32_t duration_ms;
    TimerHandle_t timer;
} storage_irrigation_node_done_entry_t;

typedef struct {
    char channel_name[PUMP_DRIVER_MAX_CHANNEL_NAME_LEN];
    char cmd_id[STORAGE_IRRIGATION_NODE_CMD_ID_LEN];
    float current_ma;
    bool current_valid;
    bool auto_off;
    uint32_t duration_ms;
} storage_irrigation_node_done_event_t;

typedef struct {
    char stage[32];
    char cmd_id[STORAGE_IRRIGATION_NODE_CMD_ID_LEN];
    uint32_t timeout_ms;
    TimerHandle_t timer;
    bool active;
    bool timeout_pending;
} storage_irrigation_node_stage_guard_t;

typedef struct {
    bool initialized;
    bool stable_state;
    bool candidate_state;
    int64_t candidate_since_us;
} storage_irrigation_node_level_switch_debounce_t;

typedef struct {
    uint32_t clean_fill_min_check_delay_ms;
    uint32_t solution_fill_clean_min_check_delay_ms;
    uint32_t solution_fill_solution_min_check_delay_ms;
    bool recirculation_solution_min_guard_enabled;
    bool irrigation_solution_min_guard_enabled;
    uint32_t estop_debounce_ms;
} storage_irrigation_node_fail_safe_config_t;

typedef struct {
    bool ok;
    int raw;
    bool active;
} storage_irrigation_node_level_reading_t;

typedef struct {
    storage_irrigation_node_level_reading_t clean_min;
    storage_irrigation_node_level_reading_t clean_max;
    storage_irrigation_node_level_reading_t solution_min;
    storage_irrigation_node_level_reading_t solution_max;
} storage_irrigation_node_level_debug_snapshot_t;

typedef struct {
    bool active;
    bool paused_by_estop;
    bool min_check_completed;
    bool terminal_event_emitted;
    uint32_t elapsed_before_pause_ms;
    int64_t started_at_us;
} storage_irrigation_node_clean_fill_guard_state_t;

typedef struct {
    bool active;
    bool paused_by_estop;
    bool clean_min_check_completed;
    bool solution_min_check_completed;
    bool terminal_event_emitted;
    uint32_t elapsed_before_pause_ms;
    int64_t started_at_us;
} storage_irrigation_node_solution_fill_guard_state_t;

typedef struct {
    bool active;
    bool paused_by_estop;
    bool low_event_emitted;
} storage_irrigation_node_binary_guard_state_t;

typedef struct {
    bool initialized;
    bool pressed;
    bool candidate_pressed;
    int64_t candidate_since_us;
} storage_irrigation_node_estop_debounce_t;

extern bool g_storage_event_time_wait_logged;
extern bool g_level_switch_event_time_wait_logged;
extern storage_irrigation_node_cmd_t g_cmd_queue[STORAGE_IRRIGATION_NODE_CMD_QUEUE_MAX];
extern size_t g_cmd_queue_head;
extern size_t g_cmd_queue_tail;
extern size_t g_cmd_queue_count;
extern SemaphoreHandle_t g_cmd_queue_mutex;
extern QueueHandle_t g_cmd_work_queue;
extern TimerHandle_t g_cmd_retry_timer;
extern storage_irrigation_node_done_entry_t g_done_entries[STORAGE_IRRIGATION_NODE_DONE_QUEUE_MAX];
extern storage_irrigation_node_stage_guard_t g_stage_guards[3];
extern QueueHandle_t g_done_queue;
extern SemaphoreHandle_t g_actuator_mutex;
extern SemaphoreHandle_t g_level_switch_mutex;
extern storage_irrigation_node_actuator_runtime_t g_actuator_runtime[PUMP_DRIVER_MAX_CHANNELS];
extern storage_irrigation_node_level_switch_debounce_t g_level_switch_debounce[GPIO_NUM_MAX];
extern bool g_sensor_log_initialized[GPIO_NUM_MAX];
extern bool g_sensor_logged_state[GPIO_NUM_MAX];
extern bool g_level_switch_event_initialized[GPIO_NUM_MAX];
extern bool g_level_switch_event_published_state[GPIO_NUM_MAX];
extern size_t g_actuator_runtime_count;
extern bool g_level_switch_event_session_connected;
extern storage_irrigation_node_fail_safe_config_t g_fail_safe_config;
extern storage_irrigation_node_clean_fill_guard_state_t g_clean_fill_guard;
extern storage_irrigation_node_solution_fill_guard_state_t g_solution_fill_guard;
extern storage_irrigation_node_binary_guard_state_t g_recirculation_guard;
extern storage_irrigation_node_binary_guard_state_t g_irrigation_guard;
extern storage_irrigation_node_estop_debounce_t g_estop_debounce;
extern bool g_estop_input_ready;
extern bool g_estop_active;
extern bool g_estop_restore_valid;
extern bool g_estop_restore_states[PUMP_DRIVER_MAX_CHANNELS];
extern bool g_level_switch_inputs_ready;

/* Cross-module API */
const storage_irrigation_node_sensor_channel_t *storage_irrigation_node_find_sensor_cfg(const char *channel);
esp_err_t storage_irrigation_node_init_actuator_outputs(void);
int storage_irrigation_node_find_actuator_index(const char *channel);
bool storage_irrigation_node_parse_relay_state(const cJSON *item, bool *state_out);
bool storage_irrigation_node_parse_timeout_ms(const cJSON *item, uint32_t *timeout_ms_out);
bool storage_irrigation_node_parse_duration_ms(const cJSON *item, uint32_t *duration_ms_out);
bool storage_irrigation_node_parse_stage_name(const cJSON *item, char *stage_out, size_t stage_out_size);
bool storage_irrigation_node_refresh_actuator_state_locked(size_t index);
esp_err_t storage_irrigation_node_set_actuator_state_locked(size_t index, bool state);
bool storage_irrigation_node_get_actuator_state_locked(const char *channel, bool *state_out);
bool storage_irrigation_node_is_pump_main_dry_run_allowed(const char *channel, bool target_state, bool has_duration, uint32_t duration_ms);
bool storage_irrigation_node_is_clean_fill_active_locked(void);
bool storage_irrigation_node_is_solution_fill_active_locked(void);
bool storage_irrigation_node_is_prepare_recirculation_active_locked(void);
bool storage_irrigation_node_is_irrigation_active_locked(void);
uint32_t storage_irrigation_node_clean_fill_elapsed_ms(void);
uint32_t storage_irrigation_node_solution_fill_elapsed_ms(void);
bool storage_irrigation_node_is_main_pump_interlock_satisfied_locked(void);
void storage_irrigation_node_append_main_pump_interlock_error(cJSON *details);
bool storage_irrigation_node_read_switch_state_by_name(const char *sensor_name, bool *state_out);
void storage_irrigation_node_update_oled_runtime(void);
cJSON *storage_irrigation_node_build_irr_state_snapshot(void);
cJSON *storage_irrigation_node_build_legacy_state_payload(void);
const char *storage_irrigation_node_canonical_actuator_channel(const char *name);
bool storage_irrigation_node_is_main_pump_channel(const char *channel);

storage_irrigation_node_stage_guard_t *storage_irrigation_node_get_stage_guard(const char *stage, bool create);
esp_err_t storage_irrigation_node_arm_stage_guard_locked(const char *stage, const char *cmd_id, uint32_t timeout_ms);
bool storage_irrigation_node_complete_stage_guard_for_channel_locked(const char *channel, char *cmd_id_out, size_t cmd_id_out_size);
bool storage_irrigation_node_complete_stage_guard_for_stage_locked(const char *stage, char *cmd_id_out, size_t cmd_id_out_size);
bool storage_irrigation_node_stop_stage_path_locked(const char *stage);
bool storage_irrigation_node_stop_clean_fill_path_locked(void);
bool storage_irrigation_node_stop_irrigation_path_locked(void);
bool storage_irrigation_node_stop_all_paths_locked(void);
void storage_irrigation_node_pause_stage_guards_locked(void);
void storage_irrigation_node_resume_stage_guards_locked(void);
void storage_irrigation_node_process_stage_timeouts(void);
void storage_irrigation_node_stage_guard_timer_cb(TimerHandle_t timer);

void storage_irrigation_node_reload_fail_safe_config_from_storage(void);
esp_err_t storage_irrigation_node_init_estop_input(void);
bool storage_irrigation_node_read_estop_pressed(void);
bool storage_irrigation_node_is_estop_active(void);
void storage_irrigation_node_handle_estop_transition(bool pressed);
storage_irrigation_node_level_debug_snapshot_t storage_irrigation_node_read_level_debug_snapshot(void);
void storage_irrigation_node_process_fail_safe_guards(void);

void storage_irrigation_node_reset_level_switch_event_session(void);
esp_err_t storage_irrigation_node_publish_level_switch_event(
    const storage_irrigation_node_sensor_channel_t *sensor,
    bool state,
    bool initial
);
void storage_irrigation_node_publish_level_switch_events_if_needed(void);
esp_err_t storage_irrigation_node_init_level_switch_inputs(void);
float storage_irrigation_node_read_level_switch(const storage_irrigation_node_sensor_channel_t *sensor, int *raw_out);
esp_err_t storage_irrigation_node_publish_level_switch_telemetry_snapshot(void);

esp_err_t storage_irrigation_node_publish_storage_event(const char *event_code, const char *cmd_id);
esp_err_t storage_irrigation_node_publish_storage_event_with_details(const char *event_code, const char *cmd_id, cJSON *details);
esp_err_t storage_irrigation_node_publish_terminal_response(
    const char *channel,
    const char *cmd_id,
    const char *status,
    const char *error_code,
    const char *message,
    cJSON *details
);

bool storage_irrigation_node_any_pump_running(void);
bool storage_irrigation_node_cmd_queue_push(const storage_irrigation_node_cmd_t *cmd);
void storage_irrigation_node_signal_cmd_process(void);
void storage_irrigation_node_schedule_done(
    const char *channel,
    const char *cmd_id,
    uint32_t duration_ms,
    float current_ma,
    bool current_valid,
    bool auto_off
);
bool storage_irrigation_node_valve_clean_fill_transient_timer_armed(void);
void storage_irrigation_node_process_cmd_queue(void);

esp_err_t storage_irrigation_node_init_channel_callback(const char *channel_name, const cJSON *channel_config, void *user_ctx);
void storage_irrigation_node_log_fail_safe_config(void);
void storage_irrigation_node_cmd_queue_task(void *pvParameters);
void storage_irrigation_node_done_task(void *pvParameters);
void storage_irrigation_node_retry_timer_cb(TimerHandle_t timer);
void storage_irrigation_node_done_timer_cb(TimerHandle_t timer);

esp_err_t handle_set_relay(const char *channel, const cJSON *params, cJSON **response, void *user_ctx);
esp_err_t handle_storage_state(const char *channel, const cJSON *params, cJSON **response, void *user_ctx);
esp_err_t handle_test_sensor(const char *channel, const cJSON *params, cJSON **response, void *user_ctx);
esp_err_t handle_probe_sensor(const char *channel, const cJSON *params, cJSON **response, void *user_ctx);

cJSON *storage_irrigation_node_channels_callback(void *user_ctx);
void storage_irrigation_node_config_handler_wrapper(const char *topic, const char *data, int data_len, void *user_ctx);
void storage_irrigation_node_command_handler_wrapper(
    const char *topic,
    const char *channel,
    const char *data,
    int data_len,
    void *user_ctx
);

#ifdef __cplusplus
}
#endif

#endif /* STORAGE_IRRIGATION_FW_INTERNAL_H */
