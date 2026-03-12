/**
 * @file storage_irrigation_node_channel_map.h
 * @brief Встроенные каналы storage_irrigation_node.
 */

#ifndef STORAGE_IRRIGATION_NODE_CHANNEL_MAP_H
#define STORAGE_IRRIGATION_NODE_CHANNEL_MAP_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include "cJSON.h"

typedef struct {
    const char *name;
    const char *metric;
    const char *unit;
    int gpio;
    bool active_low;
    uint32_t poll_interval_ms;
    int precision;
} storage_irrigation_node_sensor_channel_t;

typedef struct {
    const char *name;
    int gpio;
    bool fail_safe_nc;
    uint32_t max_duration_ms;
    uint32_t min_off_ms;
    float ml_per_second;
} storage_irrigation_node_actuator_channel_t;

extern const storage_irrigation_node_sensor_channel_t STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[];
extern const size_t STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT;

extern const storage_irrigation_node_actuator_channel_t STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS[];
extern const size_t STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT;

cJSON *storage_irrigation_node_build_config_channels(void);

#ifdef __cplusplus
}
#endif

#endif // STORAGE_IRRIGATION_NODE_CHANNEL_MAP_H
