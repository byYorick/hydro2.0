/**
 * @file test_node_app.c
 * @brief ESP32 тест-нода, эмулирующая 5 виртуальных узлов Hydro 2.0
 */

#include "test_node_app.h"
#include "mqtt_manager.h"
#include "config_storage.h"
#include "wifi_manager.h"
#include "setup_portal.h"
#include "test_node_ui.h"
#include "node_utils.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "cJSON.h"
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>
#include <math.h>
#include <time.h>

static const char *TAG = "test_node_multi";
static const char *CMD_TAG = "test_node_cmd";

#define DEFAULT_MQTT_NODE_UID "nd-test-irrig-1"
#define DEFAULT_GH_UID "gh-test-1"
#define DEFAULT_ZONE_UID "zn-test-1"
#define PRECONFIG_GH_UID "gh-temp"
#define PRECONFIG_ZONE_UID "zn-temp"

#define TELEMETRY_INTERVAL_MS 2000
#define CONFIG_REPORT_INTERVAL_MS 30000
#define COMMAND_QUEUE_LENGTH 32
#define STATE_COMMAND_QUEUE_LENGTH 12
#define COMMAND_WILDCARD_TOPIC "hydro/+/+/+/+/command"
#define CONFIG_WILDCARD_TOPIC "hydro/+/+/+/config"
#define TASK_STACK_TELEMETRY 6144
#define TASK_STACK_TELEMETRY_FALLBACK 5632
#define TASK_STACK_COMMAND_WORKER 6144
#define TASK_STACK_COMMAND_WORKER_FALLBACK 5632
#define TASK_STACK_STATE_COMMAND_WORKER 4096
#define TASK_STACK_STATE_COMMAND_WORKER_FALLBACK 3584
#define CLEAN_FILL_MIN_DELAY_SEC 10
#define CLEAN_FILL_DELAY_SEC 30
#define SOLUTION_FILL_MIN_DELAY_SEC 10
#define SOLUTION_FILL_DELAY_SEC 20
#define STATE_QUERY_BARRIER_QUIET_MS 1500
#define STATE_QUERY_BARRIER_POLL_MS 50
#define CLEAN_MAX_LATCH_LEVEL 0.92f
#define SOLUTION_MAX_LATCH_LEVEL 0.92f
#define IRR_STATE_MAX_AGE_SEC 30
#define PH_DRIFT_BIAS_PER_TICK 0.0002f
#define EC_DRIFT_BIAS_PER_TICK -0.0010f
#define PH_REACTION_BASE_DELTA 0.10f
#define EC_REACTION_BASE_DELTA 0.055f
#define PH_REACTION_NOMINAL_ML 8.0f
#define EC_REACTION_NOMINAL_ML 12.0f
#define CORRECTION_DURATION_TO_ML_PER_SEC 1.0f
#define CORRECTION_FILL_PHASE_FACTOR 0.50f
#define CORRECTION_RECIRC_PH_PHASE_FACTOR 2.50f
#define CORRECTION_RECIRC_EC_PHASE_FACTOR 3.20f
#define CORRECTION_RESPONSE_DELAY_TICKS 2
#define CORRECTION_DECAY_TICKS 4
#define CORRECTION_TRANSIENT_RATIO 0.60f
#define TELEMETRY_DRIFT_WAVE_AMPLITUDE 0.0009f
#define CORRECTION_REACTION_SCALE_MIN 0.5f
#define CORRECTION_REACTION_SCALE_MAX 5.0f
#define CONTROL_DELAY_MIN_MS 120
#define CONTROL_DELAY_MAX_MS 260
#define TRANSIENT_DELAY_BASE_MIN_MS 220
#define TRANSIENT_DELAY_BASE_MAX_MS 460
#define TRANSIENT_DELAY_EXTRA_MIN_MS 160
#define TRANSIENT_DELAY_EXTRA_MAX_MS 360
#define TRANSIENT_DELAY_SCALE_PERCENT 10
#define TRANSIENT_DELAY_SCALE_MIN_MS 220
#define TRANSIENT_DELAY_SCALE_MAX_MS 6500
#define CONFIG_REPORT_RETRY_DELAY_MS 250
#define CONFIG_REPORT_NODE_SPACING_MS 120
#define MIN_VALID_UNIX_TS_SEC 1000000000LL
#define COMMAND_DEDUP_WINDOW_SEC 180
#define COMMAND_DEDUP_CACHE_SIZE 32

#ifndef PROJECT_VER
#define PROJECT_VER "unknown"
#endif

typedef struct {
    const char *name;
    const char *type;
    const char *metric;
    bool is_actuator;
} channel_def_t;

typedef struct {
    const char *node_uid;
    const char *node_type;
    const channel_def_t *channels;
    size_t channels_count;
} virtual_node_t;

typedef struct {
    float flow_rate;
    float pump_bus_current;
    float ph_value;
    float ec_value;
    float water_level;
    float solution_level;
    float air_temp;
    float air_humidity;
    float light_level;

    bool irrigation_on;
    bool main_pump_on;
    bool valve_clean_fill_on;
    bool valve_clean_supply_on;
    bool valve_solution_fill_on;
    bool valve_solution_supply_on;
    bool valve_irrigation_on;
    bool clean_fill_stage_active;
    bool clean_max_latched;
    bool solution_fill_stage_active;
    bool solution_max_latched;
    bool tank_fill_on;
    bool tank_drain_on;
    bool fan_on;
    bool heater_on;
    bool light_on;
    bool ph_sensor_mode_active;
    bool ec_sensor_mode_active;
    bool force_clean_sensor_conflict;
    bool force_solution_sensor_conflict;
    bool simulate_clean_fill_timeout;
    bool simulate_solution_fill_timeout;
    int8_t level_clean_min_override;
    int8_t level_clean_max_override;
    int8_t level_solution_min_override;
    int8_t level_solution_max_override;

    uint8_t light_pwm;
    uint8_t irrigation_boost_ticks;
    uint8_t correction_boost_ticks;
    float pending_ph_delta;
    float pending_ec_delta;
    float ph_decay_remaining;
    float ec_decay_remaining;
    uint8_t pending_ph_delay_ticks;
    uint8_t pending_ec_delay_ticks;
    uint8_t ph_decay_ticks_remaining;
    uint8_t ec_decay_ticks_remaining;
    int64_t clean_fill_started_at;
    int64_t solution_fill_started_at;
} virtual_state_t;

typedef enum {
    COMMAND_KIND_SENSOR_PROBE = 0,
    COMMAND_KIND_ACTUATOR = 1,
    COMMAND_KIND_CONFIG_REPORT = 2,
    COMMAND_KIND_RESTART = 3,
    COMMAND_KIND_GENERIC = 4,
    COMMAND_KIND_STATE_QUERY = 5,
} command_kind_t;

typedef struct {
    char node_uid[64];
    char channel[64];
    char cmd_id[96];
    char cmd[64];

    command_kind_t kind;

    bool relay_state_present;
    bool relay_state;

    bool pwm_value_present;
    int pwm_value;

    bool amount_present;
    float amount_value;
    bool duration_ms_present;
    int duration_ms;

    bool sim_status_present;
    char sim_status[16];
    bool sim_no_effect;
    bool event_code_present;
    char event_code[96];
    bool clean_sensor_conflict_present;
    bool clean_sensor_conflict;
    bool solution_sensor_conflict_present;
    bool solution_sensor_conflict;
    bool clean_fill_timeout_present;
    bool clean_fill_timeout;
    bool solution_fill_timeout_present;
    bool solution_fill_timeout;
    bool level_clean_min_override_present;
    int8_t level_clean_min_override;
    bool level_clean_max_override_present;
    int8_t level_clean_max_override;
    bool level_solution_min_override_present;
    int8_t level_solution_min_override;
    bool level_solution_max_override_present;
    int8_t level_solution_max_override;
    bool ph_value_present;
    float ph_value;
    bool ec_value_present;
    float ec_value;
    int execute_delay_ms;
} pending_command_t;

static const channel_def_t IRRIGATION_CHANNELS[] = {
    {.name = "pump_main", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "valve_clean_fill", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "valve_clean_supply", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "valve_solution_fill", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "valve_solution_supply", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "valve_irrigation", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "level_clean_min", .type = "SENSOR", .metric = "WATER_LEVEL_SWITCH", .is_actuator = false},
    {.name = "level_clean_max", .type = "SENSOR", .metric = "WATER_LEVEL_SWITCH", .is_actuator = false},
    {.name = "level_solution_min", .type = "SENSOR", .metric = "WATER_LEVEL_SWITCH", .is_actuator = false},
    {.name = "level_solution_max", .type = "SENSOR", .metric = "WATER_LEVEL_SWITCH", .is_actuator = false},
};

