/**
 * @file ec_node_app.h
 * @brief Main application header for ec_node
 * 
 * Тонкий слой координации - геттеры/сеттеры делегируют в компоненты
 * Объединяет заголовки: tasks, init, telemetry
 */

#ifndef EC_NODE_APP_H
#define EC_NODE_APP_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize ec_node application
 */
void ec_node_app_init(void);

/**
 * @brief Start FreeRTOS tasks
 */
void ec_node_start_tasks(void);

// State getters - делегируют в компоненты
bool ec_node_is_ec_sensor_initialized(void);
bool ec_node_is_oled_initialized(void);
bool ec_node_is_pump_control_initialized(void);

// Node ID getter/setter - использует config_storage
const char* ec_node_get_node_id(void);
void ec_node_set_node_id(const char *node_id);

#ifdef __cplusplus
}
#endif

#endif // EC_NODE_APP_H

