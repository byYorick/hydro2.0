#include "light_node_config_utils.h"
#include "light_node_channel_map.h"
#include "node_config_utils.h"
#include "cJSON.h"
#include <string.h>

static bool light_node_channels_match(const cJSON *channels) {
    if (!channels || !cJSON_IsArray(channels)) {
        return false;
    }

    const int array_size = cJSON_GetArraySize(channels);
    if (array_size != (int)LIGHT_NODE_SENSOR_CHANNELS_COUNT) {
        return false;
    }

    bool found[LIGHT_NODE_SENSOR_CHANNELS_COUNT];
    for (size_t i = 0; i < LIGHT_NODE_SENSOR_CHANNELS_COUNT; i++) {
        found[i] = false;
    }

    for (int i = 0; i < array_size; i++) {
        const cJSON *entry = cJSON_GetArrayItem(channels, i);
        if (!entry || !cJSON_IsObject(entry)) {
            continue;
        }
        const cJSON *name_item = cJSON_GetObjectItem(entry, "name");
        const cJSON *channel_item = cJSON_GetObjectItem(entry, "channel");
        const char *name = cJSON_IsString(name_item) ? name_item->valuestring : NULL;
        const char *channel = cJSON_IsString(channel_item) ? channel_item->valuestring : NULL;
        for (size_t idx = 0; idx < LIGHT_NODE_SENSOR_CHANNELS_COUNT; idx++) {
            const char *expected = LIGHT_NODE_SENSOR_CHANNELS[idx].name;
            if ((name && strcmp(name, expected) == 0) || (channel && strcmp(channel, expected) == 0)) {
                found[idx] = true;
            }
        }
    }

    for (size_t i = 0; i < LIGHT_NODE_SENSOR_CHANNELS_COUNT; i++) {
        if (!found[i]) {
            return false;
        }
    }

    return true;
}

char *light_node_build_patched_config(const char *json, size_t len, bool force_replace, bool *changed) {
    return node_config_utils_build_patched_config(
        json,
        len,
        force_replace,
        light_node_channels_match,
        light_node_build_config_channels,
        changed
    );
}