static const channel_def_t PH_CORRECTION_CHANNELS[] = {
    {.name = "ph_sensor", .type = "SENSOR", .metric = "PH", .is_actuator = false},
    {.name = "pump_acid", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "pump_base", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    // Service channel required by automation-engine sensor mode dispatch.
    {.name = "system", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
};

static const channel_def_t EC_CORRECTION_CHANNELS[] = {
    {.name = "ec_sensor", .type = "SENSOR", .metric = "EC", .is_actuator = false},
    {.name = "pump_a", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "pump_b", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "pump_c", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "pump_d", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    // Service channel required by automation-engine sensor mode dispatch.
    {.name = "system", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
};

static const channel_def_t CLIMATE_CHANNELS[] = {
    {.name = "air_temp_c", .type = "SENSOR", .metric = "TEMPERATURE", .is_actuator = false},
    {.name = "air_rh", .type = "SENSOR", .metric = "HUMIDITY", .is_actuator = false},
    {.name = "fan_air", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "fan", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "heater", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
};

static const channel_def_t LIGHT_CHANNELS[] = {
    {.name = "light_level", .type = "SENSOR", .metric = "LIGHT_INTENSITY", .is_actuator = false},
    {.name = "white_light", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
};

static const virtual_node_t VIRTUAL_NODES[] = {
    {.node_uid = "nd-test-irrig-1", .node_type = "irrig", .channels = IRRIGATION_CHANNELS, .channels_count = sizeof(IRRIGATION_CHANNELS) / sizeof(IRRIGATION_CHANNELS[0])},
    {.node_uid = "nd-test-ph-1", .node_type = "ph", .channels = PH_CORRECTION_CHANNELS, .channels_count = sizeof(PH_CORRECTION_CHANNELS) / sizeof(PH_CORRECTION_CHANNELS[0])},
    {.node_uid = "nd-test-ec-1", .node_type = "ec", .channels = EC_CORRECTION_CHANNELS, .channels_count = sizeof(EC_CORRECTION_CHANNELS) / sizeof(EC_CORRECTION_CHANNELS[0])},
    {.node_uid = "nd-test-climate-1", .node_type = "climate", .channels = CLIMATE_CHANNELS, .channels_count = sizeof(CLIMATE_CHANNELS) / sizeof(CLIMATE_CHANNELS[0])},
    {.node_uid = "nd-test-light-1", .node_type = "light", .channels = LIGHT_CHANNELS, .channels_count = sizeof(LIGHT_CHANNELS) / sizeof(LIGHT_CHANNELS[0])},
};

#define VIRTUAL_NODE_COUNT (sizeof(VIRTUAL_NODES) / sizeof(VIRTUAL_NODES[0]))

typedef struct {
    char gh_uid[64];
    char zone_uid[64];
    bool preconfig_mode;
} virtual_node_namespace_t;

static virtual_node_namespace_t s_virtual_namespaces[VIRTUAL_NODE_COUNT] = {0};
static int64_t s_start_time_seconds = 0;
static int64_t s_timestamp_offset_sec = 0;
static bool s_timestamp_offset_valid = false;
static uint32_t s_telemetry_tick = 0;
static QueueHandle_t s_command_queue = NULL;
static QueueHandle_t s_state_command_queue = NULL;
static SemaphoreHandle_t s_topic_mutex = NULL;
static bool s_wildcard_subscriptions_ready = false;
static bool s_wildcard_subscribe_warned = false;
static bool s_factory_reset_pending = false;
static volatile bool s_config_report_on_connect_pending = false;
static bool s_state_command_fastpath_enabled = false;
static volatile bool s_command_worker_busy = false;
static volatile int64_t s_last_non_state_command_rx_ms = 0;

static void publish_telemetry_for_node(const char *node_uid, const char *channel, const char *metric_type, float value);

typedef struct {
    char cmd_id[96];
    int64_t seen_at_sec;
} recent_cmd_id_entry_t;

static recent_cmd_id_entry_t s_recent_cmd_ids[COMMAND_DEDUP_CACHE_SIZE] = {0};

static const virtual_state_t DEFAULT_VIRTUAL_STATE = {
    .flow_rate = 0.0f,
    .pump_bus_current = 150.0f,
    .ph_value = 6.90f,
    .ec_value = 0.60f,
    .water_level = 0.05f,
    .solution_level = 0.05f,
    .air_temp = 24.0f,
    .air_humidity = 60.0f,
    .light_level = 18000.0f,
    .irrigation_on = false,
    .main_pump_on = false,
    .valve_clean_fill_on = false,
    .valve_clean_supply_on = false,
    .valve_solution_fill_on = false,
    .valve_solution_supply_on = false,
    .valve_irrigation_on = false,
    .clean_fill_stage_active = false,
    .clean_max_latched = false,
    .solution_fill_stage_active = false,
    .solution_max_latched = false,
    .tank_fill_on = false,
    .tank_drain_on = false,
    .fan_on = false,
    .heater_on = false,
    .light_on = false,
    .ph_sensor_mode_active = false,
    .ec_sensor_mode_active = false,
    .force_clean_sensor_conflict = false,
    .force_solution_sensor_conflict = false,
    .simulate_clean_fill_timeout = false,
    .simulate_solution_fill_timeout = false,
    .level_clean_min_override = -1,
    .level_clean_max_override = -1,
    .level_solution_min_override = -1,
    .level_solution_max_override = -1,
    .light_pwm = 0,
    .irrigation_boost_ticks = 0,
    .correction_boost_ticks = 0,
    .pending_ph_delta = 0.0f,
    .pending_ec_delta = 0.0f,
    .ph_decay_remaining = 0.0f,
    .ec_decay_remaining = 0.0f,
    .pending_ph_delay_ticks = 0,
    .pending_ec_delay_ticks = 0,
    .ph_decay_ticks_remaining = 0,
    .ec_decay_ticks_remaining = 0,
    .clean_fill_started_at = 0,
    .solution_fill_started_at = 0,
};

static virtual_state_t s_virtual_state = {
    .flow_rate = 0.0f,
    .pump_bus_current = 150.0f,
    .ph_value = 6.90f,
    .ec_value = 0.60f,
    .water_level = 0.05f,
    .solution_level = 0.05f,
    .air_temp = 24.0f,
    .air_humidity = 60.0f,
    .light_level = 18000.0f,
    .irrigation_on = false,
    .main_pump_on = false,
    .valve_clean_fill_on = false,
    .valve_clean_supply_on = false,
    .valve_solution_fill_on = false,
    .valve_solution_supply_on = false,
    .valve_irrigation_on = false,
    .clean_fill_stage_active = false,
    .clean_max_latched = false,
    .solution_fill_stage_active = false,
    .solution_max_latched = false,
    .tank_fill_on = false,
    .tank_drain_on = false,
    .fan_on = false,
    .heater_on = false,
    .light_on = false,
    .ph_sensor_mode_active = false,
    .ec_sensor_mode_active = false,
    .force_clean_sensor_conflict = false,
    .force_solution_sensor_conflict = false,
    .simulate_clean_fill_timeout = false,
    .simulate_solution_fill_timeout = false,
    .level_clean_min_override = -1,
    .level_clean_max_override = -1,
    .level_solution_min_override = -1,
    .level_solution_max_override = -1,
    .light_pwm = 0,
    .irrigation_boost_ticks = 0,
    .correction_boost_ticks = 0,
    .pending_ph_delta = 0.0f,
    .pending_ec_delta = 0.0f,
    .ph_decay_remaining = 0.0f,
    .ec_decay_remaining = 0.0f,
    .pending_ph_delay_ticks = 0,
    .pending_ec_delay_ticks = 0,
    .ph_decay_ticks_remaining = 0,
    .ec_decay_ticks_remaining = 0,
    .clean_fill_started_at = 0,
    .solution_fill_started_at = 0,
};

static bool should_emit_uart_log(const char *line) {
    static const char *prefixes[] = {
        "cmd",
        "mqtt",
        "status",
        "hb",
        "cfg_report",
        "node_hello",
        "config",
        "setup",
        "task",
        "event",
        "ui_sync",
        "tel",
    };
    size_t i;

    if (!line || line[0] == '\0') {
        return false;
    }

    for (i = 0; i < (sizeof(prefixes) / sizeof(prefixes[0])); i++) {
        size_t len = strlen(prefixes[i]);
        if (strncmp(line, prefixes[i], len) == 0) {
            return true;
        }
    }

    return false;
}

static void ui_logf(const char *node_uid, const char *fmt, ...) {
    char line[96];
    const char *origin = (node_uid && node_uid[0] != '\0') ? node_uid : "SYS";
    va_list args;

    if (!fmt || fmt[0] == '\0') {
        return;
    }

    va_start(args, fmt);
    vsnprintf(line, sizeof(line), fmt, args);
    va_end(args);

    if (should_emit_uart_log(line)) {
        ESP_LOGI(CMD_TAG, "[%s] %s", origin, line);
    }
    test_node_ui_log_event(node_uid, line);
}

static int64_t get_uptime_seconds(void) {
    return esp_timer_get_time() / 1000000LL;
}

static int64_t get_uptime_ms_precise(void) {
    return esp_timer_get_time() / 1000LL;
}

static void reset_virtual_state_runtime(void) {
    s_virtual_state = DEFAULT_VIRTUAL_STATE;
}

static void maybe_calibrate_timestamp_offset_from_command_ts(int64_t command_ts_raw) {
    int64_t command_ts_sec = command_ts_raw;
    int64_t uptime_sec;
    int64_t previous_offset = s_timestamp_offset_sec;
    bool was_valid = s_timestamp_offset_valid;

    if (command_ts_sec > 1000000000000LL) {
        command_ts_sec /= 1000LL;
    }
    if (command_ts_sec < MIN_VALID_UNIX_TS_SEC) {
        return;
    }

    uptime_sec = get_uptime_seconds();
    s_timestamp_offset_sec = command_ts_sec - uptime_sec;
    s_timestamp_offset_valid = true;

    if (!was_valid || llabs(previous_offset - s_timestamp_offset_sec) > 2) {
        ESP_LOGI(
            CMD_TAG,
            "time calibrated from command: ts=%lld uptime=%lld offset=%lld",
            (long long)command_ts_sec,
            (long long)uptime_sec,
            (long long)s_timestamp_offset_sec
        );
    }
}

static bool is_duplicate_cmd_id(const char *cmd_id) {
    int free_index = -1;
    int oldest_index = 0;
    int64_t now_sec = get_uptime_seconds();

    if (!cmd_id || cmd_id[0] == '\0') {
        return false;
    }

    for (int i = 0; i < COMMAND_DEDUP_CACHE_SIZE; i++) {
        if (s_recent_cmd_ids[i].cmd_id[0] == '\0' ||
            (now_sec - s_recent_cmd_ids[i].seen_at_sec) > COMMAND_DEDUP_WINDOW_SEC) {
            if (free_index < 0) {
                free_index = i;
            }
            continue;
        }
        if (strcmp(s_recent_cmd_ids[i].cmd_id, cmd_id) == 0) {
            return true;
        }
        if (s_recent_cmd_ids[i].seen_at_sec < s_recent_cmd_ids[oldest_index].seen_at_sec) {
            oldest_index = i;
        }
    }

    int slot = (free_index >= 0) ? free_index : oldest_index;
    snprintf(s_recent_cmd_ids[slot].cmd_id, sizeof(s_recent_cmd_ids[slot].cmd_id), "%s", cmd_id);
    s_recent_cmd_ids[slot].seen_at_sec = now_sec;
    return false;
}

static int64_t get_timestamp_seconds(void) {
    int64_t wallclock_sec = (int64_t)time(NULL);
    int64_t uptime_sec = get_uptime_seconds();

    if (wallclock_sec >= MIN_VALID_UNIX_TS_SEC) {
        return wallclock_sec;
    }
    if (s_timestamp_offset_valid) {
        return uptime_sec + s_timestamp_offset_sec;
    }
    return uptime_sec;
}

static int64_t get_timestamp_ms(void) {
    return get_timestamp_seconds() * 1000LL;
}

static bool find_virtual_node_index(const char *node_uid, size_t *index_out) {
    size_t index;

    if (!node_uid || node_uid[0] == '\0') {
        return false;
    }

    for (index = 0; index < VIRTUAL_NODE_COUNT; index++) {
        if (strcmp(VIRTUAL_NODES[index].node_uid, node_uid) == 0) {
            if (index_out) {
                *index_out = index;
            }
            return true;
        }
    }

    return false;
}

static void init_virtual_namespaces(const char *gh_uid, const char *zone_uid) {
    size_t index;
    const char *safe_gh = (gh_uid && gh_uid[0] != '\0') ? gh_uid : DEFAULT_GH_UID;
    const char *safe_zone = (zone_uid && zone_uid[0] != '\0') ? zone_uid : DEFAULT_ZONE_UID;
    bool preconfig_mode = (strcmp(safe_gh, "gh-temp") == 0) || (strcmp(safe_zone, "zn-temp") == 0);

    for (index = 0; index < VIRTUAL_NODE_COUNT; index++) {
        snprintf(s_virtual_namespaces[index].gh_uid, sizeof(s_virtual_namespaces[index].gh_uid), "%s", safe_gh);
        snprintf(s_virtual_namespaces[index].zone_uid, sizeof(s_virtual_namespaces[index].zone_uid), "%s", safe_zone);
        s_virtual_namespaces[index].preconfig_mode = preconfig_mode;
    }
}

static bool get_node_namespace(
    const char *node_uid,
    char *gh_uid,
    size_t gh_uid_size,
    char *zone_uid,
    size_t zone_uid_size,
    bool *preconfig_mode
) {
    bool locked = false;
    size_t node_index = 0;

    if (!gh_uid || gh_uid_size == 0 || !zone_uid || zone_uid_size == 0 || !node_uid) {
        return false;
    }
    if (!find_virtual_node_index(node_uid, &node_index)) {
        return false;
    }

    if (s_topic_mutex) {
        if (xSemaphoreTake(s_topic_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            locked = true;
        }
    }

    snprintf(gh_uid, gh_uid_size, "%s", s_virtual_namespaces[node_index].gh_uid);
    snprintf(zone_uid, zone_uid_size, "%s", s_virtual_namespaces[node_index].zone_uid);
    if (preconfig_mode) {
        *preconfig_mode = s_virtual_namespaces[node_index].preconfig_mode;
    }

    if (locked) {
        xSemaphoreGive(s_topic_mutex);
    }

    return true;
}

static void ui_sync_all_virtual_nodes(bool set_offline_status) {
    size_t index;
    ESP_LOGI(TAG, "UI sync nodes start (set_offline=%d)", (int)set_offline_status);
    ui_logf(NULL, "ui_sync nodes start");

    for (index = 0; index < VIRTUAL_NODE_COUNT; index++) {
        char gh_uid[64] = {0};
        char zone_uid[64] = {0};

        if (!get_node_namespace(
            VIRTUAL_NODES[index].node_uid,
            gh_uid,
            sizeof(gh_uid),
            zone_uid,
            sizeof(zone_uid),
            NULL
        )) {
            snprintf(zone_uid, sizeof(zone_uid), "--");
        }

        test_node_ui_register_node(VIRTUAL_NODES[index].node_uid, zone_uid);
        test_node_ui_set_node_zone(VIRTUAL_NODES[index].node_uid, zone_uid);
        ESP_LOGI(
            TAG,
            "UI sync node[%u]: uid=%s zone=%s",
            (unsigned)index,
            VIRTUAL_NODES[index].node_uid,
            zone_uid
        );
        if (set_offline_status) {
            test_node_ui_set_node_status(VIRTUAL_NODES[index].node_uid, "OFFLINE");
        }
    }
    ui_logf(NULL, "ui_sync nodes done");
    ESP_LOGI(TAG, "UI sync nodes done");
}

static bool namespace_matches_node(const char *node_uid, const char *gh_uid, const char *zone_uid) {
    char current_gh[64] = {0};
    char current_zone[64] = {0};

    if (!node_uid || !gh_uid || !zone_uid) {
        return false;
    }

    if (!get_node_namespace(node_uid, current_gh, sizeof(current_gh), current_zone, sizeof(current_zone), NULL)) {
        return false;
    }
    return strcmp(current_gh, gh_uid) == 0 && strcmp(current_zone, zone_uid) == 0;
}

static bool is_temp_namespace(const char *gh_uid, const char *zone_uid) {
    if (!gh_uid || !zone_uid) {
        return false;
    }
    return strcmp(gh_uid, "gh-temp") == 0 && strcmp(zone_uid, "zn-temp") == 0;
}

static bool update_node_namespace(const char *node_uid, const char *gh_uid, const char *zone_uid, const char *reason) {
    size_t node_index = 0;
    bool locked = false;
    bool changed = false;

    if (!node_uid || node_uid[0] == '\0') {
        return false;
    }
    if (!gh_uid || !zone_uid || gh_uid[0] == '\0' || zone_uid[0] == '\0') {
        return false;
    }
    if (!find_virtual_node_index(node_uid, &node_index)) {
        return false;
    }

    if (s_topic_mutex && xSemaphoreTake(s_topic_mutex, pdMS_TO_TICKS(200)) == pdTRUE) {
        locked = true;
    }

    if (
        strcmp(s_virtual_namespaces[node_index].gh_uid, gh_uid) != 0 ||
        strcmp(s_virtual_namespaces[node_index].zone_uid, zone_uid) != 0
    ) {
        snprintf(s_virtual_namespaces[node_index].gh_uid, sizeof(s_virtual_namespaces[node_index].gh_uid), "%s", gh_uid);
        snprintf(s_virtual_namespaces[node_index].zone_uid, sizeof(s_virtual_namespaces[node_index].zone_uid), "%s", zone_uid);
        s_virtual_namespaces[node_index].preconfig_mode = (strcmp(gh_uid, "gh-temp") == 0) || (strcmp(zone_uid, "zn-temp") == 0);
        changed = true;
    }

    if (locked) {
        xSemaphoreGive(s_topic_mutex);
    }

    if (changed) {
        test_node_ui_set_node_zone(node_uid, zone_uid);
        ui_logf(node_uid, "zone -> %s", zone_uid);
        ESP_LOGI(
            TAG,
            "Node namespace updated: node=%s gh=%s zone=%s reason=%s",
            node_uid,
            gh_uid,
            zone_uid,
            reason ? reason : "unknown"
        );
    }

    return changed;
}

static bool parse_config_topic(
    const char *topic,
    char *out_gh_uid,
    size_t out_gh_uid_size,
    char *out_zone_uid,
    size_t out_zone_uid_size,
    char *out_node_uid,
    size_t out_node_uid_size
) {
    char topic_copy[192];
    char *saveptr = NULL;
    char *token;
    int segment = 0;
    const char *prefix = NULL;
    const char *gh_uid = NULL;
    const char *zone_uid = NULL;
    const char *node_uid = NULL;
    const char *message_type = NULL;

    if (!topic || !out_gh_uid || !out_zone_uid || !out_node_uid) {
        return false;
    }

    if (strlen(topic) >= sizeof(topic_copy)) {
        return false;
    }

    strcpy(topic_copy, topic);
    token = strtok_r(topic_copy, "/", &saveptr);
    while (token) {
        if (segment == 0) {
            prefix = token;
        } else if (segment == 1) {
            gh_uid = token;
        } else if (segment == 2) {
            zone_uid = token;
        } else if (segment == 3) {
            node_uid = token;
        } else if (segment == 4) {
            message_type = token;
        }
        segment++;
        token = strtok_r(NULL, "/", &saveptr);
    }

    if (segment != 5) {
        return false;
    }
    if (!prefix || strcmp(prefix, "hydro") != 0) {
        return false;
    }
    if (!gh_uid || !zone_uid || !node_uid || !message_type) {
        return false;
    }
    if (strcmp(message_type, "config") != 0) {
        return false;
    }

    snprintf(out_gh_uid, out_gh_uid_size, "%s", gh_uid);
    snprintf(out_zone_uid, out_zone_uid_size, "%s", zone_uid);
    snprintf(out_node_uid, out_node_uid_size, "%s", node_uid);
    return true;
}

static float clamp_float(float value, float min_value, float max_value) {
    if (value < min_value) {
        return min_value;
    }
    if (value > max_value) {
        return max_value;
    }
    return value;
}

static float resolve_correction_reaction_scale(const pending_command_t *job, float nominal_ml) {
    float commanded_ml = nominal_ml;
    float scale;

    if (!job || nominal_ml <= 0.0f) {
        return 1.0f;
    }

    if (job->amount_present && job->amount_value > 0.0f) {
        commanded_ml = job->amount_value;
    } else if (job->duration_ms_present && job->duration_ms > 0) {
        /* E2E correction scenarios configure calibration at 1 ml/s (duration_ms ~= target ml * 1000). */
        commanded_ml = (((float)job->duration_ms) / 1000.0f) * CORRECTION_DURATION_TO_ML_PER_SEC;
    }

    scale = commanded_ml / nominal_ml;
    return clamp_float(scale, CORRECTION_REACTION_SCALE_MIN, CORRECTION_REACTION_SCALE_MAX);
}

static float resolve_correction_phase_factor(bool ec_channel) {
    bool recirculation_path =
        s_virtual_state.main_pump_on &&
        s_virtual_state.valve_solution_supply_on &&
        s_virtual_state.valve_solution_fill_on;
    bool solution_fill_path =
        s_virtual_state.main_pump_on &&
        s_virtual_state.valve_clean_supply_on &&
        s_virtual_state.valve_solution_fill_on &&
        !s_virtual_state.valve_solution_supply_on;

    if (recirculation_path) {
        return ec_channel ? CORRECTION_RECIRC_EC_PHASE_FACTOR : CORRECTION_RECIRC_PH_PHASE_FACTOR;
    }
    if (solution_fill_path) {
        return CORRECTION_FILL_PHASE_FACTOR;
    }
    return 1.0f;
}

static void clear_correction_response_state(void) {
    s_virtual_state.pending_ph_delta = 0.0f;
    s_virtual_state.pending_ec_delta = 0.0f;
    s_virtual_state.ph_decay_remaining = 0.0f;
    s_virtual_state.ec_decay_remaining = 0.0f;
    s_virtual_state.pending_ph_delay_ticks = 0;
    s_virtual_state.pending_ec_delay_ticks = 0;
    s_virtual_state.ph_decay_ticks_remaining = 0;
    s_virtual_state.ec_decay_ticks_remaining = 0;
    s_virtual_state.correction_boost_ticks = 0;
}

static void schedule_correction_response(bool ec_channel, float delta) {
    float *pending_delta = ec_channel ? &s_virtual_state.pending_ec_delta : &s_virtual_state.pending_ph_delta;
    uint8_t *delay_ticks = ec_channel ? &s_virtual_state.pending_ec_delay_ticks : &s_virtual_state.pending_ph_delay_ticks;
    uint8_t total_activity_ticks = CORRECTION_RESPONSE_DELAY_TICKS + CORRECTION_DECAY_TICKS + 1;

    *pending_delta += delta;
    if (*delay_ticks == 0) {
        *delay_ticks = CORRECTION_RESPONSE_DELAY_TICKS;
    }
    if (s_virtual_state.correction_boost_ticks < total_activity_ticks) {
        s_virtual_state.correction_boost_ticks = total_activity_ticks;
    }
}

static void apply_metric_decay(
    float *value,
    float *decay_remaining,
    uint8_t *decay_ticks_remaining,
    float min_value,
    float max_value
) {
    float step;

    if (!value || !decay_remaining || !decay_ticks_remaining) {
        return;
    }
    if (*decay_ticks_remaining == 0 || fabsf(*decay_remaining) < 0.0001f) {
        *decay_remaining = 0.0f;
        *decay_ticks_remaining = 0;
        return;
    }

    step = *decay_remaining / (float)(*decay_ticks_remaining);
    *value = clamp_float(*value - step, min_value, max_value);
    *decay_remaining -= step;
    (*decay_ticks_remaining)--;

    if (*decay_ticks_remaining == 0 || fabsf(*decay_remaining) < 0.0001f) {
        *decay_remaining = 0.0f;
        *decay_ticks_remaining = 0;
    }
}

static void apply_scheduled_metric_response(
    float *value,
    float *pending_delta,
    uint8_t *delay_ticks,
    float *decay_remaining,
    uint8_t *decay_ticks_remaining,
    float min_value,
    float max_value
) {
    bool onset_applied = false;

    if (!value || !pending_delta || !delay_ticks || !decay_remaining || !decay_ticks_remaining) {
        return;
    }

    if (*delay_ticks > 0) {
        (*delay_ticks)--;
        if (*delay_ticks == 0 && fabsf(*pending_delta) >= 0.0001f) {
            float onset_delta = *pending_delta;
            float transient_delta = onset_delta * CORRECTION_TRANSIENT_RATIO;

            *value = clamp_float(*value + onset_delta, min_value, max_value);
            *pending_delta = 0.0f;
            onset_applied = true;

            if (fabsf(transient_delta) >= 0.0001f) {
                *decay_remaining += transient_delta;
                if (*decay_ticks_remaining < CORRECTION_DECAY_TICKS) {
                    *decay_ticks_remaining = CORRECTION_DECAY_TICKS;
                }
            }
        }
    }

    if (!onset_applied) {
        apply_metric_decay(value, decay_remaining, decay_ticks_remaining, min_value, max_value);
    }
}

static void apply_scheduled_correction_responses(void) {
    apply_scheduled_metric_response(
        &s_virtual_state.ph_value,
        &s_virtual_state.pending_ph_delta,
        &s_virtual_state.pending_ph_delay_ticks,
        &s_virtual_state.ph_decay_remaining,
        &s_virtual_state.ph_decay_ticks_remaining,
        4.8f,
        7.2f
    );
    apply_scheduled_metric_response(
        &s_virtual_state.ec_value,
        &s_virtual_state.pending_ec_delta,
        &s_virtual_state.pending_ec_delay_ticks,
        &s_virtual_state.ec_decay_remaining,
        &s_virtual_state.ec_decay_ticks_remaining,
        0.4f,
        3.2f
    );
}

static int random_range_ms(int min_value, int max_value) {
    uint32_t span;
    if (max_value <= min_value) {
        return min_value;
    }
    span = (uint32_t)(max_value - min_value + 1);
    return min_value + (int)(esp_random() % span);
}

static float level_switch_from_threshold(float level_value, float threshold, bool active_when_above) {
    if (active_when_above) {
        return level_value >= threshold ? 1.0f : 0.0f;
    }
    return level_value <= threshold ? 1.0f : 0.0f;
}

static float override_switch_value(int8_t override_value) {
    if (override_value > 0) {
        return 1.0f;
    }
    return 0.0f;
}

static const char *switch_override_label(int8_t override_value) {
    if (override_value < 0) {
        return "auto";
    }
    return override_value > 0 ? "on" : "off";
}

static bool parse_switch_override_param(cJSON *item, int8_t *out_value) {
    if (!item || !out_value) {
        return false;
    }
    if (cJSON_IsBool(item)) {
        *out_value = cJSON_IsTrue(item) ? 1 : 0;
        return true;
    }
    if (cJSON_IsNumber(item)) {
        double raw = cJSON_GetNumberValue(item);
        if (raw < 0.0) {
            *out_value = -1;
        } else {
            *out_value = raw > 0.0 ? 1 : 0;
        }
        return true;
    }
    return false;
}

static float resolve_clean_max_switch_value(void) {
    if (s_virtual_state.level_clean_max_override >= 0) {
        return override_switch_value(s_virtual_state.level_clean_max_override);
    }
    if (s_virtual_state.clean_max_latched) {
        return 1.0f;
    }
    return level_switch_from_threshold(s_virtual_state.water_level, 0.90f, true);
}

static float resolve_clean_min_switch_value(void) {
    if (s_virtual_state.level_clean_min_override >= 0) {
        return override_switch_value(s_virtual_state.level_clean_min_override);
    }
    bool clean_max_active = false;
    if (s_virtual_state.clean_max_latched) {
        clean_max_active = true;
    } else if (level_switch_from_threshold(s_virtual_state.water_level, 0.90f, true) >= 0.5f) {
        clean_max_active = true;
    }
    if (s_virtual_state.force_clean_sensor_conflict && clean_max_active) {
        return 0.0f;
    }
    if (s_virtual_state.clean_max_latched) {
        return 1.0f;
    }
    if (s_virtual_state.clean_fill_stage_active && s_virtual_state.clean_fill_started_at > 0) {
        int64_t now_sec = get_timestamp_seconds();
        if ((now_sec - s_virtual_state.clean_fill_started_at) >= CLEAN_FILL_MIN_DELAY_SEC) {
            return 1.0f;
        }
    }
    return level_switch_from_threshold(s_virtual_state.water_level, 0.18f, true);
}

static float resolve_solution_max_switch_value(void) {
    if (s_virtual_state.level_solution_max_override >= 0) {
        return override_switch_value(s_virtual_state.level_solution_max_override);
    }
    if (s_virtual_state.solution_max_latched) {
        return 1.0f;
    }
    return level_switch_from_threshold(s_virtual_state.solution_level, 0.90f, true);
}

static float resolve_solution_min_switch_value(void) {
    if (s_virtual_state.level_solution_min_override >= 0) {
        return override_switch_value(s_virtual_state.level_solution_min_override);
    }
    bool solution_max_active = false;
    if (s_virtual_state.solution_max_latched) {
        solution_max_active = true;
    } else if (level_switch_from_threshold(s_virtual_state.solution_level, 0.90f, true) >= 0.5f) {
        solution_max_active = true;
    }
    if (s_virtual_state.force_solution_sensor_conflict && solution_max_active) {
        return 0.0f;
    }
    if (s_virtual_state.solution_max_latched) {
        return 1.0f;
    }
    if (s_virtual_state.solution_fill_stage_active && s_virtual_state.solution_fill_started_at > 0) {
        int64_t now_sec = get_timestamp_seconds();
        if ((now_sec - s_virtual_state.solution_fill_started_at) >= SOLUTION_FILL_MIN_DELAY_SEC) {
            return 1.0f;
        }
    }
    return level_switch_from_threshold(s_virtual_state.solution_level, 0.18f, true);
}

static void publish_current_virtual_sensor_snapshot(bool include_levels, bool include_ph, bool include_ec) {
    if (!mqtt_manager_is_connected()) {
        return;
    }

    if (include_levels) {
        publish_telemetry_for_node(
            "nd-test-irrig-1",
            "level_clean_min",
            "WATER_LEVEL_SWITCH",
            resolve_clean_min_switch_value()
        );
        publish_telemetry_for_node(
            "nd-test-irrig-1",
            "level_clean_max",
            "WATER_LEVEL_SWITCH",
            resolve_clean_max_switch_value()
        );
        publish_telemetry_for_node(
            "nd-test-irrig-1",
            "level_solution_min",
            "WATER_LEVEL_SWITCH",
            resolve_solution_min_switch_value()
        );
        publish_telemetry_for_node(
            "nd-test-irrig-1",
            "level_solution_max",
            "WATER_LEVEL_SWITCH",
            resolve_solution_max_switch_value()
        );
    }

    if (include_ph && s_virtual_state.ph_sensor_mode_active) {
        publish_telemetry_for_node("nd-test-ph-1", "ph_sensor", "PH", s_virtual_state.ph_value);
    }
    if (include_ec && s_virtual_state.ec_sensor_mode_active) {
        publish_telemetry_for_node("nd-test-ec-1", "ec_sensor", "EC", s_virtual_state.ec_value);
    }
}

static bool is_clean_fill_active(void) {
    return s_virtual_state.tank_fill_on
        || (s_virtual_state.main_pump_on && s_virtual_state.valve_clean_fill_on);
}

static bool is_solution_fill_active(void) {
    return s_virtual_state.main_pump_on
        && s_virtual_state.valve_clean_supply_on
        && s_virtual_state.valve_solution_fill_on;
}

static bool is_irrigation_active(void) {
    return s_virtual_state.irrigation_on
        || (
            s_virtual_state.main_pump_on
            && s_virtual_state.valve_solution_supply_on
            && s_virtual_state.valve_irrigation_on
        );
}

static bool is_transient_command(const pending_command_t *job) {
    if (!job) {
        return false;
    }
    return strcmp(job->cmd, "run_pump") == 0 || strcmp(job->cmd, "dose") == 0;
}

static bool is_valid_terminal_status(const char *status) {
    if (!status || status[0] == '\0') {
        return false;
    }
    return strcmp(status, "DONE") == 0 ||
           strcmp(status, "NO_EFFECT") == 0 ||
           strcmp(status, "BUSY") == 0 ||
           strcmp(status, "INVALID") == 0 ||
           strcmp(status, "ERROR") == 0;
}

static bool is_main_pump_channel(const char *channel) {
    return channel
        && (
            strcmp(channel, "pump_main") == 0 ||
            strcmp(channel, "main_pump") == 0
        );
}

static bool is_fill_channel(const char *channel);
static bool is_drain_channel(const char *channel);

static bool is_water_contour_channel(const char *channel) {
    if (!channel) {
        return false;
    }
    return strcmp(channel, "pump_irrigation") == 0
        || is_main_pump_channel(channel)
        || strcmp(channel, "valve_clean_fill") == 0
        || strcmp(channel, "valve_clean_supply") == 0
        || strcmp(channel, "valve_solution_fill") == 0
        || strcmp(channel, "valve_solution_supply") == 0
        || strcmp(channel, "valve_irrigation") == 0
        || is_fill_channel(channel)
        || is_drain_channel(channel);
}

static bool is_fill_channel(const char *channel) {
    return channel
        && (
            strcmp(channel, "pump_in") == 0 ||
            strcmp(channel, "fill_valve") == 0 ||
            strcmp(channel, "water_control") == 0
        );
}

static bool is_drain_channel(const char *channel) {
    return channel
        && (
            strcmp(channel, "drain_main") == 0 ||
            strcmp(channel, "drain_valve") == 0 ||
            strcmp(channel, "drain_pump") == 0 ||
            strcmp(channel, "drain") == 0
        );
}

static bool is_ph_correction_channel(const char *channel) {
    return channel
        && (
            strcmp(channel, "pump_acid") == 0 ||
            strcmp(channel, "pump_base") == 0
        );
}

static bool is_ec_correction_channel(const char *channel) {
    return channel
        && (
            strcmp(channel, "pump_a") == 0 ||
            strcmp(channel, "pump_b") == 0 ||
            strcmp(channel, "pump_c") == 0 ||
            strcmp(channel, "pump_d") == 0
        );
}

static bool is_main_pump_interlock_satisfied(void) {
    bool clean_fill_path = s_virtual_state.valve_clean_fill_on;
    bool solution_fill_path = s_virtual_state.valve_clean_supply_on && s_virtual_state.valve_solution_fill_on;
    bool recirculation_path = s_virtual_state.valve_solution_supply_on && s_virtual_state.valve_solution_fill_on;
    bool irrigation_path = s_virtual_state.valve_solution_supply_on && s_virtual_state.valve_irrigation_on;
    return clean_fill_path || solution_fill_path || recirculation_path || irrigation_path;
}

static void append_main_pump_interlock_error(cJSON *details) {
    if (!details) {
        return;
    }
    cJSON_AddStringToObject(details, "error", "pump_interlock_blocked");
    cJSON_AddStringToObject(details, "error_code", "pump_interlock_blocked");
    cJSON_AddStringToObject(
        details,
        "error_message",
        "pump_main requires valid flow path: clean_fill OR (clean_supply+solution_fill) OR (solution_supply+solution_fill) OR (solution_supply+irrigation)"
    );
}

static bool is_storage_system_channel(const char *channel) {
    return channel
        && (
            strcmp(channel, "system") == 0 ||
            strcmp(channel, "storage_state") == 0
        );
}

static bool is_supported_actuator_command(const char *channel, const char *cmd) {
    if (!channel || !cmd || channel[0] == '\0' || cmd[0] == '\0') {
        return false;
    }

    if (strcmp(channel, "pump_irrigation") == 0 || is_main_pump_channel(channel)) {
        return strcmp(cmd, "set_relay") == 0 ||
               strcmp(cmd, "run_pump") == 0 ||
               strcmp(cmd, "dose") == 0;
    }

    if (strcmp(channel, "valve_clean_fill") == 0 ||
        strcmp(channel, "valve_clean_supply") == 0 ||
        strcmp(channel, "valve_solution_fill") == 0 ||
        strcmp(channel, "valve_solution_supply") == 0 ||
        strcmp(channel, "valve_irrigation") == 0 ||
        strcmp(channel, "fan_air") == 0 ||
        strcmp(channel, "fan") == 0 ||
        strcmp(channel, "heater") == 0) {
        return strcmp(cmd, "set_relay") == 0;
    }

    if (strcmp(channel, "white_light") == 0) {
        return strcmp(cmd, "set_relay") == 0 || strcmp(cmd, "set_pwm") == 0;
    }

    if (is_fill_channel(channel) || is_drain_channel(channel) || is_ph_correction_channel(channel) || is_ec_correction_channel(channel)) {
        return strcmp(cmd, "set_relay") == 0 ||
               strcmp(cmd, "run_pump") == 0 ||
               strcmp(cmd, "dose") == 0;
    }

    if (is_storage_system_channel(channel)) {
        return strcmp(cmd, "reset_state") == 0 ||
               strcmp(cmd, "emit_event") == 0 ||
               strcmp(cmd, "set_fault_mode") == 0 ||
               strcmp(cmd, "reset_binding") == 0 ||
               strcmp(cmd, "activate_sensor_mode") == 0 ||
               strcmp(cmd, "deactivate_sensor_mode") == 0;
    }

    return false;
}

static bool publish_all_config_reports(const char *reason);
static void handle_ui_settings_action(test_node_ui_settings_action_t action, void *user_ctx);
static bool should_boot_in_preconfig_mode(const char *gh_uid, const char *zone_uid);
static void persist_received_config_or_namespace(
    const char *node_uid,
    const char *config_payload,
    int config_payload_len,
    const char *gh_uid,
    const char *zone_uid
);

static const virtual_node_t *find_virtual_node(const char *node_uid) {
    size_t index = 0;
    if (find_virtual_node_index(node_uid, &index)) {
        return &VIRTUAL_NODES[index];
    }
    return NULL;
}

static const char *resolve_actuator_type(const char *channel_name) {
    if (!channel_name) {
        return "RELAY";
    }
    if (strstr(channel_name, "pump") != NULL) {
        return "PUMP";
    }
    if (strstr(channel_name, "light") != NULL) {
        return "LED";
    }
    if (strstr(channel_name, "fan") != NULL) {
        return "FAN";
    }
    return "RELAY";
}

static bool actuator_type_requires_relay_type(const char *actuator_type) {
    if (!actuator_type || actuator_type[0] == '\0') {
        return false;
    }

    return strcasecmp(actuator_type, "RELAY") == 0 ||
           strcasecmp(actuator_type, "VALVE") == 0 ||
           strcasecmp(actuator_type, "FAN") == 0 ||
           strcasecmp(actuator_type, "HEATER") == 0;
}

static const char *resolve_relay_type_for_channel(const char *channel_name) {
    (void)channel_name;
    // Для test-node используем безопасное дефолтное реле для совместимости
    // с backend-валидацией full config.
    return "NO";
}

static esp_err_t publish_json_payload(const char *topic, cJSON *json, int qos, int retain) {
    if (!topic || !json) {
        return ESP_ERR_INVALID_ARG;
    }

    char *payload = cJSON_PrintUnformatted(json);
    if (!payload) {
        return ESP_ERR_NO_MEM;
    }

    esp_err_t err = mqtt_manager_publish_raw(topic, payload, qos, retain);
    free(payload);
    return err;
}

static esp_err_t publish_json_payload_preallocated(
    const char *topic,
    cJSON *json,
    int qos,
    int retain,
    char *payload_buf,
    size_t payload_buf_size
) {
    if (!topic || !json || !payload_buf || payload_buf_size == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    payload_buf[0] = '\0';
    if (!cJSON_PrintPreallocated(json, payload_buf, (int)payload_buf_size, false)) {
        return ESP_ERR_NO_MEM;
    }

    return mqtt_manager_publish_raw(topic, payload_buf, qos, retain);
}

static bool format_json_number_from_float(char *buffer, size_t buffer_size, float value) {
    const uint32_t scale = 1000U;
    int len;
    int64_t scaled_abs;
    int64_t whole_part;
    int64_t fractional_part;
    bool negative;

    if (!buffer || buffer_size == 0) {
        return false;
    }

    if (!isfinite(value) || fabsf(value) > 1000000000.0f) {
        len = snprintf(buffer, buffer_size, "0");
        return len > 0 && (size_t)len < buffer_size;
    }

    negative = value < 0.0f;
    scaled_abs = (int64_t)llround((double)fabsf(value) * (double)scale);
    whole_part = scaled_abs / (int64_t)scale;
    fractional_part = scaled_abs % (int64_t)scale;

    if (fractional_part == 0) {
        len = snprintf(
            buffer,
            buffer_size,
            "%s%lld",
            negative ? "-" : "",
            (long long)whole_part
        );
    } else {
        char *dot = NULL;
        char *tail = NULL;

        len = snprintf(
            buffer,
            buffer_size,
            "%s%lld.%03lld",
            negative ? "-" : "",
            (long long)whole_part,
            (long long)fractional_part
        );
        if (len <= 0 || (size_t)len >= buffer_size) {
            return false;
        }

        dot = strchr(buffer, '.');
        if (!dot) {
            return true;
        }

        tail = buffer + strlen(buffer) - 1;
        while (tail > dot && *tail == '0') {
            *tail-- = '\0';
        }
        if (tail == dot) {
            *tail = '\0';
        }
        return true;
    }

    return len > 0 && (size_t)len < buffer_size;
}

static esp_err_t build_topic(char *buffer, size_t buffer_size, const char *node_uid, const char *channel, const char *message_type) {
    int len;
    char gh_uid[64];
    char zone_uid[64];

    if (!buffer || !node_uid || !message_type || buffer_size == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    if (!get_node_namespace(node_uid, gh_uid, sizeof(gh_uid), zone_uid, sizeof(zone_uid), NULL)) {
        ESP_LOGW(TAG, "Failed to resolve namespace for node=%s", node_uid);
        return ESP_ERR_NOT_FOUND;
    }

    if (channel && channel[0] != '\0') {
        len = snprintf(
            buffer,
            buffer_size,
            "hydro/%s/%s/%s/%s/%s",
            gh_uid,
            zone_uid,
            node_uid,
            channel,
            message_type
        );
    } else {
        len = snprintf(
            buffer,
            buffer_size,
            "hydro/%s/%s/%s/%s",
            gh_uid,
            zone_uid,
            node_uid,
            message_type
        );
    }

    if (len < 0 || (size_t)len >= buffer_size) {
        return ESP_ERR_INVALID_SIZE;
    }
    return ESP_OK;
}

static void publish_status_for_node(const char *node_uid, const char *status) {
    char topic[192];
    cJSON *json;

    if (build_topic(topic, sizeof(topic), node_uid, NULL, "status") != ESP_OK) {
        ESP_LOGE(TAG, "Failed to build status topic for %s", node_uid);
        return;
    }

    json = cJSON_CreateObject();
    if (!json) {
        return;
    }
    cJSON_AddStringToObject(json, "status", status);
    cJSON_AddNumberToObject(json, "ts", (double)get_timestamp_seconds());

    publish_json_payload(topic, json, 1, 1);
    test_node_ui_set_node_status(node_uid, status);
    if (status && strcmp(status, "ONLINE") != 0) {
        test_node_ui_mark_node_lwt(node_uid);
    }
    ui_logf(node_uid, "status %s", status ? status : "UNKNOWN");
    cJSON_Delete(json);
}

static void publish_heartbeat_for_node(const char *node_uid) {
    char topic[192];
    cJSON *json;
    wifi_ap_record_t ap_info;
    int64_t current_time = get_timestamp_seconds();
    int64_t uptime_seconds = s_start_time_seconds > 0 ? (current_time - s_start_time_seconds) : 0;

    if (!mqtt_manager_is_connected()) {
        return;
    }

    if (build_topic(topic, sizeof(topic), node_uid, NULL, "heartbeat") != ESP_OK) {
        ESP_LOGE(TAG, "Failed to build heartbeat topic for %s", node_uid);
        return;
    }

    json = cJSON_CreateObject();
    if (!json) {
        return;
    }

    cJSON_AddNumberToObject(json, "uptime", (double)uptime_seconds);
    cJSON_AddNumberToObject(json, "free_heap", (double)esp_get_free_heap_size());
    if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
        cJSON_AddNumberToObject(json, "rssi", (double)ap_info.rssi);
    }

    publish_json_payload(topic, json, 1, 0);
    test_node_ui_mark_node_heartbeat(node_uid);
    ui_logf(node_uid, "hb up=%lds heap=%u", (long)uptime_seconds, (unsigned)esp_get_free_heap_size());
    cJSON_Delete(json);
}

static void publish_telemetry_for_node(const char *node_uid, const char *channel, const char *metric_type, float value) {
    char topic[192];
    char payload[256];
    char value_buf[32];
    bool has_sensor_mode_flags = false;
    bool sensor_mode_active = false;
    int len;

    if (!mqtt_manager_is_connected() || !metric_type || metric_type[0] == '\0') {
        return;
    }

    if (build_topic(topic, sizeof(topic), node_uid, channel, "telemetry") != ESP_OK) {
        ESP_LOGE(TAG, "Failed to build telemetry topic for %s/%s", node_uid, channel);
        return;
    }

    if (!format_json_number_from_float(value_buf, sizeof(value_buf), value)) {
        ESP_LOGE(TAG, "Failed to format telemetry value for %s/%s", node_uid, channel ? channel : "-");
        return;
    }

    if (channel && strcmp(channel, "ph_sensor") == 0) {
        has_sensor_mode_flags = true;
        sensor_mode_active = s_virtual_state.ph_sensor_mode_active;
    } else if (channel && strcmp(channel, "ec_sensor") == 0) {
        has_sensor_mode_flags = true;
        sensor_mode_active = s_virtual_state.ec_sensor_mode_active;
    }

    if (has_sensor_mode_flags) {
        len = snprintf(
            payload,
            sizeof(payload),
            "{\"metric_type\":\"%s\",\"value\":%s,\"ts\":%lld,\"stub\":true,"
            "\"flow_active\":%s,\"stable\":%s,\"corrections_allowed\":%s}",
            metric_type,
            value_buf,
            (long long)get_timestamp_seconds(),
            sensor_mode_active ? "true" : "false",
            sensor_mode_active ? "true" : "false",
            sensor_mode_active ? "true" : "false"
        );
    } else {
        len = snprintf(
            payload,
            sizeof(payload),
            "{\"metric_type\":\"%s\",\"value\":%s,\"ts\":%lld,\"stub\":true}",
            metric_type,
            value_buf,
            (long long)get_timestamp_seconds()
        );
    }

    if (len <= 0 || (size_t)len >= sizeof(payload)) {
        ESP_LOGE(TAG, "Telemetry payload overflow for %s/%s", node_uid, channel ? channel : "-");
        return;
    }

    (void)mqtt_manager_publish_raw(topic, payload, 1, 0);
    ui_logf(
        node_uid,
        "tel %s/%s=%.2f",
        channel ? channel : "-",
        metric_type ? metric_type : "-",
        (double)value
    );
}

static esp_err_t publish_config_report_for_node(const virtual_node_t *node) {
    char topic[192];
    char gh_uid[64] = {0};
    char zone_uid[64] = {0};
    // Важно: не держим большой буфер на стеке, т.к. функция может вызываться из mqtt_task callback.
    // Выделяем буфер в heap на время публикации.
    char *payload_buf = NULL;
    const size_t payload_buf_size = 8192;
    bool node_preconfig_mode = false;
    cJSON *json;
    cJSON *channels;
    esp_err_t publish_err;
    size_t index;

    if (!node) {
        return ESP_ERR_INVALID_ARG;
    }

    if (build_topic(topic, sizeof(topic), node->node_uid, NULL, "config_report") != ESP_OK) {
        ESP_LOGE(TAG, "Failed to build config_report topic for %s", node->node_uid);
        return ESP_FAIL;
    }

    json = cJSON_CreateObject();
    if (!json) {
        return ESP_ERR_NO_MEM;
    }

    if (!get_node_namespace(node->node_uid, gh_uid, sizeof(gh_uid), zone_uid, sizeof(zone_uid), &node_preconfig_mode)) {
        ESP_LOGW(TAG, "Failed to resolve namespace for config_report node=%s", node->node_uid);
        cJSON_Delete(json);
        return ESP_FAIL;
    }

    cJSON_AddStringToObject(json, "node_id", node->node_uid);
    cJSON_AddNumberToObject(json, "version", 3);
    cJSON_AddStringToObject(json, "type", node->node_type);
    cJSON_AddStringToObject(json, "gh_uid", gh_uid);
    cJSON_AddStringToObject(json, "zone_uid", zone_uid);

    channels = cJSON_CreateArray();
    if (!channels) {
        cJSON_Delete(json);
        return ESP_ERR_NO_MEM;
    }

    for (index = 0; index < node->channels_count; index++) {
        cJSON *channel_json = cJSON_CreateObject();
        const channel_def_t *channel = &node->channels[index];

        if (!channel_json) {
            continue;
        }

        cJSON_AddStringToObject(channel_json, "name", channel->name);
        cJSON_AddStringToObject(channel_json, "type", channel->type);

        if (channel->is_actuator) {
            cJSON *safe_limits = cJSON_CreateObject();
            const char *actuator_type = resolve_actuator_type(channel->name);
            cJSON_AddStringToObject(channel_json, "actuator_type", actuator_type);
            if (actuator_type_requires_relay_type(actuator_type)) {
                cJSON_AddStringToObject(
                    channel_json,
                    "relay_type",
                    resolve_relay_type_for_channel(channel->name)
                );
            }
            if (safe_limits) {
                cJSON_AddNumberToObject(safe_limits, "max_duration_ms", 10000);
                cJSON_AddNumberToObject(safe_limits, "min_off_ms", 1000);
                cJSON_AddStringToObject(safe_limits, "fail_safe_mode", "NO");
                cJSON_AddItemToObject(channel_json, "safe_limits", safe_limits);
            }
        } else {
            cJSON_AddStringToObject(channel_json, "metric", channel->metric ? channel->metric : "UNKNOWN");
            cJSON_AddNumberToObject(channel_json, "poll_interval_ms", TELEMETRY_INTERVAL_MS);
        }

        cJSON_AddItemToArray(channels, channel_json);
    }

    cJSON_AddItemToObject(json, "channels", channels);

    cJSON *wifi = cJSON_CreateObject();
    if (wifi) {
        cJSON_AddBoolToObject(wifi, "configured", !node_preconfig_mode);
        cJSON_AddItemToObject(json, "wifi", wifi);
    }

    cJSON *mqtt = cJSON_CreateObject();
    if (mqtt) {
        cJSON_AddBoolToObject(mqtt, "configured", true);
        cJSON_AddItemToObject(json, "mqtt", mqtt);
    }

    payload_buf = (char *)malloc(payload_buf_size);
    publish_err = ESP_FAIL;
    for (int attempt = 0; attempt < 2; attempt++) {
        if (payload_buf) {
            publish_err = publish_json_payload_preallocated(
                topic,
                json,
                1,
                0,
                payload_buf,
                payload_buf_size
            );
        } else {
            publish_err = publish_json_payload(topic, json, 1, 0);
        }
        if (publish_err == ESP_OK) {
            break;
        }
        if (!mqtt_manager_is_connected()) {
            break;
        }
        vTaskDelay(pdMS_TO_TICKS(CONFIG_REPORT_RETRY_DELAY_MS));
    }
    if (publish_err != ESP_OK) {
        s_config_report_on_connect_pending = true;
        if (mqtt_manager_is_connected()) {
            ui_logf(node->node_uid, "cfg_report err=%s", esp_err_to_name(publish_err));
            ESP_LOGW(
                TAG,
                "config_report publish failed: node=%s channels=%u err=%s",
                node->node_uid,
                (unsigned)node->channels_count,
                esp_err_to_name(publish_err)
            );
        } else {
            ESP_LOGW(
                TAG,
                "config_report skipped due to disconnect: node=%s channels=%u err=%s",
                node->node_uid,
                (unsigned)node->channels_count,
                esp_err_to_name(publish_err)
            );
        }
    } else {
        test_node_ui_set_node_zone(node->node_uid, zone_uid);
        ui_logf(node->node_uid, "cfg_report ch=%u", (unsigned)node->channels_count);
        ESP_LOGI(
            TAG,
            "config_report published: node=%s channels=%u",
            node->node_uid,
            (unsigned)node->channels_count
        );
    }

    if (payload_buf) {
        free(payload_buf);
    }
    cJSON_Delete(json);
    return publish_err;
}

static bool publish_all_config_reports(const char *reason) {
    size_t index;
    const char *source = reason ? reason : "unknown";
    bool all_published = true;

    if (!mqtt_manager_is_connected()) {
        return false;
    }

    for (index = 0; index < (sizeof(VIRTUAL_NODES) / sizeof(VIRTUAL_NODES[0])); index++) {
        esp_err_t report_err = publish_config_report_for_node(&VIRTUAL_NODES[index]);
        if (report_err != ESP_OK) {
            all_published = false;
        }
        if (!mqtt_manager_is_connected()) {
            all_published = false;
            break;
        }
        if ((index + 1) < (sizeof(VIRTUAL_NODES) / sizeof(VIRTUAL_NODES[0]))) {
            vTaskDelay(pdMS_TO_TICKS(CONFIG_REPORT_NODE_SPACING_MS));
        }
    }

    if (all_published) {
        ESP_LOGI(TAG, "config_report batch published for all virtual nodes (reason=%s)", source);
    } else {
        ESP_LOGW(TAG, "config_report batch incomplete (reason=%s), will retry", source);
    }
    return all_published;
}

static const char *resolve_node_hello_type(const virtual_node_t *node) {
    if (!node || !node->node_type || node->node_type[0] == '\0') {
        return "unknown";
    }
    return node->node_type;
}

static const char *resolve_node_hello_name(const virtual_node_t *node) {
    if (!node || !node->node_uid) {
        return "Test Node";
    }

    if (strstr(node->node_uid, "-irrig-") != NULL) {
        return "Test: irrigation";
    }
    if (strstr(node->node_uid, "-ph-") != NULL) {
        return "Test: pH correction";
    }
    if (strstr(node->node_uid, "-ec-") != NULL) {
        return "Test: EC correction";
    }
    if (strstr(node->node_uid, "-climate-") != NULL) {
        return "Test: climate";
    }
    if (strstr(node->node_uid, "-light-") != NULL) {
        return "Test: light";
    }

    return "Test node";
}

static void publish_node_hello_for_node(const virtual_node_t *node) {
    char payload_buf[1024];
    cJSON *hello;
    cJSON *capabilities;
    cJSON *provisioning_meta;
    size_t index;

    if (!node || !node->node_uid) {
        return;
    }

    hello = cJSON_CreateObject();
    if (!hello) {
        return;
    }

    cJSON_AddStringToObject(hello, "message_type", "node_hello");
    cJSON_AddStringToObject(hello, "hardware_id", node->node_uid);
    cJSON_AddStringToObject(hello, "node_type", resolve_node_hello_type(node));
    cJSON_AddStringToObject(hello, "fw_version", PROJECT_VER);
    cJSON_AddStringToObject(hello, "hardware_revision", "esp32-devkit");

    capabilities = cJSON_CreateArray();
    if (capabilities) {
        for (index = 0; index < node->channels_count; index++) {
            cJSON_AddItemToArray(capabilities, cJSON_CreateString(node->channels[index].name));
        }
        cJSON_AddItemToObject(hello, "capabilities", capabilities);
    }

    provisioning_meta = cJSON_CreateObject();
    if (provisioning_meta) {
        cJSON_AddStringToObject(provisioning_meta, "node_uid", node->node_uid);
        cJSON_AddStringToObject(provisioning_meta, "node_name", resolve_node_hello_name(node));
        cJSON_AddBoolToObject(provisioning_meta, "virtual", true);
        cJSON_AddStringToObject(provisioning_meta, "sim_group", "test_node_multi_v1");
        cJSON_AddItemToObject(hello, "provisioning_meta", provisioning_meta);
    }

    esp_err_t publish_err = ESP_FAIL;
    for (int attempt = 0; attempt < 3; attempt++) {
        publish_err = publish_json_payload_preallocated(
            "hydro/node_hello",
            hello,
            1,
            0,
            payload_buf,
            sizeof(payload_buf)
        );
        if (publish_err == ESP_OK) {
            break;
        }
        if (!mqtt_manager_is_connected()) {
            break;
        }
        vTaskDelay(pdMS_TO_TICKS(30));
    }

    if (publish_err != ESP_OK) {
        if (mqtt_manager_is_connected()) {
            ui_logf(node->node_uid, "node_hello publish FAIL");
            ESP_LOGW(
                TAG,
                "Failed to publish node_hello for %s: err=0x%x (%s)",
                node->node_uid,
                (unsigned)publish_err,
                esp_err_to_name(publish_err)
            );
        } else {
            ESP_LOGW(
                TAG,
                "node_hello skipped due to disconnect for %s: err=0x%x (%s)",
                node->node_uid,
                (unsigned)publish_err,
                esp_err_to_name(publish_err)
            );
        }
    } else {
        ui_logf(node->node_uid, "node_hello sent");
        ESP_LOGI(TAG, "node_hello published for virtual node: %s", node->node_uid);
    }

    cJSON_Delete(hello);
}

static bool parse_command_topic(
    const char *topic,
    char *out_gh_uid,
    size_t out_gh_uid_size,
    char *out_zone_uid,
    size_t out_zone_uid_size,
    char *out_node_uid,
    size_t out_node_uid_size,
    char *out_channel,
    size_t out_channel_size
) {
    char topic_copy[192];
    char *saveptr = NULL;
    char *token;
    int segment = 0;
    const char *prefix = NULL;
    const char *gh_uid = NULL;
    const char *zone_uid = NULL;
    const char *node = NULL;
    const char *channel = NULL;
    const char *message_type = NULL;

    if (!topic || !out_gh_uid || !out_zone_uid || !out_node_uid || !out_channel) {
        return false;
    }

    if (strlen(topic) >= sizeof(topic_copy)) {
        return false;
    }

    strcpy(topic_copy, topic);
    token = strtok_r(topic_copy, "/", &saveptr);
    while (token) {
        if (segment == 0) {
            prefix = token;
        } else if (segment == 1) {
            gh_uid = token;
        } else if (segment == 2) {
            zone_uid = token;
        } else if (segment == 3) {
            node = token;
        } else if (segment == 4) {
            channel = token;
        } else if (segment == 5) {
            message_type = token;
        }
        segment++;
        token = strtok_r(NULL, "/", &saveptr);
    }

    if (segment != 6) {
        return false;
    }
    if (!prefix || strcmp(prefix, "hydro") != 0) {
        return false;
    }
    if (!gh_uid || !zone_uid || !node || !channel || !message_type) {
        return false;
    }
    if (strcmp(message_type, "command") != 0) {
        return false;
    }

    snprintf(out_gh_uid, out_gh_uid_size, "%s", gh_uid);
    snprintf(out_zone_uid, out_zone_uid_size, "%s", zone_uid);
    snprintf(out_node_uid, out_node_uid_size, "%s", node);
    snprintf(out_channel, out_channel_size, "%s", channel);
    return true;
}

static bool is_hex_signature_64(const char *sig) {
    size_t index;

    if (!sig || strlen(sig) != 64) {
        return false;
    }

    for (index = 0; index < 64; index++) {
        unsigned char ch = (unsigned char)sig[index];
        if (!isxdigit(ch)) {
            return false;
        }
    }
    return true;
}

static bool has_only_canonical_command_fields(const cJSON *command_json) {
    const cJSON *child;

    if (!command_json) {
        return false;
    }

    for (child = command_json->child; child; child = child->next) {
        const char *key = child->string;
        if (!key) {
            continue;
        }
        if (
            strcmp(key, "cmd_id") != 0 &&
            strcmp(key, "cmd") != 0 &&
            strcmp(key, "params") != 0 &&
            strcmp(key, "ts") != 0 &&
            strcmp(key, "sig") != 0
        ) {
            return false;
        }
    }

    return true;
}

static bool validate_command_payload_strict(
    cJSON *command_json,
    const char **out_error_code,
    const char **out_error_message
) {
    cJSON *cmd_id_item;
    cJSON *cmd_item;
    cJSON *params_item;
    cJSON *ts_item;
    cJSON *sig_item;
    double ts_raw;
    int64_t ts_int;
    const char *sig;

    if (out_error_code) {
        *out_error_code = "invalid_command_format";
    }
    if (out_error_message) {
        *out_error_message = "Invalid command payload";
    }

    if (!command_json || !cJSON_IsObject(command_json)) {
        if (out_error_message) {
            *out_error_message = "Command payload must be JSON object";
        }
        return false;
    }

    if (!has_only_canonical_command_fields(command_json)) {
        if (out_error_message) {
            *out_error_message = "Unknown fields in command payload";
        }
        return false;
    }

    cmd_id_item = cJSON_GetObjectItem(command_json, "cmd_id");
    cmd_item = cJSON_GetObjectItem(command_json, "cmd");
    params_item = cJSON_GetObjectItem(command_json, "params");
    ts_item = cJSON_GetObjectItem(command_json, "ts");
    sig_item = cJSON_GetObjectItem(command_json, "sig");

    if (!(cmd_id_item && cJSON_IsString(cmd_id_item) && cmd_id_item->valuestring && cmd_id_item->valuestring[0] != '\0')) {
        if (out_error_message) {
            *out_error_message = "Missing or invalid cmd_id";
        }
        return false;
    }

    if (!(cmd_item && cJSON_IsString(cmd_item) && cmd_item->valuestring && cmd_item->valuestring[0] != '\0')) {
        if (out_error_message) {
            *out_error_message = "Missing or invalid cmd";
        }
        return false;
    }

    if (!(params_item && cJSON_IsObject(params_item))) {
        if (out_error_message) {
            *out_error_message = "Missing or invalid params";
        }
        return false;
    }

    if (!(ts_item && cJSON_IsNumber(ts_item))) {
        if (out_error_code) {
            *out_error_code = "invalid_hmac_format";
        }
        if (out_error_message) {
            *out_error_message = "Missing or invalid ts";
        }
        return false;
    }

    ts_raw = cJSON_GetNumberValue(ts_item);
    ts_int = (int64_t)ts_raw;
    if (ts_raw < 0 || (double)ts_int != ts_raw) {
        if (out_error_code) {
            *out_error_code = "invalid_hmac_format";
        }
        if (out_error_message) {
            *out_error_message = "ts must be non-negative integer";
        }
        return false;
    }

    if (!(sig_item && cJSON_IsString(sig_item) && sig_item->valuestring)) {
        if (out_error_code) {
            *out_error_code = "invalid_hmac_format";
        }
        if (out_error_message) {
            *out_error_message = "Missing or invalid sig";
        }
        return false;
    }

    sig = sig_item->valuestring;
    if (!is_hex_signature_64(sig)) {
        if (out_error_code) {
            *out_error_code = "invalid_hmac_format";
        }
        if (out_error_message) {
            *out_error_message = "sig must be 64-char hex string";
        }
        return false;
    }

    return true;
}

static void publish_command_response(
    const char *node_uid,
    const char *channel,
    const char *cmd_id,
    const char *status,
    cJSON *details
) {
    char topic[192];
    cJSON *json = cJSON_CreateObject();
    esp_err_t publish_err = ESP_FAIL;
    int attempts = 1;
    if (!json) {
        return;
    }

    cJSON_AddStringToObject(json, "cmd_id", cmd_id);
    cJSON_AddStringToObject(json, "status", status);
    cJSON_AddNumberToObject(json, "ts", (double)get_timestamp_ms());
    if (details) {
        cJSON_AddItemToObject(json, "details", cJSON_Duplicate(details, 1));
    }

    if (build_topic(topic, sizeof(topic), node_uid, channel, "command_response") == ESP_OK) {
        if (status && strcmp(status, "ACK") != 0) {
            attempts = 4;
        }
        for (int i = 0; i < attempts; i++) {
            publish_err = publish_json_payload(topic, json, 1, 0);
            if (publish_err == ESP_OK) {
                break;
            }
            vTaskDelay(pdMS_TO_TICKS(80));
        }
        if (publish_err == ESP_OK) {
            ui_logf(node_uid, "cmd_resp %s %s", status ? status : "?", channel ? channel : "-");
        } else {
            ESP_LOGW(
                CMD_TAG,
                "command_response publish failed: node=%s channel=%s cmd_id=%s status=%s err=%s",
                node_uid ? node_uid : "unknown",
                channel ? channel : "unknown",
                cmd_id ? cmd_id : "unknown",
                status ? status : "unknown",
                esp_err_to_name(publish_err)
            );
        }
    } else {
        ESP_LOGE(TAG, "Failed to build command_response topic for %s/%s", node_uid, channel);
    }

    cJSON_Delete(json);
}

static cJSON *build_sensor_probe_details(const char *channel) {
    cJSON *details = cJSON_CreateObject();
    if (!details) {
        return NULL;
    }

    if (strcmp(channel, "ph_sensor") == 0) {
        cJSON_AddStringToObject(details, "metric_type", "PH");
        cJSON_AddNumberToObject(details, "value", s_virtual_state.ph_value);
        cJSON_AddStringToObject(details, "unit", "pH");
    } else if (strcmp(channel, "ec_sensor") == 0) {
        cJSON_AddStringToObject(details, "metric_type", "EC");
        cJSON_AddNumberToObject(details, "value", s_virtual_state.ec_value);
        cJSON_AddStringToObject(details, "unit", "mS/cm");
    } else if (strcmp(channel, "air_temp_c") == 0) {
        cJSON_AddStringToObject(details, "metric_type", "TEMPERATURE");
        cJSON_AddNumberToObject(details, "value", s_virtual_state.air_temp);
        cJSON_AddStringToObject(details, "unit", "C");
    } else if (strcmp(channel, "air_rh") == 0) {
        cJSON_AddStringToObject(details, "metric_type", "HUMIDITY");
        cJSON_AddNumberToObject(details, "value", s_virtual_state.air_humidity);
        cJSON_AddStringToObject(details, "unit", "%");
    } else if (strcmp(channel, "light_level") == 0) {
        cJSON_AddStringToObject(details, "metric_type", "LIGHT_INTENSITY");
        cJSON_AddNumberToObject(details, "value", s_virtual_state.light_level);
        cJSON_AddStringToObject(details, "unit", "lux");
    } else if (strcmp(channel, "water_level") == 0) {
        cJSON_AddStringToObject(details, "metric_type", "WATER_LEVEL");
        cJSON_AddNumberToObject(details, "value", s_virtual_state.water_level);
        cJSON_AddStringToObject(details, "unit", "ratio");
    } else if (strcmp(channel, "level_clean_min") == 0) {
        cJSON_AddStringToObject(details, "metric_type", "WATER_LEVEL_SWITCH");
        cJSON_AddNumberToObject(details, "value", resolve_clean_min_switch_value());
        cJSON_AddStringToObject(details, "unit", "bool");
    } else if (strcmp(channel, "level_clean_max") == 0) {
        cJSON_AddStringToObject(details, "metric_type", "WATER_LEVEL_SWITCH");
        cJSON_AddNumberToObject(details, "value", resolve_clean_max_switch_value());
        cJSON_AddStringToObject(details, "unit", "bool");
    } else if (strcmp(channel, "level_solution_min") == 0) {
        cJSON_AddStringToObject(details, "metric_type", "WATER_LEVEL_SWITCH");
        cJSON_AddNumberToObject(details, "value", resolve_solution_min_switch_value());
        cJSON_AddStringToObject(details, "unit", "bool");
    } else if (strcmp(channel, "level_solution_max") == 0) {
        cJSON_AddStringToObject(details, "metric_type", "WATER_LEVEL_SWITCH");
        cJSON_AddNumberToObject(details, "value", resolve_solution_max_switch_value());
        cJSON_AddStringToObject(details, "unit", "bool");
    } else if (strcmp(channel, "flow_present") == 0) {
        cJSON_AddStringToObject(details, "metric_type", "FLOW_RATE");
        cJSON_AddNumberToObject(details, "value", s_virtual_state.flow_rate);
        cJSON_AddStringToObject(details, "unit", "l/min");
    } else if (strcmp(channel, "pump_bus_current") == 0) {
        cJSON_AddStringToObject(details, "metric_type", "PUMP_CURRENT");
        cJSON_AddNumberToObject(details, "value", s_virtual_state.pump_bus_current);
        cJSON_AddStringToObject(details, "unit", "mA");
    } else {
        cJSON_AddStringToObject(details, "metric_type", "UNKNOWN");
        cJSON_AddNumberToObject(details, "value", 0);
    }

    cJSON_AddBoolToObject(details, "virtual", true);
    cJSON_AddNumberToObject(details, "ts", (double)get_timestamp_seconds());
    return details;
}

static cJSON *build_irr_state_snapshot(void) {
    cJSON *snapshot = cJSON_CreateObject();
    if (!snapshot) {
        return NULL;
    }

    cJSON_AddBoolToObject(snapshot, "clean_level_max", resolve_clean_max_switch_value() >= 0.5f);
    cJSON_AddBoolToObject(snapshot, "clean_level_min", resolve_clean_min_switch_value() >= 0.5f);
    cJSON_AddBoolToObject(snapshot, "solution_level_max", resolve_solution_max_switch_value() >= 0.5f);
    cJSON_AddBoolToObject(snapshot, "solution_level_min", resolve_solution_min_switch_value() >= 0.5f);
    cJSON_AddBoolToObject(snapshot, "valve_clean_fill", s_virtual_state.valve_clean_fill_on);
    cJSON_AddBoolToObject(snapshot, "valve_clean_supply", s_virtual_state.valve_clean_supply_on);
    cJSON_AddBoolToObject(snapshot, "valve_solution_fill", s_virtual_state.valve_solution_fill_on);
    cJSON_AddBoolToObject(snapshot, "valve_solution_supply", s_virtual_state.valve_solution_supply_on);
    cJSON_AddBoolToObject(snapshot, "valve_irrigation", s_virtual_state.valve_irrigation_on);
    cJSON_AddBoolToObject(snapshot, "pump_main", s_virtual_state.main_pump_on);
    return snapshot;
}

static void publish_irrig_node_event(const char *event_code) {
    char topic[192];
    cJSON *json;
    cJSON *snapshot;

    if (!event_code || event_code[0] == '\0') {
        return;
    }
    if (!mqtt_manager_is_connected()) {
        return;
    }
    if (build_topic(topic, sizeof(topic), DEFAULT_MQTT_NODE_UID, "storage_state", "event") != ESP_OK) {
        ESP_LOGW(TAG, "Failed to build node event topic for irrig node");
        return;
    }

    json = cJSON_CreateObject();
    if (!json) {
        return;
    }

    cJSON_AddStringToObject(json, "event_code", event_code);
    cJSON_AddNumberToObject(json, "ts", (double)get_timestamp_seconds());
    snapshot = build_irr_state_snapshot();
    if (snapshot) {
        cJSON_AddItemToObject(json, "snapshot", snapshot);
    }

    publish_json_payload(topic, json, 1, 0);
    ui_logf(DEFAULT_MQTT_NODE_UID, "event %s", event_code);
    cJSON_Delete(json);
}

static int resolve_command_delay_ms(command_kind_t kind, const pending_command_t *job, cJSON *params) {
    int delay_ms = random_range_ms(CONTROL_DELAY_MIN_MS, CONTROL_DELAY_MAX_MS);
    cJSON *sim_delay_ms;
    cJSON *ttl_ms;

    if (params && cJSON_IsObject(params)) {
        sim_delay_ms = cJSON_GetObjectItem(params, "sim_delay_ms");
        if (sim_delay_ms && cJSON_IsNumber(sim_delay_ms)) {
            delay_ms = (int)cJSON_GetNumberValue(sim_delay_ms);
            if (delay_ms < 50) {
                delay_ms = 50;
            }
            if (delay_ms > 20000) {
                delay_ms = 20000;
            }
            return delay_ms;
        }
    }

    if (kind == COMMAND_KIND_SENSOR_PROBE || kind == COMMAND_KIND_STATE_QUERY) {
        return random_range_ms(180, 480);
    }
    if (kind == COMMAND_KIND_CONFIG_REPORT) {
        return random_range_ms(120, 320);
    }
    if (kind == COMMAND_KIND_RESTART) {
        return random_range_ms(1200, 2200);
    }
    if (kind == COMMAND_KIND_ACTUATOR && (!job || !is_transient_command(job))) {
        if (params && cJSON_IsObject(params)) {
            ttl_ms = cJSON_GetObjectItem(params, "ttl_ms");
            if (ttl_ms && cJSON_IsNumber(ttl_ms)) {
                delay_ms = (int)cJSON_GetNumberValue(ttl_ms);
                if (delay_ms < CONTROL_DELAY_MIN_MS) {
                    delay_ms = CONTROL_DELAY_MIN_MS;
                }
                if (delay_ms > 4000) {
                    delay_ms = 4000;
                }
                return delay_ms;
            }
        }
        return delay_ms;
    }

    if (job && kind == COMMAND_KIND_ACTUATOR && is_transient_command(job)) {
        int base_ms = random_range_ms(TRANSIENT_DELAY_BASE_MIN_MS, TRANSIENT_DELAY_BASE_MAX_MS);
        int duration_ms = job->duration_ms_present ? job->duration_ms : 0;
        if (duration_ms <= 0 && job->amount_present && job->amount_value > 0.0f) {
            duration_ms = (int)(job->amount_value * 120.0f);
        }
        if (duration_ms > 0) {
            int scaled_ms = (duration_ms * TRANSIENT_DELAY_SCALE_PERCENT) / 100;
            if (scaled_ms < TRANSIENT_DELAY_SCALE_MIN_MS) {
                scaled_ms = TRANSIENT_DELAY_SCALE_MIN_MS;
            }
            if (scaled_ms > TRANSIENT_DELAY_SCALE_MAX_MS) {
                scaled_ms = TRANSIENT_DELAY_SCALE_MAX_MS;
            }
            return base_ms + scaled_ms;
        }
        return base_ms + random_range_ms(TRANSIENT_DELAY_EXTRA_MIN_MS, TRANSIENT_DELAY_EXTRA_MAX_MS);
    }

    if (params && cJSON_IsObject(params)) {
        ttl_ms = cJSON_GetObjectItem(params, "ttl_ms");
        if (ttl_ms && cJSON_IsNumber(ttl_ms)) {
            delay_ms = (int)cJSON_GetNumberValue(ttl_ms);
        }
    }

    if (delay_ms < 150) {
        delay_ms = 150;
    }
    if (delay_ms > 8000) {
        delay_ms = 8000;
    }
    return delay_ms;
}

static bool is_sensor_calibration_channel(const char *channel) {
    if (!channel) {
        return false;
    }
    return strcmp(channel, "ph_sensor") == 0 || strcmp(channel, "ec_sensor") == 0;
}

static bool is_unsupported_sensor_calibration_command(const pending_command_t *job) {
    if (!job || !is_sensor_calibration_channel(job->channel)) {
        return false;
    }
    return strcmp(job->cmd, "calibrate") == 0;
}

static void extract_command_params(cJSON *command_json, pending_command_t *job) {
    cJSON *params;

    if (!command_json || !job) {
        return;
    }

    params = cJSON_GetObjectItem(command_json, "params");
    if (!params || !cJSON_IsObject(params)) {
        return;
    }

    cJSON *state = cJSON_GetObjectItem(params, "state");
    if (state && (cJSON_IsBool(state) || cJSON_IsNumber(state))) {
        job->relay_state_present = true;
        if (cJSON_IsBool(state)) {
            job->relay_state = cJSON_IsTrue(state);
        } else {
            job->relay_state = cJSON_GetNumberValue(state) > 0;
        }
    }

    cJSON *pwm = cJSON_GetObjectItem(params, "value");
    if (pwm && cJSON_IsNumber(pwm)) {
        job->pwm_value_present = true;
        job->pwm_value = (int)cJSON_GetNumberValue(pwm);
    }

    cJSON *ml = cJSON_GetObjectItem(params, "ml");
    if (ml && cJSON_IsNumber(ml)) {
        job->amount_present = true;
        job->amount_value = (float)cJSON_GetNumberValue(ml);
    }

    cJSON *duration = cJSON_GetObjectItem(params, "duration_ms");
    if (duration && cJSON_IsNumber(duration)) {
        job->duration_ms_present = true;
        job->duration_ms = (int)cJSON_GetNumberValue(duration);
    }

    cJSON *sim_status = cJSON_GetObjectItem(params, "sim_status");
    if (sim_status && cJSON_IsString(sim_status) && sim_status->valuestring) {
        size_t idx;
        size_t max_len = sizeof(job->sim_status) - 1;
        size_t src_len = strlen(sim_status->valuestring);
        if (src_len > max_len) {
            src_len = max_len;
        }
        for (idx = 0; idx < src_len; idx++) {
            job->sim_status[idx] = (char)toupper((unsigned char)sim_status->valuestring[idx]);
        }
        job->sim_status[src_len] = '\0';
        if (is_valid_terminal_status(job->sim_status)) {
            job->sim_status_present = true;
        }
    }

    cJSON *sim_no_effect = cJSON_GetObjectItem(params, "sim_no_effect");
    if (sim_no_effect && cJSON_IsBool(sim_no_effect)) {
        job->sim_no_effect = cJSON_IsTrue(sim_no_effect);
    }

    cJSON *event_code = cJSON_GetObjectItem(params, "event_code");
    if (event_code && cJSON_IsString(event_code) && event_code->valuestring && event_code->valuestring[0] != '\0') {
        size_t max_len = sizeof(job->event_code) - 1;
        size_t src_len = strlen(event_code->valuestring);
        if (src_len > max_len) {
            src_len = max_len;
        }
        memcpy(job->event_code, event_code->valuestring, src_len);
        job->event_code[src_len] = '\0';
        job->event_code_present = true;
    }

    cJSON *sensor_conflict_clean = cJSON_GetObjectItem(params, "sensor_conflict_clean");
    if (sensor_conflict_clean && (cJSON_IsBool(sensor_conflict_clean) || cJSON_IsNumber(sensor_conflict_clean))) {
        job->clean_sensor_conflict_present = true;
        if (cJSON_IsBool(sensor_conflict_clean)) {
            job->clean_sensor_conflict = cJSON_IsTrue(sensor_conflict_clean);
        } else {
            job->clean_sensor_conflict = cJSON_GetNumberValue(sensor_conflict_clean) > 0;
        }
    }

    cJSON *sensor_conflict_solution = cJSON_GetObjectItem(params, "sensor_conflict_solution");
    if (sensor_conflict_solution && (cJSON_IsBool(sensor_conflict_solution) || cJSON_IsNumber(sensor_conflict_solution))) {
        job->solution_sensor_conflict_present = true;
        if (cJSON_IsBool(sensor_conflict_solution)) {
            job->solution_sensor_conflict = cJSON_IsTrue(sensor_conflict_solution);
        } else {
            job->solution_sensor_conflict = cJSON_GetNumberValue(sensor_conflict_solution) > 0;
        }
    }

    cJSON *clean_timeout_mode = cJSON_GetObjectItem(params, "clean_fill_timeout_mode");
    if (clean_timeout_mode && (cJSON_IsBool(clean_timeout_mode) || cJSON_IsNumber(clean_timeout_mode))) {
        job->clean_fill_timeout_present = true;
        if (cJSON_IsBool(clean_timeout_mode)) {
            job->clean_fill_timeout = cJSON_IsTrue(clean_timeout_mode);
        } else {
            job->clean_fill_timeout = cJSON_GetNumberValue(clean_timeout_mode) > 0;
        }
    }

    cJSON *solution_timeout_mode = cJSON_GetObjectItem(params, "solution_fill_timeout_mode");
    if (solution_timeout_mode && (cJSON_IsBool(solution_timeout_mode) || cJSON_IsNumber(solution_timeout_mode))) {
        job->solution_fill_timeout_present = true;
        if (cJSON_IsBool(solution_timeout_mode)) {
            job->solution_fill_timeout = cJSON_IsTrue(solution_timeout_mode);
        } else {
            job->solution_fill_timeout = cJSON_GetNumberValue(solution_timeout_mode) > 0;
        }
    }

    cJSON *level_clean_min_override = cJSON_GetObjectItem(params, "level_clean_min_override");
    if (parse_switch_override_param(level_clean_min_override, &job->level_clean_min_override)) {
        job->level_clean_min_override_present = true;
    }

    cJSON *level_clean_max_override = cJSON_GetObjectItem(params, "level_clean_max_override");
    if (parse_switch_override_param(level_clean_max_override, &job->level_clean_max_override)) {
        job->level_clean_max_override_present = true;
    }

    cJSON *level_solution_min_override = cJSON_GetObjectItem(params, "level_solution_min_override");
    if (parse_switch_override_param(level_solution_min_override, &job->level_solution_min_override)) {
        job->level_solution_min_override_present = true;
    }

    cJSON *level_solution_max_override = cJSON_GetObjectItem(params, "level_solution_max_override");
    if (parse_switch_override_param(level_solution_max_override, &job->level_solution_max_override)) {
        job->level_solution_max_override_present = true;
    }

    cJSON *ph_value = cJSON_GetObjectItem(params, "ph_value");
    if (ph_value && cJSON_IsNumber(ph_value)) {
        job->ph_value_present = true;
        job->ph_value = (float)cJSON_GetNumberValue(ph_value);
    }

    cJSON *ec_value = cJSON_GetObjectItem(params, "ec_value");
    if (ec_value && cJSON_IsNumber(ec_value)) {
        job->ec_value_present = true;
        job->ec_value = (float)cJSON_GetNumberValue(ec_value);
    }

    job->execute_delay_ms = resolve_command_delay_ms(job->kind, job, params);
}

static void update_virtual_state_from_command(const pending_command_t *job, cJSON *details, const char **status_out) {
    const char *status = "DONE";
    bool handled = false;
    bool was_solution_fill_active = is_solution_fill_active();

    if (!job || !status_out) {
        return;
    }

    if (job->sim_status_present) {
        if (strcmp(job->sim_status, "DONE") != 0) {
            if (strcmp(job->sim_status, "NO_EFFECT") == 0) {
                cJSON_AddStringToObject(details, "note", "simulated_no_effect_ignored");
            } else {
                cJSON_AddStringToObject(details, "error", "simulated_terminal_status");
                cJSON_AddStringToObject(details, "error_code", job->sim_status);
                *status_out = job->sim_status;
                return;
            }
        }
    }
    if (job->sim_no_effect) {
        cJSON_AddStringToObject(details, "note", "sim_no_effect_ignored");
    }

    if (strcmp(job->cmd, "set_relay") == 0 && !job->relay_state_present) {
        cJSON_AddStringToObject(details, "error", "missing_state");
        status = "INVALID";
        *status_out = status;
        return;
    }

    if (strcmp(job->cmd, "set_pwm") == 0 && !job->pwm_value_present) {
        cJSON_AddStringToObject(details, "error", "missing_pwm_value");
        status = "INVALID";
        *status_out = status;
        return;
    }

    if (strcmp(job->cmd, "set_relay") == 0) {
        bool has_state = true;
        bool current_state = false;

        if (strcmp(job->channel, "pump_irrigation") == 0) {
            current_state = s_virtual_state.irrigation_on;
        } else if (is_main_pump_channel(job->channel)) {
            current_state = s_virtual_state.main_pump_on;
        } else if (strcmp(job->channel, "valve_clean_fill") == 0) {
            current_state = s_virtual_state.valve_clean_fill_on;
        } else if (strcmp(job->channel, "valve_clean_supply") == 0) {
            current_state = s_virtual_state.valve_clean_supply_on;
        } else if (strcmp(job->channel, "valve_solution_fill") == 0) {
            current_state = s_virtual_state.valve_solution_fill_on;
        } else if (strcmp(job->channel, "valve_solution_supply") == 0) {
            current_state = s_virtual_state.valve_solution_supply_on;
        } else if (strcmp(job->channel, "valve_irrigation") == 0) {
            current_state = s_virtual_state.valve_irrigation_on;
        } else if (is_fill_channel(job->channel)) {
            current_state = s_virtual_state.tank_fill_on;
        } else if (is_drain_channel(job->channel)) {
            current_state = s_virtual_state.tank_drain_on;
        } else if (strcmp(job->channel, "fan_air") == 0 || strcmp(job->channel, "fan") == 0) {
            current_state = s_virtual_state.fan_on;
        } else if (strcmp(job->channel, "heater") == 0) {
            current_state = s_virtual_state.heater_on;
        } else if (strcmp(job->channel, "white_light") == 0) {
            current_state = s_virtual_state.light_on;
        } else {
            has_state = false;
        }

        if (has_state && current_state == job->relay_state) {
            cJSON_AddStringToObject(details, "note", "already_in_requested_state_treated_as_done");
        }

    }

    if (strcmp(job->channel, "white_light") == 0 && strcmp(job->cmd, "set_pwm") == 0) {
        int pwm_value = job->pwm_value;
        if (pwm_value < 0) {
            pwm_value = 0;
        }
        if (pwm_value > 255) {
            pwm_value = 255;
        }
        if ((int)s_virtual_state.light_pwm == pwm_value) {
            cJSON_AddStringToObject(details, "note", "already_in_requested_pwm_treated_as_done");
        }
    }

    if (is_ph_correction_channel(job->channel) && !s_virtual_state.ph_sensor_mode_active) {
        cJSON_AddStringToObject(details, "error", "node_not_activated");
        cJSON_AddStringToObject(details, "error_code", "node_not_activated");
        cJSON_AddStringToObject(details, "error_message", "node is not activated");
        *status_out = "ERROR";
        return;
    }

    if (is_ec_correction_channel(job->channel) && !s_virtual_state.ec_sensor_mode_active) {
        cJSON_AddStringToObject(details, "error", "node_not_activated");
        cJSON_AddStringToObject(details, "error_code", "node_not_activated");
        cJSON_AddStringToObject(details, "error_message", "node is not activated");
        *status_out = "ERROR";
        return;
    }

    if (strcmp(job->channel, "pump_irrigation") == 0) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            s_virtual_state.irrigation_on = job->relay_state;
            handled = true;
        } else if (strcmp(job->cmd, "run_pump") == 0 || strcmp(job->cmd, "dose") == 0) {
            s_virtual_state.irrigation_boost_ticks = 3;
            handled = true;
        }
    } else if (is_main_pump_channel(job->channel)) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            if (job->relay_state && !is_main_pump_interlock_satisfied()) {
                append_main_pump_interlock_error(details);
                *status_out = "ERROR";
                return;
            }
            s_virtual_state.main_pump_on = job->relay_state;
            handled = true;
        } else if (strcmp(job->cmd, "run_pump") == 0 || strcmp(job->cmd, "dose") == 0) {
            if (!is_main_pump_interlock_satisfied()) {
                append_main_pump_interlock_error(details);
                *status_out = "ERROR";
                return;
            }
            handled = true;
        }
    } else if (strcmp(job->channel, "valve_clean_fill") == 0) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            bool was_on = s_virtual_state.valve_clean_fill_on;
            s_virtual_state.valve_clean_fill_on = job->relay_state;
            handled = true;
            if (!was_on && job->relay_state) {
                s_virtual_state.clean_fill_stage_active = true;
                s_virtual_state.clean_fill_started_at = get_timestamp_seconds();
                ui_logf(
                    job->node_uid,
                    "cmd delay clean_fill start %ds",
                    CLEAN_FILL_DELAY_SEC
                );
            } else if (was_on && !job->relay_state) {
                if (s_virtual_state.clean_fill_stage_active && !s_virtual_state.clean_max_latched) {
                    ui_logf(
                        job->node_uid,
                        "cmd delay clean_fill cancel"
                    );
                }
                s_virtual_state.clean_fill_stage_active = false;
                s_virtual_state.clean_fill_started_at = 0;
            }
        }
    } else if (strcmp(job->channel, "valve_clean_supply") == 0) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            s_virtual_state.valve_clean_supply_on = job->relay_state;
            handled = true;
        }
    } else if (strcmp(job->channel, "valve_solution_fill") == 0) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            s_virtual_state.valve_solution_fill_on = job->relay_state;
            handled = true;
        }
    } else if (strcmp(job->channel, "valve_solution_supply") == 0) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            s_virtual_state.valve_solution_supply_on = job->relay_state;
            handled = true;
        }
    } else if (strcmp(job->channel, "valve_irrigation") == 0) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            s_virtual_state.valve_irrigation_on = job->relay_state;
            handled = true;
        }
    } else if (is_fill_channel(job->channel)) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            s_virtual_state.tank_fill_on = job->relay_state;
            handled = true;
        } else if (strcmp(job->cmd, "run_pump") == 0 || strcmp(job->cmd, "dose") == 0) {
            s_virtual_state.water_level = clamp_float(s_virtual_state.water_level + 0.02f, 0.05f, 0.98f);
            handled = true;
        }
    } else if (is_drain_channel(job->channel)) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            s_virtual_state.tank_drain_on = job->relay_state;
            handled = true;
        } else if (strcmp(job->cmd, "run_pump") == 0 || strcmp(job->cmd, "dose") == 0) {
            s_virtual_state.solution_level = clamp_float(s_virtual_state.solution_level - 0.02f, 0.05f, 0.98f);
            handled = true;
        }
    } else if (strcmp(job->channel, "pump_acid") == 0) {
        float scale = resolve_correction_reaction_scale(job, PH_REACTION_NOMINAL_ML);
        float phase_factor = resolve_correction_phase_factor(false);
        float delta = PH_REACTION_BASE_DELTA * scale * phase_factor;
        float projected_peak = clamp_float(
            s_virtual_state.ph_value + s_virtual_state.pending_ph_delta - delta,
            4.8f,
            7.2f
        );
        schedule_correction_response(false, -delta);
        cJSON_AddNumberToObject(details, "phase_factor", phase_factor);
        cJSON_AddNumberToObject(details, "delta_ph", -delta);
        cJSON_AddNumberToObject(details, "ph_after", projected_peak);
        cJSON_AddNumberToObject(details, "effect_delay_sec", (float)TELEMETRY_INTERVAL_MS * CORRECTION_RESPONSE_DELAY_TICKS / 1000.0f);
        cJSON_AddNumberToObject(details, "effect_decay_sec", (float)TELEMETRY_INTERVAL_MS * CORRECTION_DECAY_TICKS / 1000.0f);
        handled = true;
    } else if (strcmp(job->channel, "pump_base") == 0) {
        float scale = resolve_correction_reaction_scale(job, PH_REACTION_NOMINAL_ML);
        float phase_factor = resolve_correction_phase_factor(false);
        float delta = PH_REACTION_BASE_DELTA * scale * phase_factor;
        float projected_peak = clamp_float(
            s_virtual_state.ph_value + s_virtual_state.pending_ph_delta + delta,
            4.8f,
            7.2f
        );
        schedule_correction_response(false, delta);
        cJSON_AddNumberToObject(details, "phase_factor", phase_factor);
        cJSON_AddNumberToObject(details, "delta_ph", delta);
        cJSON_AddNumberToObject(details, "ph_after", projected_peak);
        cJSON_AddNumberToObject(details, "effect_delay_sec", (float)TELEMETRY_INTERVAL_MS * CORRECTION_RESPONSE_DELAY_TICKS / 1000.0f);
        cJSON_AddNumberToObject(details, "effect_decay_sec", (float)TELEMETRY_INTERVAL_MS * CORRECTION_DECAY_TICKS / 1000.0f);
        handled = true;
    } else if (
        strcmp(job->channel, "pump_a") == 0 ||
        strcmp(job->channel, "pump_b") == 0 ||
        strcmp(job->channel, "pump_c") == 0 ||
        strcmp(job->channel, "pump_d") == 0
    ) {
        float scale = resolve_correction_reaction_scale(job, EC_REACTION_NOMINAL_ML);
        float phase_factor = resolve_correction_phase_factor(true);
        float delta = EC_REACTION_BASE_DELTA * scale * phase_factor;
        float projected_peak = clamp_float(
            s_virtual_state.ec_value + s_virtual_state.pending_ec_delta + delta,
            0.4f,
            3.2f
        );
        schedule_correction_response(true, delta);
        cJSON_AddNumberToObject(details, "phase_factor", phase_factor);
        cJSON_AddNumberToObject(details, "delta_ec", delta);
        cJSON_AddNumberToObject(details, "ec_after", projected_peak);
        cJSON_AddNumberToObject(details, "effect_delay_sec", (float)TELEMETRY_INTERVAL_MS * CORRECTION_RESPONSE_DELAY_TICKS / 1000.0f);
        cJSON_AddNumberToObject(details, "effect_decay_sec", (float)TELEMETRY_INTERVAL_MS * CORRECTION_DECAY_TICKS / 1000.0f);
        handled = true;
    } else if (strcmp(job->channel, "fan_air") == 0 || strcmp(job->channel, "fan") == 0) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            s_virtual_state.fan_on = job->relay_state;
            handled = true;
        }
    } else if (strcmp(job->channel, "heater") == 0) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            s_virtual_state.heater_on = job->relay_state;
            handled = true;
        }
    } else if (strcmp(job->channel, "white_light") == 0) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            s_virtual_state.light_on = job->relay_state;
            if (!job->relay_state) {
                s_virtual_state.light_pwm = 0;
            }
            handled = true;
        } else if (strcmp(job->cmd, "set_pwm") == 0) {
            int pwm_value = job->pwm_value;
            if (pwm_value < 0) {
                pwm_value = 0;
            }
            if (pwm_value > 255) {
                pwm_value = 255;
            }
            s_virtual_state.light_pwm = (uint8_t)pwm_value;
            s_virtual_state.light_on = pwm_value > 0;
            handled = true;
        }
    } else if (is_storage_system_channel(job->channel)) {
        if (strcmp(job->cmd, "reset_state") == 0) {
            reset_virtual_state_runtime();
            cJSON_AddStringToObject(details, "note", "virtual_state_reset");
            handled = true;
        } else if (strcmp(job->cmd, "emit_event") == 0) {
            if (!job->event_code_present || job->event_code[0] == '\0') {
                cJSON_AddStringToObject(details, "error", "missing_event_code");
                cJSON_AddStringToObject(details, "error_code", "missing_event_code");
                *status_out = "INVALID";
                return;
            }
            publish_irrig_node_event(job->event_code);
            cJSON_AddStringToObject(details, "event_code", job->event_code);
            handled = true;
        } else if (strcmp(job->cmd, "set_fault_mode") == 0) {
            bool publish_levels = false;
            bool publish_ph = false;
            bool publish_ec = false;

            if (job->clean_sensor_conflict_present) {
                s_virtual_state.force_clean_sensor_conflict = job->clean_sensor_conflict;
            }
            if (job->solution_sensor_conflict_present) {
                s_virtual_state.force_solution_sensor_conflict = job->solution_sensor_conflict;
            }
            if (job->clean_fill_timeout_present) {
                s_virtual_state.simulate_clean_fill_timeout = job->clean_fill_timeout;
            }
            if (job->solution_fill_timeout_present) {
                s_virtual_state.simulate_solution_fill_timeout = job->solution_fill_timeout;
            }
            if (job->level_clean_min_override_present) {
                s_virtual_state.level_clean_min_override = job->level_clean_min_override;
                publish_levels = true;
            }
            if (job->level_clean_max_override_present) {
                s_virtual_state.level_clean_max_override = job->level_clean_max_override;
                publish_levels = true;
            }
            if (job->level_solution_min_override_present) {
                s_virtual_state.level_solution_min_override = job->level_solution_min_override;
                publish_levels = true;
            }
            if (job->level_solution_max_override_present) {
                s_virtual_state.level_solution_max_override = job->level_solution_max_override;
                publish_levels = true;
            }
            if (job->ph_value_present) {
                clear_correction_response_state();
                s_virtual_state.ph_value = clamp_float(job->ph_value, 4.8f, 7.2f);
                publish_ph = true;
            }
            if (job->ec_value_present) {
                clear_correction_response_state();
                s_virtual_state.ec_value = clamp_float(job->ec_value, 0.4f, 3.2f);
                publish_ec = true;
            }
            if (s_virtual_state.level_clean_max_override > 0 && s_virtual_state.clean_fill_stage_active) {
                s_virtual_state.clean_fill_stage_active = false;
                s_virtual_state.clean_fill_started_at = 0;
                s_virtual_state.clean_max_latched = true;
                if (s_virtual_state.water_level < CLEAN_MAX_LATCH_LEVEL) {
                    s_virtual_state.water_level = CLEAN_MAX_LATCH_LEVEL;
                }
                publish_irrig_node_event("clean_fill_completed");
                cJSON_AddBoolToObject(details, "clean_fill_forced_complete", true);
            }
            if (s_virtual_state.level_solution_max_override > 0 && s_virtual_state.solution_fill_stage_active) {
                s_virtual_state.solution_fill_stage_active = false;
                s_virtual_state.solution_fill_started_at = 0;
                s_virtual_state.solution_max_latched = true;
                if (s_virtual_state.solution_level < SOLUTION_MAX_LATCH_LEVEL) {
                    s_virtual_state.solution_level = SOLUTION_MAX_LATCH_LEVEL;
                }
                publish_irrig_node_event("solution_fill_completed");
                cJSON_AddBoolToObject(details, "solution_fill_forced_complete", true);
            }
            publish_current_virtual_sensor_snapshot(publish_levels, publish_ph, publish_ec);
            cJSON_AddBoolToObject(details, "sensor_conflict_clean", s_virtual_state.force_clean_sensor_conflict);
            cJSON_AddBoolToObject(details, "sensor_conflict_solution", s_virtual_state.force_solution_sensor_conflict);
            cJSON_AddBoolToObject(details, "clean_fill_timeout_mode", s_virtual_state.simulate_clean_fill_timeout);
            cJSON_AddBoolToObject(details, "solution_fill_timeout_mode", s_virtual_state.simulate_solution_fill_timeout);
            cJSON_AddStringToObject(details, "level_clean_min_override", switch_override_label(s_virtual_state.level_clean_min_override));
            cJSON_AddStringToObject(details, "level_clean_max_override", switch_override_label(s_virtual_state.level_clean_max_override));
            cJSON_AddStringToObject(details, "level_solution_min_override", switch_override_label(s_virtual_state.level_solution_min_override));
            cJSON_AddStringToObject(details, "level_solution_max_override", switch_override_label(s_virtual_state.level_solution_max_override));
            if (job->ph_value_present) {
                cJSON_AddNumberToObject(details, "ph_value", s_virtual_state.ph_value);
            }
            if (job->ec_value_present) {
                cJSON_AddNumberToObject(details, "ec_value", s_virtual_state.ec_value);
            }
            handled = true;
        } else if (strcmp(job->cmd, "reset_binding") == 0) {
            esp_err_t reset_err = config_storage_reset_namespace(PRECONFIG_GH_UID, PRECONFIG_ZONE_UID);
            if (reset_err != ESP_OK) {
                cJSON_AddStringToObject(details, "error", "binding_reset_failed");
                cJSON_AddStringToObject(details, "error_code", "binding_reset_failed");
                cJSON_AddStringToObject(details, "error_message", esp_err_to_name(reset_err));
                *status_out = "ERROR";
                return;
            }
            cJSON_AddStringToObject(details, "note", "binding_reset_pending_reboot");
            cJSON_AddStringToObject(details, "gh_uid", PRECONFIG_GH_UID);
            cJSON_AddStringToObject(details, "zone_uid", PRECONFIG_ZONE_UID);
            handled = true;
        } else if (strcmp(job->cmd, "activate_sensor_mode") == 0) {
            if (strstr(job->node_uid, "-ph-") != NULL) {
                if (s_virtual_state.ph_sensor_mode_active) {
                    cJSON_AddStringToObject(details, "note", "sensor_mode_already_active_treated_as_done");
                    handled = true;
                } else {
                    s_virtual_state.ph_sensor_mode_active = true;
                    handled = true;
                }
                publish_current_virtual_sensor_snapshot(false, true, false);
            } else if (strstr(job->node_uid, "-ec-") != NULL) {
                if (s_virtual_state.ec_sensor_mode_active) {
                    cJSON_AddStringToObject(details, "note", "sensor_mode_already_active_treated_as_done");
                    handled = true;
                } else {
                    s_virtual_state.ec_sensor_mode_active = true;
                    handled = true;
                }
                publish_current_virtual_sensor_snapshot(false, false, true);
            }
        } else if (strcmp(job->cmd, "deactivate_sensor_mode") == 0) {
            if (strstr(job->node_uid, "-ph-") != NULL) {
                if (!s_virtual_state.ph_sensor_mode_active) {
                    cJSON_AddStringToObject(details, "note", "sensor_mode_already_inactive_treated_as_done");
                    handled = true;
                } else {
                    s_virtual_state.ph_sensor_mode_active = false;
                    handled = true;
                }
            } else if (strstr(job->node_uid, "-ec-") != NULL) {
                if (!s_virtual_state.ec_sensor_mode_active) {
                    cJSON_AddStringToObject(details, "note", "sensor_mode_already_inactive_treated_as_done");
                    handled = true;
                } else {
                    s_virtual_state.ec_sensor_mode_active = false;
                    handled = true;
                }
            }
        }
    }

    if (!handled) {
        cJSON_AddStringToObject(details, "error", "unsupported_channel_cmd");
        status = "INVALID";
        *status_out = status;
        return;
    }

    if (job->amount_present) {
        cJSON_AddNumberToObject(details, "amount", job->amount_value);
    }

    s_virtual_state.water_level = clamp_float(s_virtual_state.water_level, 0.05f, 0.98f);
    s_virtual_state.solution_level = clamp_float(s_virtual_state.solution_level, 0.05f, 0.98f);

    {
        bool now_solution_fill_active = is_solution_fill_active();
        if (!was_solution_fill_active && now_solution_fill_active) {
            s_virtual_state.solution_fill_stage_active = true;
            s_virtual_state.solution_fill_started_at = get_timestamp_seconds();
            ui_logf(
                job->node_uid,
                "cmd delay solution_fill start %ds",
                SOLUTION_FILL_DELAY_SEC
            );
        } else if (was_solution_fill_active && !now_solution_fill_active) {
            if (s_virtual_state.solution_fill_stage_active && !s_virtual_state.solution_max_latched) {
                ui_logf(job->node_uid, "cmd delay solution_fill cancel");
            }
            s_virtual_state.solution_fill_stage_active = false;
            s_virtual_state.solution_fill_started_at = 0;
        }
    }

    *status_out = status;
}

