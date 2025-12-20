/**
 * @file light_node_defaults.h
 * @brief Централизованные значения по умолчанию для light_node
 * 
 * Все дефолтные значения собраны здесь для избежания дублирования
 * и упрощения обновления конфигурации.
 */

#ifndef LIGHT_NODE_DEFAULTS_H
#define LIGHT_NODE_DEFAULTS_H

#ifdef __cplusplus
extern "C" {
#endif

#include "driver/gpio.h"

// Node identification defaults
#define LIGHT_NODE_DEFAULT_NODE_ID      "nd-light-1"
#define LIGHT_NODE_DEFAULT_GH_UID       "gh-1"
#define LIGHT_NODE_DEFAULT_ZONE_UID     "zn-2"

// MQTT defaults
#define LIGHT_NODE_DEFAULT_MQTT_HOST    "192.168.1.10"
#define LIGHT_NODE_DEFAULT_MQTT_PORT    1883
#define LIGHT_NODE_DEFAULT_MQTT_KEEPALIVE 30

// I2C bus defaults
// I2C_BUS_0 для OLED и датчика света (на одной шине)
#define LIGHT_NODE_I2C_BUS_0_SDA        4   // SDA для OLED и light sensor (GPIO 4)
#define LIGHT_NODE_I2C_BUS_0_SCL        5   // SCL для OLED и light sensor (GPIO 5)
#define LIGHT_NODE_I2C_CLOCK_SPEED      100000

// OLED defaults
#define LIGHT_NODE_OLED_I2C_ADDRESS    0x3C
#define LIGHT_NODE_OLED_UPDATE_INTERVAL_MS 1500

// Light sensor defaults
#define LIGHT_NODE_LIGHT_SENSOR_POLL_INTERVAL_MS 3000
#define LIGHT_NODE_LIGHT_SENSOR_PRECISION 0

// Setup portal defaults
#define LIGHT_NODE_SETUP_AP_PASSWORD    "hydro2025"

// Factory reset (long-press) defaults
// ESP32-C3: BOOT button обычно на GPIO9
#define LIGHT_NODE_FACTORY_RESET_GPIO           GPIO_NUM_9
#define LIGHT_NODE_FACTORY_RESET_ACTIVE_LOW     1
#define LIGHT_NODE_FACTORY_RESET_HOLD_MS        20000U
#define LIGHT_NODE_FACTORY_RESET_POLL_INTERVAL  50U

#ifdef __cplusplus
}
#endif

#endif // LIGHT_NODE_DEFAULTS_H
