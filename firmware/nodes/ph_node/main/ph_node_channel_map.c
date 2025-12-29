#include "ph_node_channel_map.h"
#include "ph_node_defaults.h"
#include "cJSON.h"

const ph_node_sensor_channel_t PH_NODE_SENSOR_CHANNELS[] = {
    {
        .name = "ph_sensor",
        .metric = "PH",
        .unit = "pH",
        .poll_interval_ms = PH_NODE_PH_SENSOR_POLL_INTERVAL_MS,
        .precision = PH_NODE_PH_SENSOR_PRECISION
    },
    {
        .name = "solution_temp_c",
        .metric = "TEMP_SOLUTION",
        .unit = "C",
        .poll_interval_ms = PH_NODE_SOLUTION_TEMP_POLL_INTERVAL_MS,
        .precision = PH_NODE_SOLUTION_TEMP_PRECISION
    }
};

const size_t PH_NODE_SENSOR_CHANNELS_COUNT = sizeof(PH_NODE_SENSOR_CHANNELS) / sizeof(PH_NODE_SENSOR_CHANNELS[0]);

const ph_node_actuator_channel_t PH_NODE_ACTUATOR_CHANNELS[] = {
    {
        .name = "ph_doser_up",
        .gpio = PH_NODE_PH_DOSER_UP_GPIO,
        .fail_safe_nc = PH_NODE_PH_DOSER_FAIL_SAFE_NC,
        .max_duration_ms = PH_NODE_PH_DOSER_MAX_DURATION_MS,
        .min_off_ms = PH_NODE_PH_DOSER_MIN_OFF_MS,
        .ml_per_second = PH_NODE_PH_DOSER_ML_PER_SECOND
    },
    {
        .name = "ph_doser_down",
        .gpio = PH_NODE_PH_DOSER_DOWN_GPIO,
        .fail_safe_nc = PH_NODE_PH_DOSER_FAIL_SAFE_NC,
        .max_duration_ms = PH_NODE_PH_DOSER_MAX_DURATION_MS,
        .min_off_ms = PH_NODE_PH_DOSER_MIN_OFF_MS,
        .ml_per_second = PH_NODE_PH_DOSER_ML_PER_SECOND
    }
};

const size_t PH_NODE_ACTUATOR_CHANNELS_COUNT = sizeof(PH_NODE_ACTUATOR_CHANNELS) / sizeof(PH_NODE_ACTUATOR_CHANNELS[0]);

static cJSON *ph_node_build_sensor_entry(const ph_node_sensor_channel_t *sensor) {
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

static cJSON *ph_node_build_actuator_entry(const ph_node_actuator_channel_t *actuator) {
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

cJSON *ph_node_build_config_channels(void) {
    cJSON *channels = cJSON_CreateArray();
    if (!channels) {
        return NULL;
    }

    for (size_t i = 0; i < PH_NODE_SENSOR_CHANNELS_COUNT; i++) {
        cJSON *entry = ph_node_build_sensor_entry(&PH_NODE_SENSOR_CHANNELS[i]);
        if (!entry) {
            cJSON_Delete(channels);
            return NULL;
        }
        cJSON_AddItemToArray(channels, entry);
    }

    for (size_t i = 0; i < PH_NODE_ACTUATOR_CHANNELS_COUNT; i++) {
        cJSON *entry = ph_node_build_actuator_entry(&PH_NODE_ACTUATOR_CHANNELS[i]);
        if (!entry) {
            cJSON_Delete(channels);
            return NULL;
        }
        cJSON_AddItemToArray(channels, entry);
    }

    return channels;
}