static void execute_pending_command(const pending_command_t *job) {
    const virtual_node_t *node;
    cJSON *details;
    const char *final_status = "DONE";
    bool trigger_hardware_reboot = false;
    bool transient_main_pump_initial_state = false;
    bool transient_restore_main_pump = false;

    if (!job) {
        return;
    }

    node = find_virtual_node(job->node_uid);
    if (!node) {
        cJSON *error_details = cJSON_CreateObject();
        if (error_details) {
            cJSON_AddStringToObject(error_details, "error", "unknown_node");
        }
        publish_command_response(job->node_uid, job->channel, job->cmd_id, "ERROR", error_details);
        cJSON_Delete(error_details);
        return;
    }

    details = cJSON_CreateObject();
    if (!details) {
        publish_command_response(job->node_uid, job->channel, job->cmd_id, "ERROR", NULL);
        return;
    }

    cJSON_AddBoolToObject(details, "virtual", true);
    cJSON_AddStringToObject(details, "node_uid", job->node_uid);
    cJSON_AddStringToObject(details, "channel", job->channel);
    cJSON_AddStringToObject(details, "cmd", job->cmd);
    cJSON_AddNumberToObject(details, "exec_delay_ms", job->execute_delay_ms);
    ui_logf(job->node_uid, "cmd run %s/%s dly=%d", job->channel, job->cmd, job->execute_delay_ms);

    if (job->kind == COMMAND_KIND_ACTUATOR && !is_supported_actuator_command(job->channel, job->cmd)) {
        cJSON_AddStringToObject(details, "error", "unsupported_channel_cmd");
        publish_command_response(job->node_uid, job->channel, job->cmd_id, "INVALID", details);
        cJSON_Delete(details);
        return;
    }

    if (job->kind == COMMAND_KIND_GENERIC && is_unsupported_sensor_calibration_command(job)) {
        cJSON_AddStringToObject(details, "error", "unsupported_sensor_calibration_command");
        publish_command_response(job->node_uid, job->channel, job->cmd_id, "INVALID", details);
        cJSON_Delete(details);
        return;
    }

    if (job->kind == COMMAND_KIND_ACTUATOR && is_transient_command(job)) {
        if (is_main_pump_channel(job->channel)) {
            transient_main_pump_initial_state = s_virtual_state.main_pump_on;
            if (transient_main_pump_initial_state) {
                cJSON_AddBoolToObject(details, "main_pump_overlap", true);
            }
        }
        if (strcmp(job->channel, "pump_irrigation") == 0 && s_virtual_state.irrigation_on) {
            cJSON_AddStringToObject(details, "error", "actuator_busy");
            publish_command_response(job->node_uid, job->channel, job->cmd_id, "BUSY", details);
            cJSON_Delete(details);
            return;
        }
        if (is_fill_channel(job->channel) && s_virtual_state.tank_fill_on) {
            cJSON_AddStringToObject(details, "error", "actuator_busy");
            publish_command_response(job->node_uid, job->channel, job->cmd_id, "BUSY", details);
            cJSON_Delete(details);
            return;
        }
        if (is_drain_channel(job->channel) && s_virtual_state.tank_drain_on) {
            cJSON_AddStringToObject(details, "error", "actuator_busy");
            publish_command_response(job->node_uid, job->channel, job->cmd_id, "BUSY", details);
            cJSON_Delete(details);
            return;
        }
    }

    if (job->kind == COMMAND_KIND_ACTUATOR && is_transient_command(job)) {
        if (strcmp(job->channel, "pump_irrigation") == 0) {
            s_virtual_state.irrigation_on = true;
        } else if (is_main_pump_channel(job->channel)) {
            if (!is_main_pump_interlock_satisfied()) {
                append_main_pump_interlock_error(details);
                publish_command_response(job->node_uid, job->channel, job->cmd_id, "ERROR", details);
                cJSON_Delete(details);
                return;
            }
            s_virtual_state.main_pump_on = true;
            transient_restore_main_pump = transient_main_pump_initial_state;
        } else if (is_fill_channel(job->channel)) {
            s_virtual_state.tank_fill_on = true;
        } else if (is_drain_channel(job->channel)) {
            s_virtual_state.tank_drain_on = true;
        }
    }

    if (job->execute_delay_ms > 0) {
        vTaskDelay(pdMS_TO_TICKS(job->execute_delay_ms));
    }

    if (job->kind == COMMAND_KIND_SENSOR_PROBE) {
        cJSON *probe = build_sensor_probe_details(job->channel);
        if (probe) {
            cJSON_AddItemToObject(details, "probe", probe);
        }
    } else if (job->kind == COMMAND_KIND_STATE_QUERY) {
        cJSON *snapshot = build_irr_state_snapshot();
        if (snapshot) {
            cJSON_AddItemToObject(details, "snapshot", snapshot);
        }
        cJSON *fault_modes = cJSON_CreateObject();
        if (fault_modes) {
            cJSON_AddBoolToObject(fault_modes, "sensor_conflict_clean", s_virtual_state.force_clean_sensor_conflict);
            cJSON_AddBoolToObject(fault_modes, "sensor_conflict_solution", s_virtual_state.force_solution_sensor_conflict);
            cJSON_AddBoolToObject(fault_modes, "clean_fill_timeout_mode", s_virtual_state.simulate_clean_fill_timeout);
            cJSON_AddBoolToObject(fault_modes, "solution_fill_timeout_mode", s_virtual_state.simulate_solution_fill_timeout);
            cJSON_AddStringToObject(fault_modes, "level_clean_min_override", switch_override_label(s_virtual_state.level_clean_min_override));
            cJSON_AddStringToObject(fault_modes, "level_clean_max_override", switch_override_label(s_virtual_state.level_clean_max_override));
            cJSON_AddStringToObject(fault_modes, "level_solution_min_override", switch_override_label(s_virtual_state.level_solution_min_override));
            cJSON_AddStringToObject(fault_modes, "level_solution_max_override", switch_override_label(s_virtual_state.level_solution_max_override));
            cJSON_AddItemToObject(details, "fault_modes", fault_modes);
        }
        cJSON_AddNumberToObject(details, "sample_ts", (double)get_timestamp_seconds());
        cJSON_AddNumberToObject(details, "age_sec", 0);
        cJSON_AddNumberToObject(details, "max_age_sec", IRR_STATE_MAX_AGE_SEC);
        cJSON_AddBoolToObject(details, "is_fresh", true);
    } else if (job->kind == COMMAND_KIND_CONFIG_REPORT) {
        publish_config_report_for_node(node);
        cJSON_AddStringToObject(details, "note", "config_report_published");
    } else if (job->kind == COMMAND_KIND_RESTART) {
        size_t index;
        for (index = 0; index < VIRTUAL_NODE_COUNT; index++) {
            publish_status_for_node(VIRTUAL_NODES[index].node_uid, "RESTARTING");
        }
        cJSON_AddStringToObject(details, "note", "hardware_reboot_scheduled");
        cJSON_AddStringToObject(details, "scope", "device");
        trigger_hardware_reboot = true;
    } else if (job->kind == COMMAND_KIND_ACTUATOR) {
        update_virtual_state_from_command(job, details, &final_status);
    } else {
        cJSON_AddStringToObject(details, "note", "virtual_noop");
    }

    if (job->kind == COMMAND_KIND_ACTUATOR && is_transient_command(job)) {
        if (strcmp(job->channel, "pump_irrigation") == 0) {
            s_virtual_state.irrigation_on = false;
        } else if (is_main_pump_channel(job->channel)) {
            s_virtual_state.main_pump_on = transient_restore_main_pump;
        } else if (is_fill_channel(job->channel)) {
            s_virtual_state.tank_fill_on = false;
        } else if (is_drain_channel(job->channel)) {
            s_virtual_state.tank_drain_on = false;
        }
    }

    publish_command_response(job->node_uid, job->channel, job->cmd_id, final_status, details);
    ui_logf(job->node_uid, "cmd done %s/%s -> %s", job->channel, job->cmd, final_status);
    cJSON_Delete(details);

    if (trigger_hardware_reboot && strcmp(final_status, "DONE") == 0) {
        // Даем MQTT клиенту время отправить terminal response перед аппаратным reboot.
        vTaskDelay(pdMS_TO_TICKS(350));
        ESP_LOGW(CMD_TAG, "Hardware reboot requested by command: node=%s cmd=%s", job->node_uid, job->cmd);
        esp_restart();
    }
}

