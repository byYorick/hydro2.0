#include "node_config_utils.h"
#include "cJSON.h"

char *node_config_utils_build_patched_config(const char *json,
                                             size_t len,
                                             bool force_replace,
                                             node_config_channels_match_fn match_fn,
                                             node_config_build_channels_fn build_fn,
                                             bool *changed) {
    if (changed) {
        *changed = false;
    }

    if (!json || len == 0 || !build_fn) {
        return NULL;
    }

    cJSON *config = cJSON_ParseWithLength(json, len);
    if (!config) {
        return NULL;
    }

    bool should_replace = force_replace;
    if (!should_replace) {
        cJSON *channels = cJSON_GetObjectItem(config, "channels");
        if (match_fn) {
            should_replace = !match_fn(channels);
        } else {
            should_replace = (channels == NULL || !cJSON_IsArray(channels));
        }
    }

    if (!should_replace) {
        cJSON_Delete(config);
        return NULL;
    }

    cJSON_DeleteItemFromObject(config, "channels");
    cJSON *channels = build_fn();
    if (!channels) {
        cJSON_Delete(config);
        return NULL;
    }
    cJSON_AddItemToObject(config, "channels", channels);

    char *patched = cJSON_PrintUnformatted(config);
    cJSON_Delete(config);

    if (patched && changed) {
        *changed = true;
    }

    return patched;
}
