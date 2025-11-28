/**
 * @file relay_node_app.h
 * @brief Main application header for relay_node
 * 
 * Тонкий слой координации - геттеры/сеттеры делегируют в компоненты
 * Объединяет заголовки: tasks, init, telemetry
 */

#ifndef RELAY_NODE_APP_H
#define RELAY_NODE_APP_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize relay_node application
 */
void relay_node_app_init(void);

/**
 * @brief Start FreeRTOS tasks
 */
void relay_node_start_tasks(void);

/**
 * @brief Initialize all relay_node components
 * @return ESP_OK on success
 */
esp_err_t relay_node_init_components(void);

/**
 * @brief Publish STATUS message
 */
void relay_node_publish_status(void);

// State getters - делегируют в компоненты
bool relay_node_is_relay_control_initialized(void);
bool relay_node_is_oled_initialized(void);

// Node ID getter/setter - использует config_storage
const char* relay_node_get_node_id(void);
void relay_node_set_node_id(const char *node_id);

#ifdef __cplusplus
}
#endif

#endif // RELAY_NODE_APP_H