static void command_worker_task(void *pv_parameters) {
    pending_command_t job;
    (void)pv_parameters;

    ESP_LOGI(CMD_TAG, "Command worker started");

    while (1) {
        if (xQueueReceive(s_command_queue, &job, portMAX_DELAY) == pdTRUE) {
            s_command_worker_busy = true;
            execute_pending_command(&job);
            s_command_worker_busy = false;
        }
    }
}

static void state_command_worker_task(void *pv_parameters) {
    pending_command_t job;
    (void)pv_parameters;

    ESP_LOGI(CMD_TAG, "State command worker started");

    while (1) {
        if (xQueueReceive(s_state_command_queue, &job, portMAX_DELAY) == pdTRUE) {
            int64_t barrier_started_ms = get_uptime_ms_precise();
            while (1) {
                int64_t quiet_since_ms = s_last_non_state_command_rx_ms;
                int64_t now_ms = get_uptime_ms_precise();
                bool queue_idle = (
                    s_command_queue == NULL
                    || (
                        uxQueueMessagesWaiting(s_command_queue) == 0
                        && !s_command_worker_busy
                    )
                );

                if (quiet_since_ms < barrier_started_ms) {
                    quiet_since_ms = barrier_started_ms;
                }

                if (queue_idle && (now_ms - quiet_since_ms) >= STATE_QUERY_BARRIER_QUIET_MS) {
                    break;
                }

                vTaskDelay(pdMS_TO_TICKS(STATE_QUERY_BARRIER_POLL_MS));
            }
            execute_pending_command(&job);
        }
    }
}

