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
// Пример аппаратной карты: 4 канала.
#define RELAY_NODE_HW_CHANNELS_DEF                     \
    { "relay1", 4,  true, RELAY_TYPE_NO },             \
    { "relay2", 5,  true, RELAY_TYPE_NO },             \
    { "relay3", 18, true, RELAY_TYPE_NO },             \
    { "relay4", 19, true, RELAY_TYPE_NO }
#endif

extern const relay_node_hw_channel_t RELAY_NODE_HW_CHANNELS[];
extern const size_t RELAY_NODE_HW_CHANNELS_COUNT;

#ifdef __cplusplus
}
#endif

#endif // RELAY_NODE_HW_MAP_H
