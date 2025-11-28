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

// Node identification defaults
#define CLIMATE_NODE_DEFAULT_NODE_ID      "nd-climate-1"
#define CLIMATE_NODE_DEFAULT_GH_UID       "gh-1"
#define CLIMATE_NODE_DEFAULT_ZONE_UID     "zn-1"

// MQTT defaults
#define CLIMATE_NODE_DEFAULT_MQTT_HOST    "192.168.1.10"
#define CLIMATE_NODE_DEFAULT_MQTT_PORT    1883
#define CLIMATE_NODE_DEFAULT_MQTT_KEEPALIVE 30

// I2C bus defaults
#define CLIMATE_NODE_I2C_BUS_1_SDA        5   // SDA для датчиков (SHT3x, CCS811)
#define CLIMATE_NODE_I2C_BUS_1_SCL        4   // SCL для датчиков
#define CLIMATE_NODE_I2C_CLOCK_SPEED      100000

// OLED defaults
#define CLIMATE_NODE_OLED_I2C_ADDRESS    0x3C
#define CLIMATE_NODE_OLED_UPDATE_INTERVAL_MS 1500

// Setup portal defaults
#define CLIMATE_NODE_SETUP_AP_PASSWORD    "hydro2025"

#ifdef __cplusplus
}
#endif

#endif // CLIMATE_NODE_DEFAULTS_H

