/**
 * @file ph_node_app.h
 * @brief Main application header for ph_node
 */

#ifndef PH_NODE_APP_H
#define PH_NODE_APP_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize ph_node application
 */
void ph_node_app_init(void);

/**
 * @brief Start FreeRTOS tasks
 */
void ph_node_start_tasks(void);

// State getters/setters for components
bool ph_node_is_ph_sensor_initialized(void);
void ph_node_set_ph_sensor_initialized(bool initialized);

bool ph_node_is_oled_initialized(void);
void ph_node_set_oled_initialized(bool initialized);

bool ph_node_is_pump_control_initialized(void);
void ph_node_set_pump_control_initialized(bool initialized);

const char* ph_node_get_node_id(void);
void ph_node_set_node_id(const char *node_id);

#ifdef __cplusplus
}
#endif

#endif // PH_NODE_APP_H