static command_kind_t resolve_command_kind(const char *cmd_name) {
    if (!cmd_name || cmd_name[0] == '\0') {
        return COMMAND_KIND_GENERIC;
    }

    if (strcmp(cmd_name, "test_sensor") == 0 || strcmp(cmd_name, "probe_sensor") == 0) {
        return COMMAND_KIND_SENSOR_PROBE;
    }
    if (strcmp(cmd_name, "state") == 0) {
        return COMMAND_KIND_STATE_QUERY;
    }

    if (
        strcmp(cmd_name, "report_config") == 0 ||
        strcmp(cmd_name, "config_report") == 0 ||
        strcmp(cmd_name, "get_config") == 0 ||
        strcmp(cmd_name, "sync_config") == 0
    ) {
        return COMMAND_KIND_CONFIG_REPORT;
    }

    if (strcmp(cmd_name, "restart") == 0 || strcmp(cmd_name, "reboot") == 0) {
        return COMMAND_KIND_RESTART;
    }

    if (
        strcmp(cmd_name, "set_relay") == 0 ||
        strcmp(cmd_name, "set_pwm") == 0 ||
        strcmp(cmd_name, "run_pump") == 0 ||
        strcmp(cmd_name, "dose") == 0 ||
        strcmp(cmd_name, "emit_event") == 0 ||
        strcmp(cmd_name, "set_fault_mode") == 0 ||
        strcmp(cmd_name, "reset_state") == 0 ||
        strcmp(cmd_name, "reset_binding") == 0 ||
        strcmp(cmd_name, "activate_sensor_mode") == 0 ||
        strcmp(cmd_name, "deactivate_sensor_mode") == 0
    ) {
        return COMMAND_KIND_ACTUATOR;
    }

    return COMMAND_KIND_GENERIC;
}

