/**
 * @file light_node_channel_map.h
 * @brief Встроенные каналы light_node.
 */

#ifndef LIGHT_NODE_CHANNEL_MAP_H
#define LIGHT_NODE_CHANNEL_MAP_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>
#include <stdint.h>
#include "cJSON.h"

typedef struct {
    const char *name;
    const char *metric;
    const char *unit;
    uint32_t poll_interval_ms;
    int precision;
} light_node_sensor_channel_t;

extern const light_node_sensor_channel_t LIGHT_NODE_SENSOR_CHANNELS[];
extern const size_t LIGHT_NODE_SENSOR_CHANNELS_COUNT;

cJSON *light_node_build_config_channels(void);

#ifdef __cplusplus
}
#endif

#endif // LIGHT_NODE_CHANNEL_MAP_H
