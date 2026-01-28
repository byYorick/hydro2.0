/**
 * @file ec_node_channel_map.h
 * @brief Встроенные каналы ec_node (сенсоры и актуаторы).
 */

#ifndef EC_NODE_CHANNEL_MAP_H
#define EC_NODE_CHANNEL_MAP_H

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
    uint32_t poll_interval_ms;
    int precision;
} ec_node_sensor_channel_t;

typedef struct {
    const char *name;
    int gpio;
    bool fail_safe_nc;
    uint32_t max_duration_ms;
    uint32_t min_off_ms;
    float ml_per_second;
} ec_node_actuator_channel_t;

extern const ec_node_sensor_channel_t EC_NODE_SENSOR_CHANNELS[];
extern const size_t EC_NODE_SENSOR_CHANNELS_COUNT;

extern const ec_node_actuator_channel_t EC_NODE_ACTUATOR_CHANNELS[];
extern const size_t EC_NODE_ACTUATOR_CHANNELS_COUNT;

cJSON *ec_node_build_config_channels(void);

#ifdef __cplusplus
}
#endif

#endif // EC_NODE_CHANNEL_MAP_H