static void command_callback(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx) {
    char topic_gh_uid[64] = {0};
    char topic_zone_uid[64] = {0};
    char current_gh_uid[64] = {0};
    char current_zone_uid[64] = {0};
    char node_uid[64] = {0};
    char topic_channel[64] = {0};
    cJSON *command_json;
    cJSON *cmd_id_item;
    cJSON *cmd_item;
    cJSON *ts_item;
    const char *cmd_id;
    const char *cmd_name;
    const char *validation_error_code = NULL;
    const char *validation_error_message = NULL;
    const virtual_node_t *node;
    pending_command_t job;
    BaseType_t queue_send_status = pdFALSE;

    (void)user_ctx;

    if (!topic || !data || data_len <= 0) {
        return;
    }

    if (!parse_command_topic(
        topic,
        topic_gh_uid,
        sizeof(topic_gh_uid),
        topic_zone_uid,
        sizeof(topic_zone_uid),
        node_uid,
        sizeof(node_uid),
        topic_channel,
        sizeof(topic_channel)
    )) {
        return;
    }

    if (!namespace_matches_node(node_uid, topic_gh_uid, topic_zone_uid)) {
        bool current_is_temp = false;
        bool topic_is_temp = is_temp_namespace(topic_gh_uid, topic_zone_uid);
        if (!get_node_namespace(node_uid, current_gh_uid, sizeof(current_gh_uid), current_zone_uid, sizeof(current_zone_uid), NULL)) {
            snprintf(current_gh_uid, sizeof(current_gh_uid), "unknown");
            snprintf(current_zone_uid, sizeof(current_zone_uid), "unknown");
        }
        current_is_temp = is_temp_namespace(current_gh_uid, current_zone_uid);
        if (current_is_temp && !topic_is_temp) {
            update_node_namespace(node_uid, topic_gh_uid, topic_zone_uid, "command_namespace_auto_bind");
            ui_logf(node_uid, "cmd ns adopt %s/%s", topic_gh_uid, topic_zone_uid);
            ESP_LOGW(
                TAG,
                "Auto-adopted namespace from command: node=%s old=%s/%s new=%s/%s",
                node_uid,
                current_gh_uid,
                current_zone_uid,
                topic_gh_uid,
                topic_zone_uid
            );
        } else {
            ESP_LOGW(
                TAG,
                "Ignoring command from stale namespace: topic=%s node=%s current=%s/%s",
                topic,
                node_uid,
                current_gh_uid,
                current_zone_uid
            );
            ui_logf(node_uid, "cmd stale ns ignored");
            return;
        }
    }

    node = find_virtual_node(node_uid);
    if (!node) {
        return;
    }

    command_json = cJSON_ParseWithLength(data, data_len);
    if (!command_json) {
        char payload_preview[161];
        int preview_len = data_len;
        const char *parse_error_ptr = cJSON_GetErrorPtr();
        int parse_error_offset = -1;
        int index;

        if (preview_len > (int)sizeof(payload_preview) - 1) {
            preview_len = (int)sizeof(payload_preview) - 1;
        }
        if (preview_len < 0) {
            preview_len = 0;
        }
        for (index = 0; index < preview_len; index++) {
            unsigned char ch = (unsigned char)data[index];
            payload_preview[index] = isprint(ch) ? (char)ch : '.';
        }
        payload_preview[preview_len] = '\0';

        if (parse_error_ptr && parse_error_ptr >= data && parse_error_ptr < (data + data_len)) {
            parse_error_offset = (int)(parse_error_ptr - data);
        }

        cJSON *details = cJSON_CreateObject();
        if (details) {
            cJSON_AddStringToObject(details, "error", "invalid_json");
            cJSON_AddNumberToObject(details, "payload_len", data_len);
            if (parse_error_offset >= 0) {
                cJSON_AddNumberToObject(details, "error_offset", parse_error_offset);
            }
            publish_command_response(node_uid, topic_channel, "unknown", "INVALID", details);
            cJSON_Delete(details);
        }
        ESP_LOGI(
            CMD_TAG,
            "[%s] cmd invalid_json len=%d err_off=%d payload='%s'",
            node_uid,
            data_len,
            parse_error_offset,
            payload_preview
        );
        ui_logf(node_uid, "cmd invalid_json");
        return;
    }

    cmd_id_item = cJSON_GetObjectItem(command_json, "cmd_id");
    cmd_item = cJSON_GetObjectItem(command_json, "cmd");
    cmd_id = (cmd_id_item && cJSON_IsString(cmd_id_item) && cmd_id_item->valuestring) ? cmd_id_item->valuestring : "unknown";
    if (is_duplicate_cmd_id(cmd_id)) {
        ui_logf(node_uid, "cmd duplicate ignored");
        cJSON_Delete(command_json);
        return;
    }
    if (!validate_command_payload_strict(command_json, &validation_error_code, &validation_error_message)) {
        cJSON *details = cJSON_CreateObject();
        if (details) {
            cJSON_AddStringToObject(
                details,
                "error_code",
                validation_error_code ? validation_error_code : "invalid_command_format"
            );
            cJSON_AddStringToObject(
                details,
                "error_message",
                validation_error_message ? validation_error_message : "Invalid command payload"
            );
            publish_command_response(node_uid, topic_channel, cmd_id, "ERROR", details);
            cJSON_Delete(details);
        }
        ui_logf(node_uid, "cmd invalid %s", validation_error_code ? validation_error_code : "invalid_payload");
        cJSON_Delete(command_json);
        return;
    }
    cmd_name = (cmd_item && cJSON_IsString(cmd_item) && cmd_item->valuestring) ? cmd_item->valuestring : "";
    ts_item = cJSON_GetObjectItem(command_json, "ts");
    if (ts_item && cJSON_IsNumber(ts_item)) {
        maybe_calibrate_timestamp_offset_from_command_ts((int64_t)cJSON_GetNumberValue(ts_item));
    }

    memset(&job, 0, sizeof(job));
    snprintf(job.node_uid, sizeof(job.node_uid), "%s", node_uid);
    snprintf(job.channel, sizeof(job.channel), "%s", topic_channel);
    snprintf(job.cmd_id, sizeof(job.cmd_id), "%s", cmd_id);
    snprintf(job.cmd, sizeof(job.cmd), "%s", cmd_name);
    job.kind = resolve_command_kind(cmd_name);
    job.execute_delay_ms = resolve_command_delay_ms(job.kind, &job, NULL);

    extract_command_params(command_json, &job);

    publish_command_response(node_uid, topic_channel, cmd_id, "ACK", NULL);
    ui_logf(node_uid, "cmd ack %s/%s", topic_channel, cmd_name);

    if (job.kind == COMMAND_KIND_STATE_QUERY) {
        if (s_state_command_fastpath_enabled && s_state_command_queue != NULL) {
            queue_send_status = xQueueSend(s_state_command_queue, &job, 0);
        }
        if (queue_send_status != pdTRUE && s_command_queue) {
            queue_send_status = xQueueSendToFront(s_command_queue, &job, 0);
        }
    } else if (s_command_queue) {
        queue_send_status = xQueueSend(s_command_queue, &job, 0);
    }

    if (queue_send_status == pdTRUE && job.kind != COMMAND_KIND_STATE_QUERY) {
        s_last_non_state_command_rx_ms = get_uptime_ms_precise();
    }

    if (queue_send_status != pdTRUE) {
        cJSON *details = cJSON_CreateObject();
        if (details) {
            cJSON_AddStringToObject(details, "error", "command_queue_full");
            publish_command_response(node_uid, topic_channel, cmd_id, "BUSY", details);
            cJSON_Delete(details);
        }
        ui_logf(node_uid, "cmd busy queue_full");
    } else {
        ui_logf(node_uid, "cmd queued %s/%s", topic_channel, cmd_name);
    }

    cJSON_Delete(command_json);

    ESP_LOGI(
        CMD_TAG,
        "Virtual command accepted: node=%s channel=%s cmd=%s cmd_id=%s",
        job.node_uid,
        job.channel,
        job.cmd,
        job.cmd_id
    );
}

