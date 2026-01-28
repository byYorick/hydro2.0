/**
 * @file init_steps_utils.c
 * @brief Общие утилиты для init-steps нод
 */

#include "init_steps_utils.h"
#include "config_storage.h"
#include "cJSON.h"
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

esp_err_t init_steps_utils_get_config_string(
    const char *key,
    char *buffer,
    size_t buffer_size,
    const char *default_value
) {
    if (key == NULL || buffer == NULL || buffer_size == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t err = ESP_ERR_NOT_FOUND;

    if (strcmp(key, "node_id") == 0) {
        err = config_storage_get_node_id(buffer, buffer_size);
    } else if (strcmp(key, "gh_uid") == 0) {
        err = config_storage_get_gh_uid(buffer, buffer_size);
    } else if (strcmp(key, "zone_uid") == 0) {
        err = config_storage_get_zone_uid(buffer, buffer_size);
    }

    if (err != ESP_OK && default_value != NULL) {
        strncpy(buffer, default_value, buffer_size - 1);
        buffer[buffer_size - 1] = '\0';
        return ESP_OK;
    }

    return err;
}

esp_err_t init_steps_utils_patch_pump_config(
    init_steps_build_channels_fn build_channels,
    uint32_t current_min_ma,
    uint32_t current_max_ma
) {
    static char config_json[CONFIG_STORAGE_MAX_JSON_SIZE];

    if (build_channels == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (config_storage_get_json(config_json, sizeof(config_json)) != ESP_OK) {
        return ESP_ERR_NOT_FOUND;
    }

    cJSON *config = cJSON_Parse(config_json);
    if (!config) {
        return ESP_FAIL;
    }

    bool changed = false;
    cJSON *channels = cJSON_GetObjectItem(config, "channels");
    if (channels == NULL || !cJSON_IsArray(channels) || cJSON_GetArraySize(channels) == 0) {
        if (channels) {
            cJSON_DeleteItemFromObject(config, "channels");
        }
        cJSON *built_channels = build_channels();
        if (!built_channels) {
            cJSON_Delete(config);
            return ESP_ERR_NO_MEM;
        }
        cJSON_AddItemToObject(config, "channels", built_channels);
        changed = true;
    }

    cJSON *limits = cJSON_GetObjectItem(config, "limits");
    if (limits == NULL || !cJSON_IsObject(limits)) {
        if (limits) {
            cJSON_DeleteItemFromObject(config, "limits");
        }
        limits = cJSON_CreateObject();
        if (!limits) {
            cJSON_Delete(config);
            return ESP_ERR_NO_MEM;
        }
        cJSON_AddItemToObject(config, "limits", limits);
        changed = true;
    }

    cJSON *current_min = cJSON_GetObjectItem(limits, "currentMin");
    if (current_min == NULL || !cJSON_IsNumber(current_min)) {
        cJSON_DeleteItemFromObject(limits, "currentMin");
        cJSON_AddNumberToObject(limits, "currentMin", (double)current_min_ma);
        changed = true;
    }

    cJSON *current_max = cJSON_GetObjectItem(limits, "currentMax");
    if (current_max == NULL || !cJSON_IsNumber(current_max)) {
        cJSON_DeleteItemFromObject(limits, "currentMax");
        cJSON_AddNumberToObject(limits, "currentMax", (double)current_max_ma);
        changed = true;
    }

    if (!changed) {
        cJSON_Delete(config);
        return ESP_OK;
    }

    char *patched = cJSON_PrintUnformatted(config);
    cJSON_Delete(config);
    if (!patched) {
        return ESP_ERR_NO_MEM;
    }

    esp_err_t err = config_storage_save(patched, strlen(patched));
    free(patched);
    return err;
}
