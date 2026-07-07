/**
 * @file node_link_loss_failsafe.c
 * @brief Link-loss fail-safe: configurable MQTT disconnect timeout → actuator stop.
 */

#include "node_link_loss_failsafe.h"
#include "node_state_manager.h"
#include "node_utils.h"
#include "config_storage.h"
#include "mqtt_manager.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "cJSON.h"
#include <stdlib.h>
#include <string.h>

__attribute__((weak)) void pump_driver_append_active_channels_json(cJSON *pumps_arr) {
    (void)pumps_arr;
}

__attribute__((weak)) void relay_driver_append_active_channels_json(cJSON *relays_arr) {
    (void)relays_arr;
}

static const char *TAG = "node_link_loss";

#define LINK_LOSS_SNAPSHOT_MAX_BYTES 1024

static struct {
    bool initialized;
    uint32_t timeout_sec;
    esp_timer_handle_t timer;
    bool failsafe_triggered;
    bool event_pending;
    char snapshot_json[LINK_LOSS_SNAPSHOT_MAX_BYTES];
} s_link_loss = {0};

static void link_loss_reload_timeout_from_config(void) {
    s_link_loss.timeout_sec = 0;

    static char config_json[CONFIG_STORAGE_MAX_JSON_SIZE];
    if (config_storage_get_json(config_json, sizeof(config_json)) != ESP_OK) {
        return;
    }

    cJSON *config = cJSON_Parse(config_json);
    if (!config) {
        return;
    }

    cJSON *item = cJSON_GetObjectItem(config, "link_loss_timeout_sec");
    if (cJSON_IsNumber(item)) {
        double value = cJSON_GetNumberValue(item);
        if (value > 0.0) {
            s_link_loss.timeout_sec = (uint32_t)value;
        }
    }

    if (s_link_loss.timeout_sec == 0) {
        cJSON *guards = cJSON_GetObjectItem(config, "fail_safe_guards");
        if (cJSON_IsObject(guards)) {
            item = cJSON_GetObjectItem(guards, "link_loss_timeout_sec");
            if (cJSON_IsNumber(item)) {
                double value = cJSON_GetNumberValue(item);
                if (value > 0.0) {
                    s_link_loss.timeout_sec = (uint32_t)value;
                }
            }
        }
    }

    cJSON_Delete(config);
}

static void link_loss_build_snapshot_json(char *out, size_t out_size) {
    if (!out || out_size == 0) {
        return;
    }

    cJSON *root = cJSON_CreateObject();
    if (!root) {
        out[0] = '\0';
        return;
    }

    cJSON_AddNumberToObject(root, "timeout_sec", (double)s_link_loss.timeout_sec);

    cJSON *pumps = cJSON_CreateArray();
    cJSON *relays = cJSON_CreateArray();
    if (pumps) {
        pump_driver_append_active_channels_json(pumps);
        cJSON_AddItemToObject(root, "stopped_pumps", pumps);
    }
    if (relays) {
        relay_driver_append_active_channels_json(relays);
        cJSON_AddItemToObject(root, "stopped_relays", relays);
    }

    char *printed = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!printed) {
        out[0] = '\0';
        return;
    }

    strncpy(out, printed, out_size - 1);
    out[out_size - 1] = '\0';
    free(printed);
}

static void link_loss_timer_callback(void *arg) {
    (void)arg;

    if (mqtt_manager_is_connected()) {
        return;
    }

    ESP_LOGW(TAG, "Link-loss timeout (%u s) expired — invoking actuator fail-safe", (unsigned)s_link_loss.timeout_sec);

    link_loss_build_snapshot_json(s_link_loss.snapshot_json, sizeof(s_link_loss.snapshot_json));

    esp_err_t err = node_state_manager_invoke_actuator_failsafe("link_loss_timeout");
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Actuator fail-safe callback failed: %s", esp_err_to_name(err));
    }

    s_link_loss.failsafe_triggered = true;
    s_link_loss.event_pending = true;
}

static void link_loss_stop_timer(void) {
    if (s_link_loss.timer) {
        (void)esp_timer_stop(s_link_loss.timer);
    }
}

static void link_loss_start_timer(void) {
    if (s_link_loss.timeout_sec == 0 || s_link_loss.timer == NULL) {
        return;
    }

    uint64_t timeout_us = (uint64_t)s_link_loss.timeout_sec * 1000000ULL;
    esp_err_t err = esp_timer_start_once(s_link_loss.timer, timeout_us);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to start link-loss timer: %s", esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "Link-loss timer started (%u s)", (unsigned)s_link_loss.timeout_sec);
    }
}

static void link_loss_publish_pending_event(void) {
    if (!s_link_loss.event_pending || !mqtt_manager_is_connected() || !node_utils_is_time_synced()) {
        return;
    }

    cJSON *snapshot = NULL;
    if (s_link_loss.snapshot_json[0] != '\0') {
        snapshot = cJSON_Parse(s_link_loss.snapshot_json);
    }

    esp_err_t err = node_utils_publish_event("system", "link_loss_failsafe", snapshot);
    if (snapshot) {
        cJSON_Delete(snapshot);
    }

    if (err == ESP_OK) {
        ESP_LOGI(TAG, "Published link_loss_failsafe event");
        s_link_loss.event_pending = false;
        s_link_loss.failsafe_triggered = false;
        s_link_loss.snapshot_json[0] = '\0';
    } else {
        ESP_LOGW(TAG, "Deferred link_loss_failsafe publish: %s", esp_err_to_name(err));
    }
}

esp_err_t node_link_loss_failsafe_init(void) {
    if (s_link_loss.initialized) {
        return ESP_OK;
    }

    const esp_timer_create_args_t timer_args = {
        .callback = &link_loss_timer_callback,
        .name = "link_loss_fs",
    };

    esp_err_t err = esp_timer_create(&timer_args, &s_link_loss.timer);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create timer: %s", esp_err_to_name(err));
        return err;
    }

    link_loss_reload_timeout_from_config();
    s_link_loss.initialized = true;
    ESP_LOGI(TAG, "Link-loss failsafe initialized (timeout_sec=%u)", (unsigned)s_link_loss.timeout_sec);
    return ESP_OK;
}

void node_link_loss_failsafe_reload_config(void) {
    link_loss_reload_timeout_from_config();
    ESP_LOGI(TAG, "Link-loss timeout reloaded: %u s", (unsigned)s_link_loss.timeout_sec);
}

void node_link_loss_failsafe_on_mqtt_connected(bool connected) {
    if (!s_link_loss.initialized) {
        return;
    }

    if (connected) {
        link_loss_stop_timer();
        link_loss_publish_pending_event();
        return;
    }

    s_link_loss.failsafe_triggered = false;
    link_loss_stop_timer();
    link_loss_start_timer();
}