static void config_callback(const char *topic, const char *data, int data_len, void *user_ctx) {
    char topic_gh_uid[64] = {0};
    char topic_zone_uid[64] = {0};
    char topic_node_uid[64] = {0};
    char current_gh_uid[64] = {0};
    char current_zone_uid[64] = {0};
    char next_gh_uid[64] = {0};
    char next_zone_uid[64] = {0};
    bool current_preconfig_mode = false;
    cJSON *config_json = NULL;
    cJSON *gh_uid_item;
    cJSON *zone_uid_item;
    const virtual_node_t *node;
    bool is_temp_topic = false;
    (void)user_ctx;

    if (!topic || !data || data_len <= 0) {
        return;
    }

    if (!parse_config_topic(
        topic,
        topic_gh_uid,
        sizeof(topic_gh_uid),
        topic_zone_uid,
        sizeof(topic_zone_uid),
        topic_node_uid,
        sizeof(topic_node_uid)
    )) {
        return;
    }

    node = find_virtual_node(topic_node_uid);
    if (!node) {
        return;
    }

    if (!get_node_namespace(
        topic_node_uid,
        current_gh_uid,
        sizeof(current_gh_uid),
        current_zone_uid,
        sizeof(current_zone_uid),
        &current_preconfig_mode
    )) {
        ESP_LOGW(TAG, "Cannot resolve current namespace for node=%s", topic_node_uid);
        return;
    }

    is_temp_topic = (strcmp(topic_gh_uid, "gh-temp") == 0) && (strcmp(topic_zone_uid, "zn-temp") == 0);

    if (
        !current_preconfig_mode &&
        !is_temp_topic &&
        (strcmp(topic_gh_uid, current_gh_uid) != 0 || strcmp(topic_zone_uid, current_zone_uid) != 0)
    ) {
        ESP_LOGW(
            TAG,
            "Ignoring config from stale namespace: topic=%s node=%s current=%s/%s",
            topic,
            topic_node_uid,
            current_gh_uid,
            current_zone_uid
        );
        ui_logf(topic_node_uid, "config stale ns ignored");
        return;
    }

    config_json = cJSON_ParseWithLength(data, data_len);
    if (!config_json) {
        ESP_LOGW(TAG, "Failed to parse config payload for topic=%s", topic);
        ui_logf(topic_node_uid, "config invalid_json");
        return;
    }

    gh_uid_item = cJSON_GetObjectItem(config_json, "gh_uid");
    zone_uid_item = cJSON_GetObjectItem(config_json, "zone_uid");

    if (gh_uid_item && cJSON_IsString(gh_uid_item) && gh_uid_item->valuestring && gh_uid_item->valuestring[0] != '\0') {
        snprintf(next_gh_uid, sizeof(next_gh_uid), "%s", gh_uid_item->valuestring);
    } else {
        snprintf(next_gh_uid, sizeof(next_gh_uid), "%s", topic_gh_uid);
    }

    if (zone_uid_item && cJSON_IsString(zone_uid_item) && zone_uid_item->valuestring && zone_uid_item->valuestring[0] != '\0') {
        snprintf(next_zone_uid, sizeof(next_zone_uid), "%s", zone_uid_item->valuestring);
    } else {
        snprintf(next_zone_uid, sizeof(next_zone_uid), "%s", topic_zone_uid);
    }

    cJSON_Delete(config_json);

    if (next_gh_uid[0] == '\0' || next_zone_uid[0] == '\0') {
        ESP_LOGW(TAG, "Config ignored: invalid namespace gh=%s zone=%s", next_gh_uid, next_zone_uid);
        ui_logf(topic_node_uid, "config invalid namespace");
        return;
    }

    if (!update_node_namespace(topic_node_uid, next_gh_uid, next_zone_uid, "mqtt_config")) {
        ESP_LOGI(
            TAG,
            "Config namespace unchanged for node=%s gh=%s zone=%s",
            topic_node_uid,
            next_gh_uid,
            next_zone_uid
        );
    }

    persist_received_config_or_namespace(
        topic_node_uid,
        data,
        data_len,
        next_gh_uid,
        next_zone_uid
    );

    publish_status_for_node(topic_node_uid, "ONLINE");
    publish_config_report_for_node(node);
    test_node_ui_set_node_zone(topic_node_uid, next_zone_uid);
    ui_logf(topic_node_uid, "config applied zone=%s", next_zone_uid);

    ESP_LOGI(
        TAG,
        "Config applied for virtual node: node=%s gh=%s zone=%s",
        topic_node_uid,
        next_gh_uid,
        next_zone_uid
    );
}

static void apply_passive_drift(void) {
    float drift = ((float)(s_telemetry_tick % 11) - 5.0f) * TELEMETRY_DRIFT_WAVE_AMPLITUDE;
    float ph_drift = drift;
    float ec_drift = drift * 2.0f;
    bool clean_fill_active = is_clean_fill_active();
    bool solution_fill_active = is_solution_fill_active();
    bool irrigation_active = is_irrigation_active();
    int64_t now_sec = get_timestamp_seconds();

    apply_scheduled_correction_responses();

    if (s_virtual_state.pending_ph_delay_ticks == 0 &&
        s_virtual_state.pending_ec_delay_ticks == 0 &&
        s_virtual_state.ph_decay_ticks_remaining == 0 &&
        s_virtual_state.ec_decay_ticks_remaining == 0) {
        ph_drift += PH_DRIFT_BIAS_PER_TICK;
        ec_drift += EC_DRIFT_BIAS_PER_TICK;
    }

    s_virtual_state.ph_value = clamp_float(s_virtual_state.ph_value + ph_drift, 4.8f, 7.2f);
    s_virtual_state.ec_value = clamp_float(s_virtual_state.ec_value + ec_drift, 0.4f, 3.2f);

    if (s_virtual_state.clean_fill_stage_active && s_virtual_state.clean_fill_started_at > 0) {
        if ((now_sec - s_virtual_state.clean_fill_started_at) >= CLEAN_FILL_DELAY_SEC) {
            if (s_virtual_state.simulate_clean_fill_timeout) {
                publish_irrig_node_event("clean_fill_timeout");
            } else {
                if (s_virtual_state.water_level < CLEAN_MAX_LATCH_LEVEL) {
                    s_virtual_state.water_level = CLEAN_MAX_LATCH_LEVEL;
                }
                if (!s_virtual_state.clean_max_latched) {
                    ui_logf(DEFAULT_MQTT_NODE_UID, "cmd delay clean_fill done max=1");
                    publish_irrig_node_event("clean_fill_completed");
                }
                s_virtual_state.clean_max_latched = true;
            }
            s_virtual_state.clean_fill_stage_active = false;
            s_virtual_state.clean_fill_started_at = 0;
        }
    }
    if (s_virtual_state.solution_fill_stage_active && s_virtual_state.solution_fill_started_at > 0) {
        if ((now_sec - s_virtual_state.solution_fill_started_at) >= SOLUTION_FILL_DELAY_SEC) {
            if (s_virtual_state.simulate_solution_fill_timeout) {
                publish_irrig_node_event("solution_fill_timeout");
            } else {
                if (s_virtual_state.solution_level < SOLUTION_MAX_LATCH_LEVEL) {
                    s_virtual_state.solution_level = SOLUTION_MAX_LATCH_LEVEL;
                }
                if (!s_virtual_state.solution_max_latched) {
                    ui_logf(DEFAULT_MQTT_NODE_UID, "cmd delay solution_fill done max=1");
                    publish_irrig_node_event("solution_fill_completed");
                }
                s_virtual_state.solution_max_latched = true;
            }
            s_virtual_state.solution_fill_stage_active = false;
            s_virtual_state.solution_fill_started_at = 0;
        }
    }

    if (clean_fill_active) {
        s_virtual_state.water_level = clamp_float(s_virtual_state.water_level + 0.003f, 0.05f, 0.88f);
    }
    if (solution_fill_active) {
        float transfer = 0.006f;
        float available = s_virtual_state.water_level - 0.05f;
        if (available > 0.0f) {
            if (transfer > available) {
                transfer = available;
            }
            s_virtual_state.water_level = clamp_float(s_virtual_state.water_level - transfer, 0.05f, 0.98f);
            s_virtual_state.solution_level = clamp_float(s_virtual_state.solution_level + transfer, 0.05f, 0.98f);
        }
    }
    if (irrigation_active) {
        s_virtual_state.solution_level = clamp_float(s_virtual_state.solution_level - 0.008f, 0.05f, 0.98f);
    }
    if (s_virtual_state.tank_drain_on) {
        s_virtual_state.solution_level = clamp_float(s_virtual_state.solution_level - 0.008f, 0.05f, 0.98f);
    }
    if (s_virtual_state.fan_on) {
        s_virtual_state.air_temp = clamp_float(s_virtual_state.air_temp - 0.05f, 18.0f, 32.0f);
        s_virtual_state.air_humidity = clamp_float(s_virtual_state.air_humidity - 0.08f, 35.0f, 90.0f);
    } else {
        s_virtual_state.air_temp = clamp_float(s_virtual_state.air_temp + 0.02f, 18.0f, 32.0f);
        s_virtual_state.air_humidity = clamp_float(s_virtual_state.air_humidity + 0.03f, 35.0f, 90.0f);
    }
    if (s_virtual_state.heater_on) {
        s_virtual_state.air_temp = clamp_float(s_virtual_state.air_temp + 0.09f, 18.0f, 32.0f);
        s_virtual_state.air_humidity = clamp_float(s_virtual_state.air_humidity - 0.04f, 35.0f, 90.0f);
    }

    if (s_virtual_state.light_on) {
        float pwm_factor = (float)s_virtual_state.light_pwm / 255.0f;
        if (pwm_factor < 0.1f) {
            pwm_factor = 1.0f;
        }
        s_virtual_state.light_level = clamp_float(12000.0f + (pwm_factor * 18000.0f), 2000.0f, 36000.0f);
    } else {
        s_virtual_state.light_level = clamp_float(s_virtual_state.light_level - 700.0f, 100.0f, 36000.0f);
    }

    s_virtual_state.flow_rate = irrigation_active ? 1.20f : 0.0f;
    if (s_virtual_state.irrigation_boost_ticks > 0) {
        s_virtual_state.flow_rate += 0.40f;
        s_virtual_state.irrigation_boost_ticks--;
    }

    s_virtual_state.pump_bus_current = 120.0f;
    if (irrigation_active) {
        s_virtual_state.pump_bus_current += 80.0f;
    }
    if (clean_fill_active || solution_fill_active || s_virtual_state.tank_drain_on) {
        s_virtual_state.pump_bus_current += 70.0f;
    }
    if (s_virtual_state.correction_boost_ticks > 0) {
        s_virtual_state.pump_bus_current += 50.0f;
        s_virtual_state.correction_boost_ticks--;
    }
}

static void publish_virtual_telemetry_batch(void) {
    apply_passive_drift();

    publish_telemetry_for_node(
        "nd-test-irrig-1",
        "level_clean_min",
        "WATER_LEVEL_SWITCH",
        resolve_clean_min_switch_value()
    );
    publish_telemetry_for_node(
        "nd-test-irrig-1",
        "level_clean_max",
        "WATER_LEVEL_SWITCH",
        resolve_clean_max_switch_value()
    );
    publish_telemetry_for_node(
        "nd-test-irrig-1",
        "level_solution_min",
        "WATER_LEVEL_SWITCH",
        resolve_solution_min_switch_value()
    );
    publish_telemetry_for_node(
        "nd-test-irrig-1",
        "level_solution_max",
        "WATER_LEVEL_SWITCH",
        resolve_solution_max_switch_value()
    );

    if (s_virtual_state.ph_sensor_mode_active) {
        publish_telemetry_for_node("nd-test-ph-1", "ph_sensor", "PH", s_virtual_state.ph_value);
    }
    if (s_virtual_state.ec_sensor_mode_active) {
        publish_telemetry_for_node("nd-test-ec-1", "ec_sensor", "EC", s_virtual_state.ec_value);
    }

    publish_telemetry_for_node("nd-test-climate-1", "air_temp_c", "TEMPERATURE", s_virtual_state.air_temp);
    publish_telemetry_for_node("nd-test-climate-1", "air_rh", "HUMIDITY", s_virtual_state.air_humidity);

    publish_telemetry_for_node("nd-test-light-1", "light_level", "LIGHT_INTENSITY", s_virtual_state.light_level);

    s_telemetry_tick++;
}

static void refresh_wildcard_subscriptions(const char *reason) {
    esp_err_t cmd_sub_err;
    esp_err_t cfg_sub_err;

    if (!mqtt_manager_is_connected()) {
        s_wildcard_subscriptions_ready = false;
        s_wildcard_subscribe_warned = false;
        return;
    }
    if (s_wildcard_subscriptions_ready) {
        return;
    }

    cmd_sub_err = mqtt_manager_subscribe_raw(COMMAND_WILDCARD_TOPIC, 1);
    cfg_sub_err = mqtt_manager_subscribe_raw(CONFIG_WILDCARD_TOPIC, 1);

    if (cmd_sub_err == ESP_OK && cfg_sub_err == ESP_OK) {
        s_wildcard_subscriptions_ready = true;
        s_wildcard_subscribe_warned = false;
        ESP_LOGI(TAG, "Wildcard subscriptions ready (reason=%s)", reason ? reason : "unknown");
        return;
    }

    if (!s_wildcard_subscribe_warned) {
        ESP_LOGW(
            TAG,
            "Wildcard subscribe attempt failed (reason=%s, cmd=%s, cfg=%s), will retry",
            reason ? reason : "unknown",
            esp_err_to_name(cmd_sub_err),
            esp_err_to_name(cfg_sub_err)
        );
        s_wildcard_subscribe_warned = true;
    }
}

static void task_publish_telemetry(void *pv_parameters) {
    size_t index;
    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(TELEMETRY_INTERVAL_MS);
    bool last_wifi_connected = false;
    bool last_mqtt_connected = false;
    bool has_wifi_state = false;
    bool has_mqtt_state = false;
    char last_wifi_text[33] = {0};
    uint8_t node_resync_ticks = 0;
    uint32_t config_elapsed_ms = 0;
    (void)pv_parameters;

    ESP_LOGI(TAG, "Telemetry task started");
    while (1) {
        bool wifi_connected;
        bool mqtt_connected;
        char wifi_text[33] = "X";

        vTaskDelayUntil(&last_wake_time, interval);
        wifi_connected = wifi_manager_is_connected();
        mqtt_connected = mqtt_manager_is_connected();

        if (mqtt_connected) {
            publish_virtual_telemetry_batch();
        } else {
            // В offline режиме продолжаем обновлять виртуальное состояние,
            // но не шлём telemetry в MQTT, чтобы не засорять лог ошибками publish.
            apply_passive_drift();
            s_telemetry_tick++;
        }

        if (wifi_connected) {
            wifi_ap_record_t ap_info = {0};
            if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK && ap_info.ssid[0] != '\0') {
                memcpy(wifi_text, ap_info.ssid, sizeof(ap_info.ssid));
                wifi_text[sizeof(wifi_text) - 1] = '\0';
            } else {
                snprintf(wifi_text, sizeof(wifi_text), "OK");
            }
        }

        if (!has_wifi_state || wifi_connected != last_wifi_connected || strcmp(wifi_text, last_wifi_text) != 0) {
            test_node_ui_set_wifi_status(wifi_connected, wifi_text);
            has_wifi_state = true;
            last_wifi_connected = wifi_connected;
            snprintf(last_wifi_text, sizeof(last_wifi_text), "%s", wifi_text);
        }

        if (!has_mqtt_state || mqtt_connected != last_mqtt_connected) {
            test_node_ui_set_mqtt_status(mqtt_connected, mqtt_connected ? "OK" : "X");
            has_mqtt_state = true;
            last_mqtt_connected = mqtt_connected;
        }

        if (mqtt_connected) {
            refresh_wildcard_subscriptions("telemetry_loop");
        }

        if (mqtt_connected) {
            if (s_config_report_on_connect_pending) {
                bool batch_ok = publish_all_config_reports("mqtt_connected_deferred");
                s_config_report_on_connect_pending = !batch_ok;
                config_elapsed_ms = 0;
            }

            for (index = 0; index < (sizeof(VIRTUAL_NODES) / sizeof(VIRTUAL_NODES[0])); index++) {
                if (!mqtt_manager_is_connected()) {
                    break;
                }
                publish_heartbeat_for_node(VIRTUAL_NODES[index].node_uid);
            }

            config_elapsed_ms += TELEMETRY_INTERVAL_MS;
            if (config_elapsed_ms >= CONFIG_REPORT_INTERVAL_MS) {
                bool batch_ok = publish_all_config_reports("periodic");
                if (!batch_ok) {
                    s_config_report_on_connect_pending = true;
                }
                config_elapsed_ms = 0;
            }
        }

        node_resync_ticks++;
        if (node_resync_ticks >= 2) {
            node_resync_ticks = 0;
            ui_sync_all_virtual_nodes(false);
        }

        if (!mqtt_connected) {
            ui_logf(NULL, "tel local (mqtt off)");
            config_elapsed_ms = 0;
        }
    }
}

static void wifi_connected_callback(bool connected, void *user_ctx) {
    (void)user_ctx;

    if (connected) {
        // Важно: callback вызывается из системного event-task (sys_evt), здесь только лёгкая работа.
        test_node_ui_set_wifi_status(true, "OK");
    } else {
        test_node_ui_set_wifi_status(false, "X");
    }
}

static void mqtt_connected_callback(bool connected, void *user_ctx) {
    size_t index;
    size_t preconfig_count = 0;
    (void)user_ctx;

    if (!connected) {
        s_wildcard_subscriptions_ready = false;
        s_wildcard_subscribe_warned = false;
        // При разрыве соединения сохраняем отложенный флаг,
        // чтобы после reconnect гарантированно перепослать config_report.
        s_config_report_on_connect_pending = true;
        test_node_ui_set_mqtt_status(false, "X");
        ui_logf(NULL, "mqtt disconnected");
        for (index = 0; index < VIRTUAL_NODE_COUNT; index++) {
            test_node_ui_mark_node_lwt(VIRTUAL_NODES[index].node_uid);
            test_node_ui_set_node_status(VIRTUAL_NODES[index].node_uid, "OFFLINE");
        }
        test_node_ui_show_step("MQTT disconnected");
        return;
    }

    test_node_ui_set_mqtt_status(true, "OK");
    ui_logf(NULL, "mqtt connected");
    test_node_ui_show_step("MQTT connected: subscribing");

    if (!mqtt_manager_is_connected()) {
        ESP_LOGW(TAG, "MQTT callback(connected=true) ignored: manager is already disconnected");
        return;
    }

    // Подписываем wildcard сразу после reconnect, чтобы не терять ранние команды.
    refresh_wildcard_subscriptions("mqtt_connected_cb");

    for (index = 0; index < VIRTUAL_NODE_COUNT; index++) {
        bool node_preconfig_mode = false;
        char node_gh_uid[64] = {0};
        char node_zone_uid[64] = {0};

        if (!mqtt_manager_is_connected()) {
            ESP_LOGW(TAG, "MQTT disconnected during virtual node sync, stopping batch");
            break;
        }

        if (get_node_namespace(
            VIRTUAL_NODES[index].node_uid,
            node_gh_uid,
            sizeof(node_gh_uid),
            node_zone_uid,
            sizeof(node_zone_uid),
            &node_preconfig_mode
        )) {
            if (node_preconfig_mode) {
                preconfig_count++;
            }
        }

        publish_node_hello_for_node(&VIRTUAL_NODES[index]);
        publish_status_for_node(VIRTUAL_NODES[index].node_uid, "ONLINE");
    }

    if (mqtt_manager_is_connected()) {
        s_config_report_on_connect_pending = true;
    }
    test_node_ui_show_step("MQTT connected: virtual nodes ONLINE");

    ESP_LOGI(
        TAG,
        "Virtual nodes status published (preconfig=%u/%u)",
        (unsigned)preconfig_count,
        (unsigned)VIRTUAL_NODE_COUNT
    );
}

