/**
 * @file test_node_app.c
 * @brief ESP32 тест-нода, эмулирующая 6 виртуальных узлов Hydro 2.0
 */

#include "test_node_app.h"
#include "mqtt_manager.h"
#include "config_storage.h"
#include "wifi_manager.h"
#include "setup_portal.h"
#include "test_node_ui.h"
#include "node_utils.h"
#include "esp_log.h"
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

static const char *TAG = "test_node_multi";

#define DEFAULT_MQTT_NODE_UID "nd-test-irrig-1"
#define DEFAULT_GH_UID "gh-test-1"
#define DEFAULT_ZONE_UID "zn-test-1"
#define PRECONFIG_GH_UID "gh-temp"
#define PRECONFIG_ZONE_UID "zn-temp"

#define TELEMETRY_INTERVAL_MS 5000
#define CONFIG_REPORT_INTERVAL_MS 30000
#define COMMAND_QUEUE_LENGTH 32
#define COMMAND_WILDCARD_TOPIC "hydro/+/+/+/+/command"
#define CONFIG_WILDCARD_TOPIC "hydro/+/+/+/config"
#define TASK_STACK_TELEMETRY 4096
#define TASK_STACK_TELEMETRY_FALLBACK 3584
#define TASK_STACK_COMMAND_WORKER 6144
#define TASK_STACK_COMMAND_WORKER_FALLBACK 5632

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
    float air_temp;
    float air_humidity;
    float light_level;

    bool irrigation_on;
    bool tank_fill_on;
    bool tank_drain_on;
    bool fan_on;
    bool light_on;

    uint8_t light_pwm;
    uint8_t irrigation_boost_ticks;
    uint8_t correction_boost_ticks;
} virtual_state_t;

typedef enum {
    COMMAND_KIND_SENSOR_PROBE = 0,
    COMMAND_KIND_ACTUATOR = 1,
    COMMAND_KIND_CONFIG_REPORT = 2,
    COMMAND_KIND_RESTART = 3,
    COMMAND_KIND_GENERIC = 4,
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

    int execute_delay_ms;
} pending_command_t;

static const channel_def_t IRRIGATION_CHANNELS[] = {
    {.name = "pump_irrigation", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "flow_present", .type = "SENSOR", .metric = "FLOW_RATE", .is_actuator = false},
    {.name = "pump_bus_current", .type = "SENSOR", .metric = "PUMP_CURRENT", .is_actuator = false},
};

