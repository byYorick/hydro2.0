/**
 * @file climate_node_defaults.h
 * @brief Централизованные значения по умолчанию для climate_node
 * 
 * Все дефолтные значения собраны здесь для избежания дублирования
 * и упрощения обновления конфигурации.
 */

#ifndef CLIMATE_NODE_DEFAULTS_H
#define CLIMATE_NODE_DEFAULTS_H

#ifdef __cplusplus
extern "C" {
#endif

#include "driver/gpio.h"

// Node identification defaults
#define CLIMATE_NODE_DEFAULT_NODE_ID      "nd-climate-1"
#define CLIMATE_NODE_DEFAULT_GH_UID       "gh-1"
#define CLIMATE_NODE_DEFAULT_ZONE_UID     "zn-1"

// MQTT defaults
#define CLIMATE_NODE_DEFAULT_MQTT_HOST    "192.168.1.10"
#define CLIMATE_NODE_DEFAULT_MQTT_PORT    1883
#define CLIMATE_NODE_DEFAULT_MQTT_KEEPALIVE 30

// I2C bus defaults
// I2C_BUS_0 для OLED (используется в setup mode и normal mode)
#define CLIMATE_NODE_I2C_BUS_0_SDA        5   // SDA для OLED
#define CLIMATE_NODE_I2C_BUS_0_SCL        4   // SCL для OLED
// I2C_BUS_1 для датчиков
// GPIO 25 (DAC1) и GPIO 26 (DAC2) имеют встроенные ЦАП, но в проекте не используются
// Можно использовать для I2C, если функции DAC не нужны
#define CLIMATE_NODE_I2C_BUS_1_SDA        25  // SDA для SHT3x (GPIO 25)
#define CLIMATE_NODE_I2C_BUS_1_SCL        26  // SCL для SHT3x (GPIO 26)
#define CLIMATE_NODE_I2C_CLOCK_SPEED      100000

// OLED defaults
#define CLIMATE_NODE_OLED_I2C_ADDRESS    0x3C
#define CLIMATE_NODE_OLED_UPDATE_INTERVAL_MS 1500

// Setup portal defaults
/* NULL: setup_portal генерирует пароль AP на сессию и пишет его в serial. */
#define CLIMATE_NODE_SETUP_AP_PASSWORD    NULL

// Factory reset (long-press) defaults
#define CLIMATE_NODE_FACTORY_RESET_GPIO           GPIO_NUM_0  // BOOT button on most devkits
#define CLIMATE_NODE_FACTORY_RESET_ACTIVE_LOW     1
#define CLIMATE_NODE_FACTORY_RESET_HOLD_MS        20000U
#define CLIMATE_NODE_FACTORY_RESET_POLL_INTERVAL  50U

/* Фрамуги: два реле направления и концевик полного закрытия (active-low, подтяжка к питанию).
   Вытяжка: GPIO, если в NodeConfig нет реле fan_A/fan_B. E-STOP active-low с внутренней подтяжкой. */
#define CLIMATE_VENT_LEFT_OPEN_GPIO            GPIO_NUM_16
#define CLIMATE_VENT_LEFT_CLOSE_GPIO           GPIO_NUM_17
#define CLIMATE_VENT_LEFT_CLOSED_LIMIT_GPIO    GPIO_NUM_32
#define CLIMATE_VENT_RIGHT_OPEN_GPIO           GPIO_NUM_18
#define CLIMATE_VENT_RIGHT_CLOSE_GPIO          GPIO_NUM_19
#define CLIMATE_VENT_RIGHT_CLOSED_LIMIT_GPIO   GPIO_NUM_33
#define CLIMATE_EXHAUST_GPIO                   GPIO_NUM_27
#define CLIMATE_ESTOP_GPIO                     GPIO_NUM_13

#ifdef __cplusplus
}
#endif

#endif // CLIMATE_NODE_DEFAULTS_H

