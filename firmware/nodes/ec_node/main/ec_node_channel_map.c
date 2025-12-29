#include "ec_node_channel_map.h"
#include "ec_node_defaults.h"
#include "cJSON.h"

const ec_node_sensor_channel_t EC_NODE_SENSOR_CHANNELS[] = {
    {
        .name = "ec_sensor",
        .metric = "EC",
        .unit = "mS/cm",
        .poll_interval_ms = EC_NODE_EC_SENSOR_POLL_INTERVAL_MS,
        .precision = EC_NODE_EC_SENSOR_PRECISION
    }
};

const size_t EC_NODE_SENSOR_CHANNELS_COUNT = sizeof(EC_NODE_SENSOR_CHANNELS) / sizeof(EC_NODE_SENSOR_CHANNELS[0]);

const ec_node_actuator_channel_t EC_NODE_ACTUATOR_CHANNELS[] = {
    {
        .name = "pump_nutrient",
        .gpio = EC_NODE_PUMP_NUTRIENT_GPIO,
        .fail_safe_nc = EC_NODE_PUMP_FAIL_SAFE_NC,
        .max_duration_ms = EC_NODE_PUMP_MAX_DURATION_MS,
        .min_off_ms = EC_NODE_PUMP_MIN_OFF_MS,
        .ml_per_second = EC_NODE_PUMP_ML_PER_SECOND
    }
};

const size_t EC_NODE_ACTUATOR_CHANNELS_COUNT = sizeof(EC_NODE_ACTUATOR_CHANNELS) / sizeof(EC_NODE_ACTUATOR_CHANNELS[0]);

static cJSON *ec_node_build_sensor_entry(const ec_node_sensor_channel_t *sensor) {
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

static cJSON *ec_node_build_actuator_entry(const ec_node_actuator_channel_t *actuator) {
    if (actuator == NULL || actuator->name == NULL) {
        return NULL;
    }

    cJSON *entry = cJSON_CreateObject();
    if (!entry) {
        return NULL;
    }

    cJSON_AddStringToObject(entry, "name", actuator->name);
    cJSON_AddStringToObject(entry, "channel", actuator->name);
    cJSON_AddStringToObject(entry, "type", "ACTUATOR");
    cJSON_AddStringToObject(entry, "actuator_type", "PERISTALTIC_PUMP");
    cJSON_AddNumberToObject(entry, "gpio", actuator->gpio);

    cJSON *safe_limits = cJSON_CreateObject();
    if (!safe_limits) {
        cJSON_Delete(entry);
        return NULL;
    }

    cJSON_AddNumberToObject(safe_limits, "max_duration_ms", actuator->max_duration_ms);
    cJSON_AddNumberToObject(safe_limits, "min_off_ms", actuator->min_off_ms);
    cJSON_AddStringToObject(safe_limits, "fail_safe_mode", actuator->fail_safe_nc ? "NC" : "NO");
    cJSON_AddItemToObject(entry, "safe_limits", safe_limits);
    cJSON_AddNumberToObject(entry, "ml_per_second", actuator->ml_per_second);

    return entry;
}

cJSON *ec_node_build_config_channels(void) {
    cJSON *channels = cJSON_CreateArray();
    if (!channels) {
        return NULL;
    }

    for (size_t i = 0; i < EC_NODE_SENSOR_CHANNELS_COUNT; i++) {
        cJSON *entry = ec_node_build_sensor_entry(&EC_NODE_SENSOR_CHANNELS[i]);
        if (!entry) {
            cJSON_Delete(channels);
            return NULL;
        }
        cJSON_AddItemToArray(channels, entry);
    }

    for (size_t i = 0; i < EC_NODE_ACTUATOR_CHANNELS_COUNT; i++) {
        cJSON *entry = ec_node_build_actuator_entry(&EC_NODE_ACTUATOR_CHANNELS[i]);
        if (!entry) {
            cJSON_Delete(channels);
            return NULL;
        }
        cJSON_AddItemToArray(channels, entry);
    }

    return channels;
}
