#include "light_node_channel_map.h"
#include "light_node_defaults.h"
#include "cJSON.h"

const light_node_sensor_channel_t LIGHT_NODE_SENSOR_CHANNELS[] = {
    {
        .name = "light",
        .metric = "LIGHT",
        .unit = "lux",
        .poll_interval_ms = LIGHT_NODE_LIGHT_SENSOR_POLL_INTERVAL_MS,
        .precision = LIGHT_NODE_LIGHT_SENSOR_PRECISION
    }
};

const size_t LIGHT_NODE_SENSOR_CHANNELS_COUNT =
    sizeof(LIGHT_NODE_SENSOR_CHANNELS) / sizeof(LIGHT_NODE_SENSOR_CHANNELS[0]);

static cJSON *light_node_build_sensor_entry(const light_node_sensor_channel_t *sensor) {
    if (sensor == NULL || sensor->name == NULL || sensor->metric == NULL) {
        return NULL;
    }

    cJSON *entry = cJSON_CreateObject();
    if (!entry) {
        return NULL;
    }

    cJSON_AddStringToObject(entry, "name", sensor->name);
    cJSON_AddStringToObject(entry, "channel", sensor->name);
    cJSON_AddStringToObject(entry, "type", "SENSOR");
    cJSON_AddStringToObject(entry, "metric", sensor->metric);

    if (sensor->unit) {
        cJSON_AddStringToObject(entry, "unit", sensor->unit);
    }
    if (sensor->poll_interval_ms > 0) {
        cJSON_AddNumberToObject(entry, "poll_interval_ms", sensor->poll_interval_ms);
    }
    if (sensor->precision >= 0) {
        cJSON_AddNumberToObject(entry, "precision", sensor->precision);
    }

    return entry;
}

cJSON *light_node_build_config_channels(void) {
    cJSON *channels = cJSON_CreateArray();
    if (!channels) {
        return NULL;
    }

    for (size_t i = 0; i < LIGHT_NODE_SENSOR_CHANNELS_COUNT; i++) {
        cJSON *entry = light_node_build_sensor_entry(&LIGHT_NODE_SENSOR_CHANNELS[i]);
        if (!entry) {
            cJSON_Delete(channels);
            return NULL;
        }
        cJSON_AddItemToArray(channels, entry);
    }

    return channels;
}
