/**
 * @file ph_node_defaults.h
 * @brief Централизованные значения по умолчанию для ph_node
 * 
 * Все дефолтные значения собраны здесь для избежания дублирования
 * и упрощения обновления конфигурации.
 */

#ifndef PH_NODE_DEFAULTS_H
#define PH_NODE_DEFAULTS_H

#ifdef __cplusplus
extern "C" {
#endif

#include "driver/gpio.h"

// Node identification defaults
#define PH_NODE_DEFAULT_NODE_ID      "nd-ph-1"
#define PH_NODE_DEFAULT_GH_UID       "gh-1"
#define PH_NODE_DEFAULT_ZONE_UID     "zn-3"

// MQTT defaults
#define PH_NODE_DEFAULT_MQTT_HOST    "192.168.1.10"
#define PH_NODE_DEFAULT_MQTT_PORT    1883
#define PH_NODE_DEFAULT_MQTT_KEEPALIVE 30

// Sensor polling defaults
#define PH_NODE_PH_SENSOR_POLL_INTERVAL_MS     3000
#define PH_NODE_PH_SENSOR_PRECISION            2
#define PH_NODE_SOLUTION_TEMP_POLL_INTERVAL_MS 5000
#define PH_NODE_SOLUTION_TEMP_PRECISION        1

// I2C bus defaults
#define PH_NODE_I2C_BUS_0_SDA        21  // ESP32 стандартный SDA (OLED + INA209)
#define PH_NODE_I2C_BUS_0_SCL        22  // ESP32 стандартный SCL
#define PH_NODE_I2C_BUS_1_SDA        18  // ESP32 альтернативный SDA (pH sensor)
#define PH_NODE_I2C_BUS_1_SCL        19  // ESP32 альтернативный SCL
#define PH_NODE_I2C_CLOCK_SPEED      100000

// OLED defaults
#define PH_NODE_OLED_I2C_ADDRESS    0x3C
#define PH_NODE_OLED_UPDATE_INTERVAL_MS 1500

// Setup portal defaults
#define PH_NODE_SETUP_AP_PASSWORD    "hydro2025"

// Factory reset (long-press) defaults
#define PH_NODE_FACTORY_RESET_GPIO           GPIO_NUM_0  // BOOT button on most devkits
#define PH_NODE_FACTORY_RESET_ACTIVE_LOW     1
#define PH_NODE_FACTORY_RESET_HOLD_MS        20000U
#define PH_NODE_FACTORY_RESET_POLL_INTERVAL  50U

// pH pump actuator defaults
#define PH_NODE_PH_DOSER_UP_GPIO            GPIO_NUM_12
#define PH_NODE_PH_DOSER_DOWN_GPIO          GPIO_NUM_13
#define PH_NODE_PH_DOSER_FAIL_SAFE_NC       0
#define PH_NODE_PH_DOSER_MAX_DURATION_MS    15000U
#define PH_NODE_PH_DOSER_MIN_OFF_MS         5000U
#define PH_NODE_PH_DOSER_ML_PER_SECOND      1.5f

// Pump current limits (INA209)
#define PH_NODE_PUMP_CURRENT_MIN_MA        50.0f
#define PH_NODE_PUMP_CURRENT_MAX_MA        500.0f

#ifdef __cplusplus
}
#endif

#endif // PH_NODE_DEFAULTS_H