static const channel_def_t PH_CORRECTION_CHANNELS[] = {
    {.name = "ph_sensor", .type = "SENSOR", .metric = "PH", .is_actuator = false},
    {.name = "pump_acid", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "pump_base", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
};

static const channel_def_t EC_CORRECTION_CHANNELS[] = {
    {.name = "ec_sensor", .type = "SENSOR", .metric = "EC", .is_actuator = false},
    {.name = "pump_a", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "pump_b", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "pump_c", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "pump_d", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
};

static const channel_def_t ACCUMULATION_CHANNELS[] = {
    {.name = "water_level", .type = "SENSOR", .metric = "WATER_LEVEL", .is_actuator = false},
    {.name = "pump_in", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
    {.name = "drain_main", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
};

static const channel_def_t CLIMATE_CHANNELS[] = {
    {.name = "air_temp_c", .type = "SENSOR", .metric = "TEMPERATURE", .is_actuator = false},
    {.name = "air_rh", .type = "SENSOR", .metric = "HUMIDITY", .is_actuator = false},
    {.name = "fan_air", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
};

static const channel_def_t LIGHT_CHANNELS[] = {
    {.name = "light_level", .type = "SENSOR", .metric = "LIGHT_INTENSITY", .is_actuator = false},
    {.name = "white_light", .type = "ACTUATOR", .metric = NULL, .is_actuator = true},
};

static const virtual_node_t VIRTUAL_NODES[] = {
    {.node_uid = "nd-test-irrig-1", .node_type = "pump_node", .channels = IRRIGATION_CHANNELS, .channels_count = sizeof(IRRIGATION_CHANNELS) / sizeof(IRRIGATION_CHANNELS[0])},
    {.node_uid = "nd-test-ph-1", .node_type = "ph_node", .channels = PH_CORRECTION_CHANNELS, .channels_count = sizeof(PH_CORRECTION_CHANNELS) / sizeof(PH_CORRECTION_CHANNELS[0])},
    {.node_uid = "nd-test-ec-1", .node_type = "ec_node", .channels = EC_CORRECTION_CHANNELS, .channels_count = sizeof(EC_CORRECTION_CHANNELS) / sizeof(EC_CORRECTION_CHANNELS[0])},
    {.node_uid = "nd-test-tank-1", .node_type = "water_sensor_node", .channels = ACCUMULATION_CHANNELS, .channels_count = sizeof(ACCUMULATION_CHANNELS) / sizeof(ACCUMULATION_CHANNELS[0])},
    {.node_uid = "nd-test-climate-1", .node_type = "climate_node", .channels = CLIMATE_CHANNELS, .channels_count = sizeof(CLIMATE_CHANNELS) / sizeof(CLIMATE_CHANNELS[0])},
    {.node_uid = "nd-test-light-1", .node_type = "lighting_node", .channels = LIGHT_CHANNELS, .channels_count = sizeof(LIGHT_CHANNELS) / sizeof(LIGHT_CHANNELS[0])},
};

#define VIRTUAL_NODE_COUNT (sizeof(VIRTUAL_NODES) / sizeof(VIRTUAL_NODES[0]))

typedef struct {
    char gh_uid[64];
    char zone_uid[64];
    bool preconfig_mode;
} virtual_node_namespace_t;

static virtual_node_namespace_t s_virtual_namespaces[VIRTUAL_NODE_COUNT] = {0};
static int64_t s_start_time_seconds = 0;
static uint32_t s_telemetry_tick = 0;
static QueueHandle_t s_command_queue = NULL;
static SemaphoreHandle_t s_topic_mutex = NULL;
static bool s_wildcard_subscriptions_ready = false;

static virtual_state_t s_virtual_state = {
    .flow_rate = 0.0f,
    .pump_bus_current = 150.0f,
    .ph_value = 5.80f,
    .ec_value = 1.70f,
    .water_level = 0.62f,
    .air_temp = 24.0f,
    .air_humidity = 60.0f,
    .light_level = 18000.0f,
    .irrigation_on = false,
    .tank_fill_on = false,
    .tank_drain_on = false,
    .fan_on = false,
    .light_on = false,
    .light_pwm = 0,
    .irrigation_boost_ticks = 0,
    .correction_boost_ticks = 0,
};

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

    ESP_LOGI(TAG, "UI_LOG [%s] %s", origin, line);
    test_node_ui_log_event(node_uid, line);
}

static int64_t get_timestamp_seconds(void) {
    return esp_timer_get_time() / 1000000LL;
}

static int64_t get_timestamp_ms(void) {
    return esp_timer_get_time() / 1000LL;
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

static void publish_all_config_reports(const char *reason);

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
    cJSON *json;

    if (!mqtt_manager_is_connected()) {
        return;
    }

    if (build_topic(topic, sizeof(topic), node_uid, channel, "telemetry") != ESP_OK) {
        ESP_LOGE(TAG, "Failed to build telemetry topic for %s/%s", node_uid, channel);
        return;
    }

    json = cJSON_CreateObject();
    if (!json) {
        return;
    }

    cJSON_AddStringToObject(json, "metric_type", metric_type);
    cJSON_AddNumberToObject(json, "value", value);
    cJSON_AddNumberToObject(json, "ts", (double)get_timestamp_seconds());
    cJSON_AddBoolToObject(json, "stub", true);

    publish_json_payload(topic, json, 1, 0);
    ui_logf(
        node_uid,
        "tel %s/%s=%.2f",
        channel ? channel : "-",
        metric_type ? metric_type : "-",
        (double)value
    );
    cJSON_Delete(json);
}

static void publish_config_report_for_node(const virtual_node_t *node) {
    char topic[192];
    char payload_buf[1536];
    char gh_uid[64] = {0};
    char zone_uid[64] = {0};
    bool node_preconfig_mode = false;
    cJSON *json;
    cJSON *channels;
    esp_err_t publish_err;
    size_t index;

    if (!node) {
        return;
    }

    if (build_topic(topic, sizeof(topic), node->node_uid, NULL, "config_report") != ESP_OK) {
        ESP_LOGE(TAG, "Failed to build config_report topic for %s", node->node_uid);
        return;
    }

    json = cJSON_CreateObject();
    if (!json) {
        return;
    }

    if (!get_node_namespace(node->node_uid, gh_uid, sizeof(gh_uid), zone_uid, sizeof(zone_uid), &node_preconfig_mode)) {
        ESP_LOGW(TAG, "Failed to resolve namespace for config_report node=%s", node->node_uid);
        cJSON_Delete(json);
        return;
    }

    cJSON_AddStringToObject(json, "node_id", node->node_uid);
    cJSON_AddNumberToObject(json, "version", 3);
    cJSON_AddStringToObject(json, "type", node->node_type);
    cJSON_AddStringToObject(json, "gh_uid", gh_uid);
    cJSON_AddStringToObject(json, "zone_uid", zone_uid);

    channels = cJSON_CreateArray();
    if (!channels) {
        cJSON_Delete(json);
        return;
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
            cJSON_AddStringToObject(channel_json, "actuator_type", resolve_actuator_type(channel->name));
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

    publish_err = ESP_FAIL;
    for (int attempt = 0; attempt < 3; attempt++) {
        publish_err = publish_json_payload_preallocated(
            topic,
            json,
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

    cJSON_Delete(json);
}

static void publish_all_config_reports(const char *reason) {
    size_t index;
    const char *source = reason ? reason : "unknown";

    if (!mqtt_manager_is_connected()) {
        return;
    }

    for (index = 0; index < (sizeof(VIRTUAL_NODES) / sizeof(VIRTUAL_NODES[0])); index++) {
        publish_config_report_for_node(&VIRTUAL_NODES[index]);
    }

    ESP_LOGI(TAG, "config_report batch published for all virtual nodes (reason=%s)", source);
}

static const char *resolve_node_hello_type(const virtual_node_t *node) {
    if (!node || !node->node_uid) {
        return "unknown";
    }

    if (strstr(node->node_uid, "-ph-") != NULL) {
        return "ph";
    }
    if (strstr(node->node_uid, "-ec-") != NULL) {
        return "ec";
    }
    if (strstr(node->node_uid, "-climate-") != NULL) {
        return "climate";
    }
    if (strstr(node->node_uid, "-light-") != NULL) {
        return "light";
    }
    if (strstr(node->node_uid, "-irrig-") != NULL || strstr(node->node_uid, "-tank-") != NULL) {
        return "pump";
    }

    return "unknown";
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
    if (strstr(node->node_uid, "-tank-") != NULL) {
        return "Test: accumulation node";
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

static void publish_command_response(
    const char *node_uid,
    const char *channel,
    const char *cmd_id,
    const char *status,
    cJSON *details
) {
    char topic[192];
    cJSON *json = cJSON_CreateObject();
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
        publish_json_payload(topic, json, 1, 0);
        ui_logf(node_uid, "cmd_resp %s %s", status ? status : "?", channel ? channel : "-");
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

static int resolve_command_delay_ms(command_kind_t kind, cJSON *params) {
    int delay_ms = 900;
    cJSON *ttl_ms = NULL;

    if (kind == COMMAND_KIND_SENSOR_PROBE) {
        return 350;
    }
    if (kind == COMMAND_KIND_CONFIG_REPORT) {
        return 200;
    }
    if (kind == COMMAND_KIND_RESTART) {
        return 1500;
    }

    if (params && cJSON_IsObject(params)) {
        ttl_ms = cJSON_GetObjectItem(params, "ttl_ms");
        if (ttl_ms && cJSON_IsNumber(ttl_ms)) {
            delay_ms = (int)cJSON_GetNumberValue(ttl_ms);
        }
    }

    if (delay_ms < 250) {
        delay_ms = 250;
    }
    if (delay_ms > 4000) {
        delay_ms = 4000;
    }

    return delay_ms;
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
    } else {
        cJSON *duration = cJSON_GetObjectItem(params, "duration_ms");
        if (duration && cJSON_IsNumber(duration)) {
            job->amount_present = true;
            job->amount_value = (float)cJSON_GetNumberValue(duration);
        }
    }

    job->execute_delay_ms = resolve_command_delay_ms(job->kind, params);
}

static void update_virtual_state_from_command(const pending_command_t *job, cJSON *details, const char **status_out) {
    const char *status = "DONE";

    if (!job || !status_out) {
        return;
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

    if (strcmp(job->channel, "pump_irrigation") == 0) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            s_virtual_state.irrigation_on = job->relay_state;
        } else if (strcmp(job->cmd, "run_pump") == 0 || strcmp(job->cmd, "dose") == 0) {
            s_virtual_state.irrigation_boost_ticks = 3;
        }
    } else if (strcmp(job->channel, "pump_in") == 0) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            s_virtual_state.tank_fill_on = job->relay_state;
        } else if (strcmp(job->cmd, "run_pump") == 0 || strcmp(job->cmd, "dose") == 0) {
            s_virtual_state.water_level = clamp_float(s_virtual_state.water_level + 0.02f, 0.05f, 0.98f);
        }
    } else if (strcmp(job->channel, "drain_main") == 0) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            s_virtual_state.tank_drain_on = job->relay_state;
        } else if (strcmp(job->cmd, "run_pump") == 0 || strcmp(job->cmd, "dose") == 0) {
            s_virtual_state.water_level = clamp_float(s_virtual_state.water_level - 0.02f, 0.05f, 0.98f);
        }
    } else if (strcmp(job->channel, "pump_acid") == 0) {
        s_virtual_state.ph_value = clamp_float(s_virtual_state.ph_value - 0.03f, 4.8f, 7.2f);
        s_virtual_state.correction_boost_ticks = 2;
    } else if (strcmp(job->channel, "pump_base") == 0) {
        s_virtual_state.ph_value = clamp_float(s_virtual_state.ph_value + 0.03f, 4.8f, 7.2f);
        s_virtual_state.correction_boost_ticks = 2;
    } else if (
        strcmp(job->channel, "pump_a") == 0 ||
        strcmp(job->channel, "pump_b") == 0 ||
        strcmp(job->channel, "pump_c") == 0 ||
        strcmp(job->channel, "pump_d") == 0
    ) {
        s_virtual_state.ec_value = clamp_float(s_virtual_state.ec_value + 0.05f, 0.4f, 3.2f);
        s_virtual_state.correction_boost_ticks = 2;
    } else if (strcmp(job->channel, "fan_air") == 0) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            s_virtual_state.fan_on = job->relay_state;
        }
    } else if (strcmp(job->channel, "white_light") == 0) {
        if (strcmp(job->cmd, "set_relay") == 0) {
            s_virtual_state.light_on = job->relay_state;
            if (!job->relay_state) {
                s_virtual_state.light_pwm = 0;
            }
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
        }
    }

    if (job->amount_present) {
        cJSON_AddNumberToObject(details, "amount", job->amount_value);
    }

    *status_out = status;
}

static void execute_pending_command(const pending_command_t *job) {
    const virtual_node_t *node;
    cJSON *details;
    const char *final_status = "DONE";

    if (!job) {
        return;
    }

    node = find_virtual_node(job->node_uid);
    if (!node) {
        return;
    }

    details = cJSON_CreateObject();
    if (!details) {
        return;
    }

    cJSON_AddBoolToObject(details, "virtual", true);
    cJSON_AddStringToObject(details, "node_uid", job->node_uid);
    cJSON_AddStringToObject(details, "channel", job->channel);
    cJSON_AddStringToObject(details, "cmd", job->cmd);
    cJSON_AddNumberToObject(details, "exec_delay_ms", job->execute_delay_ms);
    ui_logf(job->node_uid, "cmd run %s/%s dly=%d", job->channel, job->cmd, job->execute_delay_ms);

    if (job->kind == COMMAND_KIND_SENSOR_PROBE) {
        cJSON *probe = build_sensor_probe_details(job->channel);
        if (probe) {
            cJSON_AddItemToObject(details, "probe", probe);
        }
    } else if (job->kind == COMMAND_KIND_CONFIG_REPORT) {
        publish_config_report_for_node(node);
        cJSON_AddStringToObject(details, "note", "config_report_published");
    } else if (job->kind == COMMAND_KIND_RESTART) {
        publish_status_for_node(job->node_uid, "RESTARTING");
        vTaskDelay(pdMS_TO_TICKS(450));
        publish_status_for_node(job->node_uid, "ONLINE");
        cJSON_AddStringToObject(details, "note", "virtual_restart_done");
    } else if (job->kind == COMMAND_KIND_ACTUATOR) {
        update_virtual_state_from_command(job, details, &final_status);
    } else {
        cJSON_AddStringToObject(details, "note", "virtual_noop");
    }

    publish_command_response(job->node_uid, job->channel, job->cmd_id, final_status, details);
    ui_logf(job->node_uid, "cmd done %s/%s -> %s", job->channel, job->cmd, final_status);
    cJSON_Delete(details);
}

static void command_worker_task(void *pv_parameters) {
    pending_command_t job;
    (void)pv_parameters;

    ESP_LOGI(TAG, "Command worker started");

    while (1) {
        if (xQueueReceive(s_command_queue, &job, portMAX_DELAY) == pdTRUE) {
            if (job.execute_delay_ms > 0) {
                vTaskDelay(pdMS_TO_TICKS(job.execute_delay_ms));
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
        strcmp(cmd_name, "dose") == 0
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
    const char *cmd_id;
    const char *cmd_name;
    const virtual_node_t *node;
    pending_command_t job;

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
        if (!get_node_namespace(node_uid, current_gh_uid, sizeof(current_gh_uid), current_zone_uid, sizeof(current_zone_uid), NULL)) {
            snprintf(current_gh_uid, sizeof(current_gh_uid), "unknown");
            snprintf(current_zone_uid, sizeof(current_zone_uid), "unknown");
        }
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

    node = find_virtual_node(node_uid);
    if (!node) {
        return;
    }

    command_json = cJSON_ParseWithLength(data, data_len);
    if (!command_json) {
        cJSON *details = cJSON_CreateObject();
        if (details) {
            cJSON_AddStringToObject(details, "error", "invalid_json");
            publish_command_response(node_uid, topic_channel, "unknown", "INVALID", details);
            cJSON_Delete(details);
        }
        ui_logf(node_uid, "cmd invalid_json");
        return;
    }

    cmd_id_item = cJSON_GetObjectItem(command_json, "cmd_id");
    cmd_item = cJSON_GetObjectItem(command_json, "cmd");
    cmd_id = (cmd_id_item && cJSON_IsString(cmd_id_item) && cmd_id_item->valuestring) ? cmd_id_item->valuestring : "unknown";
    cmd_name = (cmd_item && cJSON_IsString(cmd_item) && cmd_item->valuestring) ? cmd_item->valuestring : "";

    if (cmd_name[0] == '\0') {
        cJSON *details = cJSON_CreateObject();
        if (details) {
            cJSON_AddStringToObject(details, "error", "missing_cmd");
            publish_command_response(node_uid, topic_channel, cmd_id, "INVALID", details);
            cJSON_Delete(details);
        }
        ui_logf(node_uid, "cmd missing_cmd");
        cJSON_Delete(command_json);
        return;
    }

    memset(&job, 0, sizeof(job));
    snprintf(job.node_uid, sizeof(job.node_uid), "%s", node_uid);
    snprintf(job.channel, sizeof(job.channel), "%s", topic_channel);
    snprintf(job.cmd_id, sizeof(job.cmd_id), "%s", cmd_id);
    snprintf(job.cmd, sizeof(job.cmd), "%s", cmd_name);
    job.kind = resolve_command_kind(cmd_name);
    job.execute_delay_ms = resolve_command_delay_ms(job.kind, NULL);

    extract_command_params(command_json, &job);

    publish_command_response(node_uid, topic_channel, cmd_id, "ACK", NULL);
    ui_logf(node_uid, "cmd ack %s/%s", topic_channel, cmd_name);

    if (!s_command_queue || xQueueSend(s_command_queue, &job, 0) != pdTRUE) {
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
        TAG,
        "Virtual command accepted: node=%s channel=%s cmd=%s cmd_id=%s",
        node_uid,
        channel ? channel : topic_channel,
        cmd_name,
        cmd_id
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

    if (
        !current_preconfig_mode &&
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
    float drift = ((float)(s_telemetry_tick % 11) - 5.0f) * 0.002f;

    s_virtual_state.ph_value = clamp_float(s_virtual_state.ph_value + drift, 4.8f, 7.2f);
    s_virtual_state.ec_value = clamp_float(s_virtual_state.ec_value + (drift * 4.0f), 0.4f, 3.2f);

    if (s_virtual_state.tank_fill_on) {
        s_virtual_state.water_level = clamp_float(s_virtual_state.water_level + 0.008f, 0.05f, 0.98f);
    }
    if (s_virtual_state.tank_drain_on) {
        s_virtual_state.water_level = clamp_float(s_virtual_state.water_level - 0.008f, 0.05f, 0.98f);
    }

    if (s_virtual_state.fan_on) {
        s_virtual_state.air_temp = clamp_float(s_virtual_state.air_temp - 0.05f, 18.0f, 32.0f);
        s_virtual_state.air_humidity = clamp_float(s_virtual_state.air_humidity - 0.08f, 35.0f, 90.0f);
    } else {
        s_virtual_state.air_temp = clamp_float(s_virtual_state.air_temp + 0.02f, 18.0f, 32.0f);
        s_virtual_state.air_humidity = clamp_float(s_virtual_state.air_humidity + 0.03f, 35.0f, 90.0f);
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

    s_virtual_state.flow_rate = s_virtual_state.irrigation_on ? 1.20f : 0.0f;
    if (s_virtual_state.irrigation_boost_ticks > 0) {
        s_virtual_state.flow_rate += 0.40f;
        s_virtual_state.irrigation_boost_ticks--;
    }

    s_virtual_state.pump_bus_current = 120.0f;
    if (s_virtual_state.irrigation_on) {
        s_virtual_state.pump_bus_current += 80.0f;
    }
    if (s_virtual_state.tank_fill_on || s_virtual_state.tank_drain_on) {
        s_virtual_state.pump_bus_current += 70.0f;
    }
    if (s_virtual_state.correction_boost_ticks > 0) {
        s_virtual_state.pump_bus_current += 50.0f;
        s_virtual_state.correction_boost_ticks--;
    }
}

static void publish_virtual_telemetry_batch(void) {
    apply_passive_drift();

    publish_telemetry_for_node("nd-test-irrig-1", "flow_present", "FLOW_RATE", s_virtual_state.flow_rate);
    publish_telemetry_for_node("nd-test-irrig-1", "pump_bus_current", "PUMP_CURRENT", s_virtual_state.pump_bus_current);

    publish_telemetry_for_node("nd-test-ph-1", "ph_sensor", "PH", s_virtual_state.ph_value);
    publish_telemetry_for_node("nd-test-ec-1", "ec_sensor", "EC", s_virtual_state.ec_value);

    publish_telemetry_for_node("nd-test-tank-1", "water_level", "WATER_LEVEL", s_virtual_state.water_level);

    publish_telemetry_for_node("nd-test-climate-1", "air_temp_c", "TEMPERATURE", s_virtual_state.air_temp);
    publish_telemetry_for_node("nd-test-climate-1", "air_rh", "HUMIDITY", s_virtual_state.air_humidity);

    publish_telemetry_for_node("nd-test-light-1", "light_level", "LIGHT_INTENSITY", s_virtual_state.light_level);

    s_telemetry_tick++;
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

        if (mqtt_connected && !s_wildcard_subscriptions_ready) {
            esp_err_t cmd_sub_err = mqtt_manager_subscribe_raw(COMMAND_WILDCARD_TOPIC, 1);
            esp_err_t cfg_sub_err = mqtt_manager_subscribe_raw(CONFIG_WILDCARD_TOPIC, 1);
            if (cmd_sub_err == ESP_OK && cfg_sub_err == ESP_OK) {
                s_wildcard_subscriptions_ready = true;
            }
        }

        if (mqtt_connected) {
            for (index = 0; index < (sizeof(VIRTUAL_NODES) / sizeof(VIRTUAL_NODES[0])); index++) {
                if (!mqtt_manager_is_connected()) {
                    break;
                }
                publish_heartbeat_for_node(VIRTUAL_NODES[index].node_uid);
            }

            config_elapsed_ms += TELEMETRY_INTERVAL_MS;
            if (config_elapsed_ms >= CONFIG_REPORT_INTERVAL_MS) {
                publish_all_config_reports("periodic");
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
        publish_all_config_reports("mqtt_connected");
    }
    test_node_ui_show_step("MQTT connected: virtual nodes ONLINE");

    ESP_LOGI(
        TAG,
        "Virtual nodes ONLINE published (preconfig=%u/%u)",
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

    reset_runtime_namespace_to_preconfig(
        &mqtt_node_info,
        gh_uid,
        sizeof(gh_uid),
        zone_uid,
        sizeof(zone_uid)
    );
    test_node_ui_show_step("App init: preconfig namespace set");

    s_topic_mutex = xSemaphoreCreateMutex();
    if (!s_topic_mutex) {
        ESP_LOGE(TAG, "Failed to create topic mutex");
        test_node_ui_show_step("App init: topic mutex FAILED");
        return ESP_ERR_NO_MEM;
    }
    test_node_ui_show_step("App init: topic mutex OK");

    init_virtual_namespaces(mqtt_node_info.gh_uid, mqtt_node_info.zone_uid);
    ui_sync_all_virtual_nodes(true);

    s_command_queue = xQueueCreate(COMMAND_QUEUE_LENGTH, sizeof(pending_command_t));
    if (!s_command_queue) {
        ESP_LOGE(TAG, "Failed to create command queue");
        test_node_ui_show_step("App init: command queue FAILED");
        return ESP_ERR_NO_MEM;
    }
    test_node_ui_show_step("App init: command queue OK");

    test_node_ui_show_step("App init: mqtt_manager_init");
    err = mqtt_manager_init(&mqtt_config, &mqtt_node_info);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "mqtt_manager_init failed: %s", esp_err_to_name(err));
        test_node_ui_show_step("App init: mqtt_manager_init FAILED");
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
        return err;
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
