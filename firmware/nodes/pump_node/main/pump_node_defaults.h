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

// Node identification defaults
#define PUMP_NODE_DEFAULT_NODE_ID      "nd-pump-1"
#define PUMP_NODE_DEFAULT_GH_UID       "gh-1"
#define PUMP_NODE_DEFAULT_ZONE_UID     "zn-3"

// MQTT defaults
#define PUMP_NODE_DEFAULT_MQTT_HOST    "192.168.1.10"
#define PUMP_NODE_DEFAULT_MQTT_PORT    1883
#define PUMP_NODE_DEFAULT_MQTT_KEEPALIVE 30

// I2C bus defaults (для INA209)
#define PUMP_NODE_I2C_BUS_0_SDA        21  // ESP32 стандартный SDA (INA209)
#define PUMP_NODE_I2C_BUS_0_SCL        22  // ESP32 стандартный SCL
#define PUMP_NODE_I2C_CLOCK_SPEED      100000

// Setup portal defaults
#define PUMP_NODE_SETUP_AP_PASSWORD    "hydro2025"

#ifdef __cplusplus
}
#endif

#endif // PUMP_NODE_DEFAULTS_H

