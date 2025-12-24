/**
 * @file ec_node_defaults.h
 * @brief Централизованные значения по умолчанию для ec_node
 * 
 * Все дефолтные значения собраны здесь для избежания дублирования
 * и упрощения обновления конфигурации.
 */

#ifndef EC_NODE_DEFAULTS_H
#define EC_NODE_DEFAULTS_H

#ifdef __cplusplus
extern "C" {
#endif

#include "driver/gpio.h"

// Node identification defaults
#define EC_NODE_DEFAULT_NODE_ID      "nd-ec-1"
#define EC_NODE_DEFAULT_GH_UID       "gh-1"
#define EC_NODE_DEFAULT_ZONE_UID     "zn-3"

// MQTT defaults
#define EC_NODE_DEFAULT_MQTT_HOST    "192.168.1.10"
#define EC_NODE_DEFAULT_MQTT_PORT    1883
#define EC_NODE_DEFAULT_MQTT_KEEPALIVE 30

// I2C bus defaults
// trema_ec использует дефолтную шину (I2C_BUS_0), поэтому EC sensor тоже на I2C_BUS_0
#define EC_NODE_I2C_BUS_0_SDA        21  // ESP32 стандартный SDA (OLED + EC sensor)
#define EC_NODE_I2C_BUS_0_SCL        22  // ESP32 стандартный SCL
#define EC_NODE_I2C_CLOCK_SPEED      100000

// OLED defaults
#define EC_NODE_OLED_I2C_ADDRESS    0x3C
#define EC_NODE_OLED_UPDATE_INTERVAL_MS 1500

// Setup portal defaults
#define EC_NODE_SETUP_AP_PASSWORD    "hydro2025"

// Factory reset (long-press) defaults
#define EC_NODE_FACTORY_RESET_GPIO           GPIO_NUM_0  // BOOT button on most devkits
#define EC_NODE_FACTORY_RESET_ACTIVE_LOW     1
#define EC_NODE_FACTORY_RESET_HOLD_MS        20000U
#define EC_NODE_FACTORY_RESET_POLL_INTERVAL  50U

#ifdef __cplusplus
}
#endif

#endif // EC_NODE_DEFAULTS_H