static esp_err_t run_setup_portal_blocking(void) {
    esp_err_t err;
    setup_portal_full_config_t setup_cfg = {
        .node_type_prefix = "TESTNODE",
        .ap_password = "hydro2025",
        .enable_oled = false,
        .oled_user_ctx = NULL,
    };
    char setup_pin[7] = {0};
    char ap_ssid[32] = {0};
    const char *ap_password = setup_cfg.ap_password ? setup_cfg.ap_password : "hydro2025";

    ESP_LOGW(TAG, "Launching setup portal for WiFi/MQTT configuration");
    test_node_ui_set_mode("SETUP");
    test_node_ui_set_wifi_status(false, "X");
    test_node_ui_set_mqtt_status(false, "X");
    test_node_ui_set_setup_info("...", ap_password, "......");
    ui_logf(NULL, "setup portal start");
    test_node_ui_show_step("=== NODE SETUP MODE ACTIVATED ===");
    if (setup_portal_generate_pin(setup_pin, sizeof(setup_pin)) == ESP_OK) {
        snprintf(ap_ssid, sizeof(ap_ssid), "%s_SETUP_%s", setup_cfg.node_type_prefix, setup_pin);
        test_node_ui_set_setup_info(ap_ssid, ap_password, setup_pin);
        ui_logf(NULL, "=== NODE SETUP MODE ACTIVATED ===");
        ui_logf(NULL, "Connection data:");
        ui_logf(NULL, "  WiFi SSID:    %s", ap_ssid);
        ui_logf(NULL, "  WiFi Pass:    [%u characters]", (unsigned)strlen(ap_password));
        ui_logf(NULL, "  PIN:          [%u characters]", (unsigned)strlen(setup_pin));
        ui_logf(NULL, "  Open browser: http://192.168.4.1");
    } else {
        test_node_ui_set_setup_info("TESTNODE_SETUP_??????", ap_password, "------");
        ui_logf(NULL, "setup pin generate failed");
    }
    test_node_ui_show_step("Setup portal started");
    err = setup_portal_run_full_setup(&setup_cfg);
    if (err == ESP_OK) {
        test_node_ui_set_mode("RUN");
        test_node_ui_show_step("Setup portal completed");
    } else {
        test_node_ui_set_mode("SETUP_ERR");
    }
    return err;
}

static bool has_valid_network_config(void) {
    config_storage_wifi_t wifi_cfg = {0};
    config_storage_mqtt_t mqtt_cfg = {0};

    if (config_storage_get_wifi(&wifi_cfg) != ESP_OK) {
        return false;
    }
    if (strlen(wifi_cfg.ssid) == 0) {
        return false;
    }

    if (config_storage_get_mqtt(&mqtt_cfg) != ESP_OK) {
        return false;
    }
    if (strlen(mqtt_cfg.host) == 0 || mqtt_cfg.port == 0) {
        return false;
    }

    return true;
}

static void reset_runtime_namespace_to_preconfig(
    mqtt_node_info_t *mqtt_node_info,
    char *gh_uid,
    size_t gh_uid_size,
    char *zone_uid,
    size_t zone_uid_size
) {
    if (!mqtt_node_info || !gh_uid || !zone_uid || gh_uid_size == 0 || zone_uid_size == 0) {
        return;
    }

    // Важно: сбрасываем только runtime namespace тест-ноды.
    // Wi-Fi/MQTT credentials в NVS не изменяются.
    snprintf(gh_uid, gh_uid_size, "%s", PRECONFIG_GH_UID);
    snprintf(zone_uid, zone_uid_size, "%s", PRECONFIG_ZONE_UID);
    mqtt_node_info->gh_uid = gh_uid;
    mqtt_node_info->zone_uid = zone_uid;

    ESP_LOGW(
        TAG,
        "Runtime namespace reset to preconfig defaults on boot: %s/%s",
        PRECONFIG_GH_UID,
        PRECONFIG_ZONE_UID
    );
}

static bool should_boot_in_preconfig_mode(const char *gh_uid, const char *zone_uid) {
    if (!gh_uid || !zone_uid || gh_uid[0] == '\0' || zone_uid[0] == '\0') {
        return true;
    }

    return (strcmp(gh_uid, PRECONFIG_GH_UID) == 0) || (strcmp(zone_uid, PRECONFIG_ZONE_UID) == 0);
}

// True when payload contains a full NodeConfig (not namespace-only config nudge).
static bool is_full_node_config_payload(const char *config_payload, int config_payload_len) {
    if (!config_payload || config_payload_len <= 0) {
        return false;
    }

    cJSON *root = cJSON_ParseWithLength(config_payload, (size_t)config_payload_len);
    if (!root) {
        return false;
    }

    cJSON *node_id = cJSON_GetObjectItem(root, "node_id");
    cJSON *version = cJSON_GetObjectItem(root, "version");
    cJSON *type = cJSON_GetObjectItem(root, "type");
    cJSON *channels = cJSON_GetObjectItem(root, "channels");
    cJSON *mqtt = cJSON_GetObjectItem(root, "mqtt");

    bool is_full =
        cJSON_IsString(node_id) &&
        cJSON_IsNumber(version) &&
        cJSON_IsString(type) &&
        cJSON_IsArray(channels) &&
        cJSON_IsObject(mqtt);

    cJSON_Delete(root);
    return is_full;
}

static void persist_received_config_or_namespace(
    const char *node_uid,
    const char *config_payload,
    int config_payload_len,
    const char *gh_uid,
    const char *zone_uid
) {
    bool allow_namespace_persist = false;
    esp_err_t save_err = ESP_ERR_INVALID_ARG;

    if (!node_uid || !gh_uid || !zone_uid || gh_uid[0] == '\0' || zone_uid[0] == '\0') {
        return;
    }

    // test_node использует единый NVS key для всех виртуальных нод.
    // Сохранение полного NodeConfig из runtime-MQTT приводит к периодическим
    // валидационным конфликтам и шуму в логах, а также потенциально перетирает
    // базовый конфиг тестовой ноды. Для real-hardware e2e нам нужен только
    // persist namespace базовой виртуальной ноды.
    allow_namespace_persist = (strcmp(node_uid, DEFAULT_MQTT_NODE_UID) == 0);

    if (config_payload && config_payload_len > 0 &&
        is_full_node_config_payload(config_payload, config_payload_len)) {
        ESP_LOGI(
            TAG,
            "Full config payload received for node=%s; skip full config_storage save in test_node runtime path",
            node_uid
        );
    }
    save_err = ESP_ERR_NOT_SUPPORTED;

    if (save_err == ESP_OK) {
        ui_logf(node_uid, "config persisted");
        return;
    }

    // В test_node config_storage хранит один общий NodeConfig key.
    // Если писать namespace сюда для любой виртуальной ноды, после reboot все виртуальные
    // ноды стартуют в одной и той же зоне. Поэтому fallback-персист namespace
    // разрешаем только для базовой виртуальной ноды.
    if (allow_namespace_persist) {
        save_err = config_storage_reset_namespace(gh_uid, zone_uid);
        if (save_err == ESP_OK) {
            ui_logf(node_uid, "namespace persisted");
            ESP_LOGW(
                TAG,
                "Config save failed, namespace persisted only: node=%s gh=%s zone=%s",
                node_uid,
                gh_uid,
                zone_uid
            );
            return;
        }
    } else {
        ui_logf(node_uid, "namespace persist skipped");
        ESP_LOGI(
            TAG,
            "Skip global namespace persist for virtual node=%s gh=%s zone=%s",
            node_uid,
            gh_uid,
            zone_uid
        );
        return;
    }

    ui_logf(node_uid, "config persist err=%s", esp_err_to_name(save_err));
    ESP_LOGW(
        TAG,
        "Failed to persist config/namespace: node=%s gh=%s zone=%s err=%s",
        node_uid,
        gh_uid,
        zone_uid,
        esp_err_to_name(save_err)
    );
}

static esp_err_t start_worker_task(
    TaskFunction_t task_fn,
    const char *task_name,
    uint32_t stack_size,
    uint32_t fallback_stack_size,
    UBaseType_t priority,
    bool required
) {
    BaseType_t created = pdFAIL;
    char step_line[96];
    uint32_t free_heap_before = esp_get_free_heap_size();
    uint32_t used_stack = stack_size;

    created = xTaskCreate(task_fn, task_name, stack_size, NULL, priority, NULL);
    if (created != pdPASS && fallback_stack_size > 0 && fallback_stack_size < stack_size) {
        ESP_LOGW(
            TAG,
            "Task '%s' start failed with stack=%u, retry with fallback=%u (heap=%u)",
            task_name ? task_name : "unknown",
            (unsigned)stack_size,
            (unsigned)fallback_stack_size,
            (unsigned)free_heap_before
        );
        created = xTaskCreate(task_fn, task_name, fallback_stack_size, NULL, priority, NULL);
        used_stack = fallback_stack_size;
    }

    if (created != pdPASS) {
        snprintf(step_line, sizeof(step_line), "Task %s FAILED (OOM)", task_name ? task_name : "unknown");
        test_node_ui_show_step(step_line);
        ui_logf(NULL, "task %s FAIL heap=%u", task_name ? task_name : "unknown", (unsigned)free_heap_before);

        if (required) {
            ESP_LOGE(
                TAG,
                "Failed to start required task '%s' (stack=%u prio=%u heap=%u)",
                task_name ? task_name : "unknown",
                (unsigned)used_stack,
                (unsigned)priority,
                (unsigned)free_heap_before
            );
            return ESP_ERR_NO_MEM;
        }

        ESP_LOGW(
            TAG,
            "Failed to start optional task '%s' (stack=%u prio=%u heap=%u)",
            task_name ? task_name : "unknown",
            (unsigned)used_stack,
            (unsigned)priority,
            (unsigned)free_heap_before
        );
        return ESP_FAIL;
    }

    ESP_LOGI(
        TAG,
        "Task started: %s (stack=%u prio=%u heap_after=%u)",
        task_name ? task_name : "unknown",
        (unsigned)used_stack,
        (unsigned)priority,
        (unsigned)esp_get_free_heap_size()
    );
    ui_logf(NULL, "task %s started", task_name ? task_name : "unknown");
    return ESP_OK;
}

static void factory_reset_reboot_task(void *pv_params) {
    (void)pv_params;
    vTaskDelay(pdMS_TO_TICKS(1500));
    esp_restart();
}

static void handle_ui_settings_action(test_node_ui_settings_action_t action, void *user_ctx) {
    (void)user_ctx;

    if (action == TEST_NODE_UI_SETTINGS_ACTION_RESET_ZONES) {
        size_t index;
        esp_err_t save_err = config_storage_reset_namespace(PRECONFIG_GH_UID, PRECONFIG_ZONE_UID);

        for (index = 0; index < VIRTUAL_NODE_COUNT; index++) {
            (void)update_node_namespace(
                VIRTUAL_NODES[index].node_uid,
                PRECONFIG_GH_UID,
                PRECONFIG_ZONE_UID,
                "ui_settings_reset_zones"
            );
        }
        ui_sync_all_virtual_nodes(false);

        if (mqtt_manager_is_connected()) {
            publish_all_config_reports("ui_settings_reset_zones");
        }

        if (save_err == ESP_OK) {
            ui_logf(NULL, "settings: zones reset to %s/%s", PRECONFIG_GH_UID, PRECONFIG_ZONE_UID);
        } else {
            ui_logf(
                NULL,
                "settings: zones runtime reset, config save err=%s",
                esp_err_to_name(save_err)
            );
        }
        return;
    }

    if (action == TEST_NODE_UI_SETTINGS_ACTION_FACTORY_RESET) {
        esp_err_t reset_err = config_storage_factory_reset();
        if (reset_err != ESP_OK) {
            ui_logf(NULL, "settings: factory reset failed (%s)", esp_err_to_name(reset_err));
            return;
        }
        if (!s_factory_reset_pending) {
            s_factory_reset_pending = true;
            ui_logf(NULL, "settings: factory reset OK, rebooting...");
            test_node_ui_set_mode("RESET");
            if (xTaskCreate(factory_reset_reboot_task, "factory_reset_reboot", 3072, NULL, 7, NULL) != pdPASS) {
                s_factory_reset_pending = false;
                ui_logf(NULL, "settings: reboot task create failed");
            }
        }
    }
}

static void cleanup_init_runtime_resources(void) {
    if (s_command_queue) {
        vQueueDelete(s_command_queue);
        s_command_queue = NULL;
    }
    if (s_state_command_queue) {
        vQueueDelete(s_state_command_queue);
        s_state_command_queue = NULL;
    }
    if (s_topic_mutex) {
        vSemaphoreDelete(s_topic_mutex);
        s_topic_mutex = NULL;
    }

    s_wildcard_subscriptions_ready = false;
    s_wildcard_subscribe_warned = false;
    s_state_command_fastpath_enabled = false;
    s_last_non_state_command_rx_ms = 0;
    (void)mqtt_manager_deinit();
    wifi_manager_deinit();
}

esp_err_t test_node_app_init(void) {
    esp_err_t err;
    char wifi_ssid[CONFIG_STORAGE_MAX_STRING_LEN];
    char wifi_password[CONFIG_STORAGE_MAX_STRING_LEN];
    char mqtt_host[CONFIG_STORAGE_MAX_STRING_LEN];
    char mqtt_username[CONFIG_STORAGE_MAX_STRING_LEN];
    char mqtt_password[CONFIG_STORAGE_MAX_STRING_LEN];
    char node_id[64];
    char gh_uid[CONFIG_STORAGE_MAX_STRING_LEN];
    char zone_uid[CONFIG_STORAGE_MAX_STRING_LEN];
    wifi_manager_config_t wifi_config = {0};
    mqtt_manager_config_t mqtt_config = {0};
    mqtt_node_info_t mqtt_node_info = {0};

    s_start_time_seconds = get_timestamp_seconds();
    s_factory_reset_pending = false;
    s_state_command_fastpath_enabled = false;
    s_last_non_state_command_rx_ms = 0;
    s_wildcard_subscribe_warned = false;
    test_node_ui_set_mode("BOOT");
    test_node_ui_set_wifi_status(false, "X");
    test_node_ui_set_mqtt_status(false, "X");
    test_node_ui_show_step("App init: config_storage_init");

    err = config_storage_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "config_storage_init failed: %s", esp_err_to_name(err));
        test_node_ui_show_step("App init: config_storage_init FAILED");
        return err;
    }
    test_node_ui_show_step("App init: config_storage_init OK");

    test_node_ui_show_step("App init: config_storage_load");
    if (config_storage_load() != ESP_OK || !has_valid_network_config()) {
        test_node_ui_show_step("App init: no config, entering setup");
        err = run_setup_portal_blocking();
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "setup_portal_run_full_setup failed: %s", esp_err_to_name(err));
            test_node_ui_show_step("Setup portal FAILED");
            return err;
        }
        test_node_ui_show_step("Setup portal done, continue init");
    }

    test_node_ui_show_step("App init: wifi_manager_init");
    err = wifi_manager_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "wifi_manager_init failed: %s", esp_err_to_name(err));
        test_node_ui_show_step("App init: wifi_manager_init FAILED");
        return err;
    }
    test_node_ui_show_step("App init: wifi_manager_init OK");
    wifi_manager_register_connection_cb(wifi_connected_callback, NULL);
    test_node_ui_register_settings_action_cb(handle_ui_settings_action, NULL);

    test_node_ui_show_step("App init: load WiFi config");
    err = node_utils_init_wifi_config(&wifi_config, wifi_ssid, wifi_password);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "WiFi config unavailable, running setup mode");
        test_node_ui_show_step("WiFi config missing, setup mode");
        return run_setup_portal_blocking();
    }
    test_node_ui_set_wifi_status(false, wifi_ssid);

    test_node_ui_show_step("App init: WiFi connect");
    err = wifi_manager_connect(&wifi_config);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "wifi_manager_connect failed (%s), running setup mode", esp_err_to_name(err));
        test_node_ui_show_step("WiFi connect FAILED, setup mode");
        return run_setup_portal_blocking();
    }
    test_node_ui_show_step("App init: WiFi connect requested");
    test_node_ui_set_wifi_status(false, wifi_ssid);

    test_node_ui_show_step("App init: load MQTT config");
    err = node_utils_init_mqtt_config(
        &mqtt_config,
        &mqtt_node_info,
        mqtt_host,
        mqtt_username,
        mqtt_password,
        node_id,
        gh_uid,
        zone_uid,
        DEFAULT_GH_UID,
        DEFAULT_ZONE_UID,
        DEFAULT_MQTT_NODE_UID
    );

    if (err != ESP_OK) {
        ESP_LOGW(TAG, "MQTT config invalid, running setup mode");
        test_node_ui_show_step("MQTT config invalid, setup mode");
        return run_setup_portal_blocking();
    }
    test_node_ui_show_step("App init: MQTT config OK");

    if (should_boot_in_preconfig_mode(gh_uid, zone_uid)) {
        reset_runtime_namespace_to_preconfig(
            &mqtt_node_info,
            gh_uid,
            sizeof(gh_uid),
            zone_uid,
            sizeof(zone_uid)
        );
        test_node_ui_show_step("App init: preconfig namespace set");
    } else {
        ESP_LOGI(TAG, "Namespace restored from config storage: %s/%s", gh_uid, zone_uid);
        test_node_ui_show_step("App init: namespace restored");
    }

    s_topic_mutex = xSemaphoreCreateMutex();
    if (!s_topic_mutex) {
        ESP_LOGE(TAG, "Failed to create topic mutex");
        test_node_ui_show_step("App init: topic mutex FAILED");
        cleanup_init_runtime_resources();
        return ESP_ERR_NO_MEM;
    }
    test_node_ui_show_step("App init: topic mutex OK");

    init_virtual_namespaces(mqtt_node_info.gh_uid, mqtt_node_info.zone_uid);
    ui_sync_all_virtual_nodes(true);

    s_command_queue = xQueueCreate(COMMAND_QUEUE_LENGTH, sizeof(pending_command_t));
    if (!s_command_queue) {
        ESP_LOGE(TAG, "Failed to create command queue");
        test_node_ui_show_step("App init: command queue FAILED");
        cleanup_init_runtime_resources();
        return ESP_ERR_NO_MEM;
    }
    test_node_ui_show_step("App init: command queue OK");

    s_state_command_queue = xQueueCreate(STATE_COMMAND_QUEUE_LENGTH, sizeof(pending_command_t));
    if (!s_state_command_queue) {
        ESP_LOGW(TAG, "Failed to create state command queue, fallback to command queue priority path");
        test_node_ui_show_step("App init: state queue fallback");
    } else {
        test_node_ui_show_step("App init: state queue OK");
    }

    test_node_ui_show_step("App init: mqtt_manager_init");
    err = mqtt_manager_init(&mqtt_config, &mqtt_node_info);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "mqtt_manager_init failed: %s", esp_err_to_name(err));
        test_node_ui_show_step("App init: mqtt_manager_init FAILED");
        cleanup_init_runtime_resources();
        return err;
    }
    test_node_ui_show_step("App init: mqtt_manager_init OK");

    mqtt_manager_register_command_cb(command_callback, NULL);
    mqtt_manager_register_config_cb(config_callback, NULL);
    mqtt_manager_register_connection_cb(mqtt_connected_callback, NULL);

    err = mqtt_manager_start();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "mqtt_manager_start failed: %s", esp_err_to_name(err));
        test_node_ui_show_step("App init: mqtt_manager_start FAILED");
        cleanup_init_runtime_resources();
        return err;
    }
    test_node_ui_show_step("App init: MQTT service started");
    test_node_ui_set_mqtt_status(false, "...");

    // Критичные задачи (без них UI/зоны/логи не будут обновляться)
    err = start_worker_task(
        command_worker_task,
        "command_worker",
        TASK_STACK_COMMAND_WORKER,
        TASK_STACK_COMMAND_WORKER_FALLBACK,
        6,
        true
    );
    if (err != ESP_OK) {
        cleanup_init_runtime_resources();
        return err;
    }

    if (s_state_command_queue) {
        err = start_worker_task(
            state_command_worker_task,
            "state_cmd_worker",
            TASK_STACK_STATE_COMMAND_WORKER,
            TASK_STACK_STATE_COMMAND_WORKER_FALLBACK,
            7,
            false
        );
        if (err == ESP_OK) {
            s_state_command_fastpath_enabled = true;
            test_node_ui_show_step("App init: state fastpath ON");
        } else {
            s_state_command_fastpath_enabled = false;
            vQueueDelete(s_state_command_queue);
            s_state_command_queue = NULL;
            test_node_ui_show_step("App init: state fastpath OFF");
        }
    }

    err = start_worker_task(
        task_publish_telemetry,
        "telemetry_task",
        TASK_STACK_TELEMETRY,
        TASK_STACK_TELEMETRY_FALLBACK,
        5,
        true
    );
    if (err != ESP_OK) {
        cleanup_init_runtime_resources();
        return err;
    }
    // task_ui_state_sync перенесён в telemetry_task (экономия heap под OOM).

    // Heartbeat и periodic config_report выполняются внутри telemetry_task
    // (уменьшаем число RTOS-задач, чтобы убрать OOM на старте).

    test_node_ui_show_step("App init: worker tasks started (checked)");

    {
        char base_gh_uid[64] = {0};
        char base_zone_uid[64] = {0};
        bool base_preconfig_mode = false;
        if (!get_node_namespace(
            VIRTUAL_NODES[0].node_uid,
            base_gh_uid,
            sizeof(base_gh_uid),
            base_zone_uid,
            sizeof(base_zone_uid),
            &base_preconfig_mode
        )) {
            snprintf(base_gh_uid, sizeof(base_gh_uid), "unknown");
            snprintf(base_zone_uid, sizeof(base_zone_uid), "unknown");
        }

        ESP_LOGI(
            TAG,
            "Test node initialized: virtual_nodes=%u base_namespace=%s/%s mode=%s",
            (unsigned)VIRTUAL_NODE_COUNT,
            base_gh_uid,
            base_zone_uid,
            base_preconfig_mode ? "setup/preconfig" : "configured"
        );
    }
    test_node_ui_show_step("App init: completed");
    test_node_ui_set_mode("RUN");
    return ESP_OK;
}
