#include "storage_irrigation_node_channel_map.h"
#include "storage_irrigation_node_defaults.h"
#include "cJSON.h"

const storage_irrigation_node_sensor_channel_t STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[] = {
    {
        .name = "level_clean_min",
        .metric = "WATER_LEVEL_SWITCH",
        .unit = "bool",
        .gpio = STORAGE_IRRIGATION_NODE_LEVEL_CLEAN_MIN_GPIO,
        .active_low = STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_ACTIVE_LOW,
        .poll_interval_ms = STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_POLL_INTERVAL_MS,
        .precision = 0
    },
    {
        .name = "level_clean_max",
        .metric = "WATER_LEVEL_SWITCH",
        .unit = "bool",
        .gpio = STORAGE_IRRIGATION_NODE_LEVEL_CLEAN_MAX_GPIO,
        .active_low = STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_ACTIVE_LOW,
        .poll_interval_ms = STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_POLL_INTERVAL_MS,
        .precision = 0
    },
    {
        .name = "level_solution_min",
        .metric = "WATER_LEVEL_SWITCH",
        .unit = "bool",
        .gpio = STORAGE_IRRIGATION_NODE_LEVEL_SOLUTION_MIN_GPIO,
        .active_low = STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_ACTIVE_LOW,
        .poll_interval_ms = STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_POLL_INTERVAL_MS,
        .precision = 0
    },
    {
        .name = "level_solution_max",
        .metric = "WATER_LEVEL_SWITCH",
        .unit = "bool",
        .gpio = STORAGE_IRRIGATION_NODE_LEVEL_SOLUTION_MAX_GPIO,
        .active_low = STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_ACTIVE_LOW,
        .poll_interval_ms = STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_POLL_INTERVAL_MS,
        .precision = 0
    },
};

const size_t STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT =
    sizeof(STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS) / sizeof(STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[0]);

const storage_irrigation_node_actuator_channel_t STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS[] = {
    {
        .name = "pump_main",
        .gpio = STORAGE_IRRIGATION_NODE_PUMP_MAIN_GPIO,
        .fail_safe_nc = STORAGE_IRRIGATION_NODE_PUMP_FAIL_SAFE_NC,
        .max_duration_ms = STORAGE_IRRIGATION_NODE_PUMP_MAX_DURATION_MS,
        .min_off_ms = STORAGE_IRRIGATION_NODE_PUMP_MIN_OFF_MS,
        .ml_per_second = STORAGE_IRRIGATION_NODE_PUMP_ML_PER_SECOND
    },
    {
        .name = "valve_clean_fill",
        .gpio = STORAGE_IRRIGATION_NODE_VALVE_CLEAN_FILL_GPIO,
        .fail_safe_nc = STORAGE_IRRIGATION_NODE_PUMP_FAIL_SAFE_NC,
        .max_duration_ms = STORAGE_IRRIGATION_NODE_PUMP_MAX_DURATION_MS,
        .min_off_ms = STORAGE_IRRIGATION_NODE_PUMP_MIN_OFF_MS,
        .ml_per_second = STORAGE_IRRIGATION_NODE_PUMP_ML_PER_SECOND
    },
    {
        .name = "valve_clean_supply",
        .gpio = STORAGE_IRRIGATION_NODE_VALVE_CLEAN_SUPPLY_GPIO,
        .fail_safe_nc = STORAGE_IRRIGATION_NODE_PUMP_FAIL_SAFE_NC,
        .max_duration_ms = STORAGE_IRRIGATION_NODE_PUMP_MAX_DURATION_MS,
        .min_off_ms = STORAGE_IRRIGATION_NODE_PUMP_MIN_OFF_MS,
        .ml_per_second = STORAGE_IRRIGATION_NODE_PUMP_ML_PER_SECOND
    },
    {
        .name = "valve_solution_fill",
        .gpio = STORAGE_IRRIGATION_NODE_VALVE_SOLUTION_FILL_GPIO,
        .fail_safe_nc = STORAGE_IRRIGATION_NODE_PUMP_FAIL_SAFE_NC,
        .max_duration_ms = STORAGE_IRRIGATION_NODE_PUMP_MAX_DURATION_MS,
        .min_off_ms = STORAGE_IRRIGATION_NODE_PUMP_MIN_OFF_MS,
        .ml_per_second = STORAGE_IRRIGATION_NODE_PUMP_ML_PER_SECOND
    },
    {
        .name = "valve_solution_supply",
        .gpio = STORAGE_IRRIGATION_NODE_VALVE_SOLUTION_SUPPLY_GPIO,
        .fail_safe_nc = STORAGE_IRRIGATION_NODE_PUMP_FAIL_SAFE_NC,
        .max_duration_ms = STORAGE_IRRIGATION_NODE_PUMP_MAX_DURATION_MS,
        .min_off_ms = STORAGE_IRRIGATION_NODE_PUMP_MIN_OFF_MS,
        .ml_per_second = STORAGE_IRRIGATION_NODE_PUMP_ML_PER_SECOND
    },
    {
        .name = "valve_irrigation",
        .gpio = STORAGE_IRRIGATION_NODE_VALVE_IRRIGATION_GPIO,
        .fail_safe_nc = STORAGE_IRRIGATION_NODE_PUMP_FAIL_SAFE_NC,
        .max_duration_ms = STORAGE_IRRIGATION_NODE_PUMP_MAX_DURATION_MS,
        .min_off_ms = STORAGE_IRRIGATION_NODE_PUMP_MIN_OFF_MS,
        .ml_per_second = STORAGE_IRRIGATION_NODE_PUMP_ML_PER_SECOND
    }
};

const size_t STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT =
    sizeof(STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS) / sizeof(STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS[0]);

static cJSON *storage_irrigation_node_build_sensor_entry(const storage_irrigation_node_sensor_channel_t *sensor) {
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
    cJSON_AddNumberToObject(entry, "gpio", sensor->gpio);
    cJSON_AddBoolToObject(entry, "active_low", sensor->active_low);
    if (sensor->poll_interval_ms > 0) {
        cJSON_AddNumberToObject(entry, "poll_interval_ms", sensor->poll_interval_ms);
    }
    if (sensor->precision >= 0) {
        cJSON_AddNumberToObject(entry, "precision", sensor->precision);
    }

    return entry;
}

static cJSON *storage_irrigation_node_build_actuator_entry(
    const storage_irrigation_node_actuator_channel_t *actuator
) {
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
    cJSON_AddStringToObject(entry, "actuator_type", "PUMP");
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

cJSON *storage_irrigation_node_build_config_channels(void) {
    cJSON *channels = cJSON_CreateArray();
    if (!channels) {
        return NULL;
    }

    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT; i++) {
        cJSON *entry = storage_irrigation_node_build_sensor_entry(&STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[i]);
        if (!entry) {
            cJSON_Delete(channels);
            return NULL;
        }
        cJSON_AddItemToArray(channels, entry);
    }

    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT; i++) {
        cJSON *entry = storage_irrigation_node_build_actuator_entry(&STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS[i]);
        if (!entry) {
            cJSON_Delete(channels);
            return NULL;
        }
        cJSON_AddItemToArray(channels, entry);
    }

    return channels;
}
