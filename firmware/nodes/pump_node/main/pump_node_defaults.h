/**
 * @file pump_node_defaults.h
 * @brief Централизованные значения по умолчанию для pump_node
 * 
 * Все дефолтные значения собраны здесь для избежания дублирования
 * и упрощения обновления конфигурации.
 */

#ifndef PUMP_NODE_DEFAULTS_H
#define PUMP_NODE_DEFAULTS_H

#ifdef __cplusplus
extern "C" {
#endif

#include "driver/gpio.h"

// Node identification defaults
#define PUMP_NODE_DEFAULT_NODE_ID      "nd-pump-1"
#define PUMP_NODE_DEFAULT_GH_UID       "gh-1"
#define PUMP_NODE_DEFAULT_ZONE_UID     "zn-3"

// MQTT defaults
#define PUMP_NODE_DEFAULT_MQTT_HOST    "192.168.1.10"
#define PUMP_NODE_DEFAULT_MQTT_PORT    1883
#define PUMP_NODE_DEFAULT_MQTT_KEEPALIVE 30

// I2C bus defaults (для INA209 и OLED)
#define PUMP_NODE_I2C_BUS_0_SDA        21  // ESP32 стандартный SDA (INA209 + OLED)
#define PUMP_NODE_I2C_BUS_0_SCL        22  // ESP32 стандартный SCL
#define PUMP_NODE_I2C_CLOCK_SPEED      100000

// OLED defaults (опционально)
#define PUMP_NODE_OLED_I2C_ADDRESS    0x3C
#define PUMP_NODE_OLED_UPDATE_INTERVAL_MS 1500

// Setup portal defaults
#define PUMP_NODE_SETUP_AP_PASSWORD    "hydro2025"

// Factory reset (long-press) defaults
#define PUMP_NODE_FACTORY_RESET_GPIO           GPIO_NUM_0  // BOOT button on most devkits
#define PUMP_NODE_FACTORY_RESET_ACTIVE_LOW     1
#define PUMP_NODE_FACTORY_RESET_HOLD_MS        20000U
#define PUMP_NODE_FACTORY_RESET_POLL_INTERVAL  50U

#ifdef __cplusplus
}
#endif

#endif // PUMP_NODE_DEFAULTS_H

