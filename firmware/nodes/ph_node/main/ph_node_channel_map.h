/**
 * @file ph_node_channel_map.h
 * @brief Жёстко заданные каналы ph_node
 *
 * Каналы описаны в прошивке и не принимаются из MQTT.
 */

#ifndef PH_NODE_CHANNEL_MAP_H
#define PH_NODE_CHANNEL_MAP_H

#include "cJSON.h"
#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    const char *name;
    const char *metric;
    const char *unit;
    int poll_interval_ms;
    int precision;
} ph_node_sensor_channel_t;

typedef struct {
    const char *name;
    int gpio;
    bool fail_safe_nc;
    uint32_t max_duration_ms;
    uint32_t min_off_ms;
    float ml_per_second;
} ph_node_actuator_channel_t;

extern const ph_node_sensor_channel_t PH_NODE_SENSOR_CHANNELS[];
extern const size_t PH_NODE_SENSOR_CHANNELS_COUNT;

extern const ph_node_actuator_channel_t PH_NODE_ACTUATOR_CHANNELS[];
extern const size_t PH_NODE_ACTUATOR_CHANNELS_COUNT;

/**
 * @brief Создаёт cJSON массив каналов (sensor + actuator)
 *
 * @return Новый cJSON массив или NULL при ошибке (владелец вызывает cJSON_Delete)
 */
cJSON *ph_node_build_config_channels(void);

#ifdef __cplusplus
}
#endif

#endif // PH_NODE_CHANNEL_MAP_H
