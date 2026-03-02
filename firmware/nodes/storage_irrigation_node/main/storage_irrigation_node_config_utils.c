#include "storage_irrigation_node_config_utils.h"
#include "storage_irrigation_node_channel_map.h"
#include "node_config_utils.h"
#include "config_storage.h"
#include "cJSON.h"
#include <string.h>
#include <stdlib.h>

static bool storage_irrigation_node_channels_match(const cJSON *channels) {
    if (!channels || !cJSON_IsArray(channels)) {
        return false;
    }

    const int expected_count =
        (int)(STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT + STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT);
    if (cJSON_GetArraySize(channels) != expected_count) {
        return false;
    }

    bool found_sensor[STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT];
    bool found_actuator[STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT];
    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT; i++) {
        found_sensor[i] = false;
    }
    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT; i++) {
        found_actuator[i] = false;
    }

    const int actual_count = cJSON_GetArraySize(channels);
    for (int i = 0; i < actual_count; i++) {
        const cJSON *entry = cJSON_GetArrayItem(channels, i);
        if (!entry || !cJSON_IsObject(entry)) {
            continue;
        }

        const cJSON *name_item = cJSON_GetObjectItem(entry, "name");
        const cJSON *channel_item = cJSON_GetObjectItem(entry, "channel");
        const cJSON *gpio_item = cJSON_GetObjectItem(entry, "gpio");
        const cJSON *active_low_item = cJSON_GetObjectItem(entry, "active_low");

        const char *name = cJSON_IsString(name_item) ? name_item->valuestring : NULL;
        const char *channel = cJSON_IsString(channel_item) ? channel_item->valuestring : NULL;
        const char *key = name ? name : channel;
        if (!key) {
            continue;
        }

        for (size_t s = 0; s < STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT; s++) {
            if (strcmp(key, STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[s].name) == 0 &&
                cJSON_IsNumber(gpio_item) &&
                (int)cJSON_GetNumberValue(gpio_item) == STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[s].gpio) {
                if (active_low_item && cJSON_IsBool(active_low_item)) {
                    if ((bool)cJSON_IsTrue(active_low_item) != STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[s].active_low) {
                        continue;
                    }
                }
                found_sensor[s] = true;
            }
        }
        for (size_t a = 0; a < STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT; a++) {
            if (strcmp(key, STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS[a].name) == 0 &&
                cJSON_IsNumber(gpio_item) &&
                (int)cJSON_GetNumberValue(gpio_item) == STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS[a].gpio) {
                found_actuator[a] = true;
            }
        }
    }

    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT; i++) {
        if (!found_sensor[i]) {
            return false;
        }
    }
    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT; i++) {
        if (!found_actuator[i]) {
            return false;
        }
    }

    return true;
}

char *storage_irrigation_node_build_patched_config(const char *json, size_t len, bool force_replace, bool *changed) {
    return node_config_utils_build_patched_config(
        json,
        len,
        force_replace,
        storage_irrigation_node_channels_match,
        storage_irrigation_node_build_config_channels,
        changed
    );
}

esp_err_t storage_irrigation_node_patch_stored_config(bool force_replace, bool *changed) {
    if (changed) {
        *changed = false;
    }

    static char config_json[CONFIG_STORAGE_MAX_JSON_SIZE];
    esp_err_t err = config_storage_get_json(config_json, sizeof(config_json));
    if (err != ESP_OK) {
        return err;
    }

    bool local_changed = false;
    char *patched = storage_irrigation_node_build_patched_config(
        config_json,
        strlen(config_json),
        force_replace,
        &local_changed
    );
    if (!patched) {
        return ESP_OK;
    }

    err = config_storage_save(patched, strlen(patched));
    free(patched);
    if (err != ESP_OK) {
        return err;
    }

    if (changed) {
        *changed = local_changed;
    }
    return ESP_OK;
}
