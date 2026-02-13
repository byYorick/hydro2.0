/**
 * @file relay_node_hw_map.h
 * @brief Аппаратная карта каналов реле: имя -> GPIO/режим.
 *
 * Каналы и GPIO задаются прошивкой и не приходят с сервера.
 * Отредактируйте массив RELAY_NODE_HW_CHANNELS под свою плату.
 */

#ifndef RELAY_NODE_HW_MAP_H
#define RELAY_NODE_HW_MAP_H

#ifdef __cplusplus
extern "C" {
#endif

#include "relay_driver.h"
#include <stdbool.h>
#include <stddef.h>

typedef struct {
    const char *channel_name;
    int gpio_pin;
    bool active_high;
    relay_type_t relay_type;
} relay_node_hw_channel_t;

#ifndef RELAY_NODE_HW_CHANNELS_DEF
// Аппаратная карта под водную обвязку зоны:
// - fill_valve: подача чистой воды в резервуар зоны
// - water_control: переключение линии "коррекция pH/EC" ↔ "полив"
// - drain_valve: дренаж (только для субстрата)
// TODO: скорректировать GPIO под реальную плату.
#define RELAY_NODE_HW_CHANNELS_DEF                     \
    { "fill_valve",    4,  false, RELAY_TYPE_NO },     \
    { "water_control", 5,  false, RELAY_TYPE_NO },     \
    { "drain_valve",   18, false, RELAY_TYPE_NO }
#endif

extern const relay_node_hw_channel_t RELAY_NODE_HW_CHANNELS[];
extern const size_t RELAY_NODE_HW_CHANNELS_COUNT;

#ifdef __cplusplus
}
#endif

#endif // RELAY_NODE_HW_MAP_H
