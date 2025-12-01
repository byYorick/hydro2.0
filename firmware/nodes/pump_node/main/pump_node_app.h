/**
 * @file pump_node_app.h
 * @brief Main application header for pump_node
 * 
 * Тонкий слой координации - геттеры/сеттеры делегируют в компоненты
 * Объединяет заголовки: tasks, init, telemetry
 */

#ifndef PUMP_NODE_APP_H
#define PUMP_NODE_APP_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize pump_node application
 */
void pump_node_app_init(void);

/**
 * @brief Start FreeRTOS tasks
 */
void pump_node_start_tasks(void);

/**
 * @brief Initialize all pump_node components
 * @return ESP_OK on success
 */
esp_err_t pump_node_init_components(void);

/**
 * @brief Publish STATUS message
 */
void pump_node_publish_status(void);

// State getters - делегируют в компоненты
bool pump_node_is_pump_control_initialized(void);

// Node ID getter/setter - использует config_storage
const char* pump_node_get_node_id(void);
void pump_node_set_node_id(const char *node_id);

#ifdef __cplusplus
}
#endif

#endif // PUMP_NODE_APP_H

